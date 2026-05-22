"""Wire drag, selection, and clipboard state managers for the node editor.

These are pure data / algorithm classes that carry no Qt scene or view
inheritance.  NodeEditorScene and NodeEditorView both delegate to them.
"""
from __future__ import annotations

import json
import uuid
import weakref
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QApplication, QGraphicsScene

from sourcegraph.sys.graph import Connection
from sourcegraph.sys.history import MoveNodesCommand
from sourcegraph.sys.registry import NODE_CLASS_MAPPINGS

from sourcegraph.gui.items.node import NodeItem, PortItem
from sourcegraph.gui.items.wire import ConnectionItem

if TYPE_CHECKING:
    from sourcegraph.gui.node_editor.scene import NodeEditorScene


# -- Wire drag state -----------------------------------------------------------

@dataclass
class WireDragState:
    """Consolidates all transient wire-dragging fields that were previously
    scattered across the scene as separate attributes."""
    drag_conn:   ConnectionItem | None                       = field(default=None)
    drag_port:   PortItem       | None                       = field(default=None)
    hover_port:  PortItem       | None                       = field(default=None)
    moving_conn: tuple[Connection, ConnectionItem] | None    = field(default=None)

    def active(self) -> bool:
        return self.drag_conn is not None

    def clear(self, scene: QGraphicsScene) -> None:
        if self.drag_conn is not None:
            try:
                scene.removeItem(self.drag_conn)
            except RuntimeError:
                pass
        if self.hover_port is not None:
            try:
                self.hover_port.set_highlight(False)
            except RuntimeError:
                pass
        self.drag_conn = self.drag_port = self.hover_port = self.moving_conn = None


# -- Selection rubber-band mode ------------------------------------------------

class RubberBandMode(Enum):
    REPLACE  = auto()   # default: clear and select band contents
    ADD      = auto()   # Shift+drag: union with current selection
    SUBTRACT = auto()   # Ctrl+drag:  remove band contents from selection


# -- Selection move tracker ----------------------------------------------------

class SelectionMoveTracker:
    """Captures node positions at drag-start; pushes MoveNodesCommand on release."""

    def __init__(self) -> None:
        self._start: dict[str, QPointF] = {}

    def begin(self, items) -> None:
        self._start = {n.node.id: n.pos() for n in items if isinstance(n, NodeItem)}

    def commit(self, scene) -> None:
        if not self._start:
            return
        moves = [
            (nid, sp.x(), sp.y(), item.x(), item.y())
            for nid, sp in self._start.items()
            if (item := scene._node_items.get(nid)) and item.pos() != sp
        ]
        if moves:
            cmd = MoveNodesCommand(scene.graph, moves, weakref.ref(scene))
            scene._undo_manager._cmd_stack.push(cmd)
        self._start.clear()

    @property
    def active(self) -> bool:
        return bool(self._start)

    def clear(self) -> None:
        self._start.clear()


# -- Clipboard manager ---------------------------------------------------------

class ClipboardManager:
    """Handles copy/cut/paste/duplicate of nodes AND property-level clipboard.

    OS clipboard bridge:
      - Ctrl+Shift+C writes node properties as JSON to the OS clipboard.
      - Ctrl+Shift+V with a selected node pastes properties from the internal
        clipboard, or creates a node from OS clipboard JSON.
    """

    _data:          dict | None = None   # node+connections clipboard
    _property_data: dict | None = None  # {type, inputs} for property paste

    @classmethod
    def copy(cls, scene, items) -> None:
        node_ids = {n.node.id for n in items if isinstance(n, NodeItem)}
        cls._data = {
            "nodes": [n.node.to_dict() for n in items if isinstance(n, NodeItem)],
            "connections": [
                {"src_node": c.src_node, "src_port": c.src_port,
                 "dst_node": c.dst_node, "dst_port": c.dst_port}
                for c in scene.graph.connections
                if c.src_node in node_ids and c.dst_node in node_ids
            ],
        }
        cls.copy_to_os_clipboard(cls._data)

    @classmethod
    def cut(cls, scene, items) -> None:
        node_items = [i for i in items if isinstance(i, NodeItem)]
        if not node_items:
            return
        cls.copy(scene, node_items)
        with scene._undo_manager.transaction("Cut Selection"):
            for item in node_items:
                scene._delete_node(item, push_undo=False)
        scene._emit_graph_changed()

    @classmethod
    def paste(cls, scene, pos: QPointF | None = None) -> None:
        if cls._data:
            cls._do_paste(scene, cls._data, pos)

    @classmethod
    def duplicate(cls, scene, items, pos: QPointF | None = None) -> None:
        prev = cls._data
        cls.copy(scene, items)
        if cls._data:
            cls._do_paste(scene, cls._data, pos)
        cls._data = prev

    @classmethod
    def _do_paste(cls, scene, data: dict, pos: QPointF | None) -> None:
        nodes_data = data.get("nodes", [])
        if not nodes_data:
            return

        if pos is not None:
            min_x  = min(n["x"] for n in nodes_data)
            min_y  = min(n["y"] for n in nodes_data)
            offset = pos - QPointF(min_x, min_y)
        else:
            offset = QPointF(32, 32)

        scene._suppress_bus = True
        try:
            with scene._undo_manager.transaction("Paste Nodes"):
                id_map: dict[str, str] = {}
                nodes_to_paste = []

                for n_dict in nodes_data:
                    cls_node = NODE_CLASS_MAPPINGS.get(n_dict["type"])
                    if not cls_node:
                        continue
                    new_dict          = n_dict.copy()
                    old_id            = new_dict["id"]
                    new_id            = str(uuid.uuid4())
                    id_map[old_id]    = new_id
                    new_dict["id"]    = new_id
                    new_dict["x"]    += offset.x()
                    new_dict["y"]    += offset.y()
                    node              = cls_node.from_dict(new_dict)
                    node.graph        = scene.graph
                    nodes_to_paste.append(node)

                scene.clearSelection()
                for node in nodes_to_paste:
                    scene.graph.add_node(node)
                    item = NodeItem(node)
                    scene._node_items[node.id] = item
                    scene.addItem(item)
                    item.setSelected(True)
                    scene._after_node_mutation(node.id)

                for c_dict in data.get("connections", []):
                    sn = id_map.get(c_dict["src_node"])
                    dn = id_map.get(c_dict["dst_node"])
                    if sn and dn:
                        scene.graph.connect(sn, c_dict["src_port"], dn, c_dict["dst_port"])
                        conn = scene.graph.get_input_connection(dn, c_dict["dst_port"])
                        if conn:
                            scene._materialise_conn(conn)
        finally:
            scene._suppress_bus = False

        scene._flush_updates()

    @classmethod
    def copy_properties(cls, node_item: NodeItem) -> None:
        props = {name: port.value for name, port in node_item.node.inputs.items()}
        meta  = {"type": type(node_item.node).__name__, "inputs": props}
        cls._property_data = meta
        cls.copy_to_os_clipboard(meta)

    @classmethod
    def paste_properties(cls, scene, target: NodeItem) -> None:
        data = cls._property_data
        if not data:
            return
        with scene._undo_manager.transaction("Paste Properties"):
            changed = False
            for name, value in data.get("inputs", {}).items():
                if name in target.node.inputs:
                    port = target.node.inputs[name]
                    if port.value != value:
                        port.value = value
                        changed    = True
            if changed:
                scene._after_node_mutation(target.node.id)
                scene._emit_graph_changed()

    @classmethod
    def copy_to_os_clipboard(cls, data: dict) -> None:
        QApplication.clipboard().setText(json.dumps(data, indent=2))

    @classmethod
    def try_paste_from_os_clipboard(cls, scene, pos: QPointF) -> bool:
        text = QApplication.clipboard().text().strip()
        if not text:
            return False
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return False
        if not isinstance(data, dict):
            return False

        if "nodes" in data:
            cls._data = data
            cls._do_paste(scene, data, pos)
            return True

        node_type = data.get("type")
        if node_type and node_type in NODE_CLASS_MAPPINGS:
            cls_node = NODE_CLASS_MAPPINGS[node_type]
            node     = cls_node()
            for name, value in data.get("inputs", {}).items():
                if name in node.inputs:
                    node.inputs[name].value = value
            scene.add_node(node, pos)
            return True

        return False
