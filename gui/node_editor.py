from __future__ import annotations
import os
import json
import math
import weakref
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto

from PySide6.QtWidgets import (QGraphicsScene, QGraphicsView, QMenu,
                                QWidget, QFileDialog, QLabel,
                                QGraphicsOpacityEffect, QDialog, QApplication)
from PySide6.QtGui     import (QColor, QPainter, QBrush, QPen, QKeySequence,
                                QKeyEvent, QWheelEvent, QMouseEvent, QCursor,
                                QUndoCommand, QUndoStack, QDragEnterEvent, QDropEvent,
                                QDragMoveEvent, QAction, QFont, QPixmap,
                                QSurfaceFormat, QPainterPath, QTransform, qGray)
from PySide6.QtCore    import Qt, QPointF, QPoint, QRect, Signal, QRectF, QTimer, QPropertyAnimation
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from core.graph import Graph, Connection
from core.node import port_uses_graph_variables
from core.history import create_history_manager, HistoryManager
from core.events import (
    NodeAddedEvent, NodeRemovedEvent,
    ConnectionAddedEvent, ConnectionRemovedEvent,
    GraphLoadedEvent,
)
from core.history import (
    AddNodeCommand, RemoveNodeCommand, ConnectCommand,
    DisconnectCommand, MoveNodesCommand,
)
from core.recent_nodes import add_recent_node
from gui.widgets.icon_provider import load_pixmap
from gui.widgets.safe_graphics_view import SafeGraphicsView
from core.registry import NODE_CLASS_MAPPINGS, NODE_CATEGORIES
from nodes.subgraph.subgraph import SubgraphNode, SubgraphInputNode, SubgraphOutputNode
from gui.items.node       import NodeItem, ResizeHandle, PortItem, DEFAULT_W
from gui.commands         import PropertyCommand, FoldCommand, ResizeNodeCommand
from gui.items.wire       import ConnectionItem
from gui.dialogs          import RenameDialog
from gui.theme            import *
from gui.logger           import log
from gui.widgets.basic_shapes import ShapeDrawer
from gui.menu.node_search_dialog import NodeSearchDialog
from gui.background_renderer import (
    BackgroundRenderer, GridBackgroundRenderer,
    ModernGLBackgroundRenderer,
)


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
      - Ctrl+Shift+V with a selected node pastes properties from internal
        clipboard onto it, or creates a node from OS clipboard JSON.
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


# -- Shortcut registry ---------------------------------------------------------

class ShortcutRegistry:
    """Maps (key, modifiers) pairs to callbacks.  keyPressEvent calls handle()."""

    def __init__(self) -> None:
        self._bindings: list[tuple[int, Qt.KeyboardModifier, object, str]] = []

    def register(
        self,
        key:         int,
        modifiers:   Qt.KeyboardModifier,
        callback,
        description: str = "",
    ) -> None:
        self._bindings.append((key, Qt.KeyboardModifier(modifiers), callback, description))

    def handle(self, event: QKeyEvent) -> bool:
        k = event.key()
        m = Qt.KeyboardModifier(event.modifiers())
        for key, mods, cb, _ in self._bindings:
            if k == key and m == mods:
                cb()
                return True
        return False


# -- Context menu factory ------------------------------------------------------

class ContextMenuFactory:
    """Builds and executes context menus for nodes, ports, and the background."""

    @staticmethod
    def exec_node_menu(scene, view, item: NodeItem, global_pos) -> None:
        item.setSelected(True)
        menu = QMenu(view)
        menu.setStyleSheet(MENU)

        rename_act  = menu.addAction("Rename")  if not item.node.locked_title else None
        open_act    = menu.addAction("Open Subgraph") if isinstance(item.node, SubgraphNode) else None
        resize_act  = menu.addAction("Resize")
        convert_act = menu.addAction("Convert to Subgraph")
        fold_act    = menu.addAction("Unfold" if item.node.folded else "Fold")
        menu.addSeparator()
        copy_props_act  = menu.addAction("Copy Properties")
        paste_props_act = menu.addAction("Paste Properties")
        menu.addSeparator()
        delete_act      = menu.addAction("Delete")
        menu.addSeparator()
        add_exec_act    = menu.addAction("Add to Execution")

        action = menu.exec(global_pos)
        if not action:
            return

        if action == open_act:
            path = item.node.inputs.get("graph_path").value
            if path:
                view.subgraph_requested.emit(path)
        elif action == rename_act:
            scene._start_rename(item)
        elif action == resize_act:
            if item.node.folded:
                item.node.folded = False
                default_h = item._calculate_height()
                item.node.folded = True
                old_h = item._unfolded_height
            else:
                default_h = item._calculate_height()
                old_h = item._h
            cmd = ResizeNodeCommand(item, item._w, old_h, DEFAULT_W, default_h)
            scene._undo_manager.undo_stack.push(cmd)
        elif action == convert_act:
            targets = [i for i in scene.selectedItems() if isinstance(i, NodeItem)]
            if not targets:
                targets = [item]
            scene._convert_to_subgraph(targets)
        elif action == fold_act:
            cmd = FoldCommand(item, item.node.folded, not item.node.folded)
            scene._undo_manager.push(cmd)
        elif action == copy_props_act:
            ClipboardManager.copy_properties(item)
        elif action == paste_props_act:
            ClipboardManager.paste_properties(scene, item)
        elif action == delete_act:
            scene.remove_selected()
        elif action == add_exec_act:
            mw = view.window()
            exec_widget = mw.panel_manager.get_widget("ExecutionDock") if hasattr(mw, "panel_manager") else None
            if exec_widget:
                with scene._undo_manager.transaction("Add to Execution"):
                    if not item.isSelected():
                        scene.clearSelection()
                        item.setSelected(True)
                    exec_widget._add_selected_node()
                exec_panel = mw.panel_manager.get_panel("ExecutionDock")
                if exec_panel:
                    exec_panel.show()
                    exec_panel.raise_()

    @staticmethod
    def exec_port_menu(scene, view, item: PortItem, global_pos) -> None:
        conn = scene.graph.get_input_connection(item.port.node_id, item.port.name)
        menu = QMenu(view)
        menu.setStyleSheet(MENU)

        if conn:
            delete_act = menu.addAction("Delete connection")
            action = menu.exec(global_pos)
            if action == delete_act:
                with scene._undo_manager.transaction("Delete Connection"):
                    for pair in list(scene._conn_items):
                        if pair[0] == conn:
                            scene._delete_conn(pair[1], push_undo=False)
                            break
        else:
            create_act = menu.addAction("Create wire")
            action = menu.exec(global_pos)
            if action == create_act:
                scene._wire_drag.drag_port = item
                scene._wire_drag.drag_conn = ConnectionItem(
                    item.scene_center(), src_port_type=item.port.port_type)
                scene.addItem(scene._wire_drag.drag_conn)

    @staticmethod
    def exec_background_menu(scene, view, scene_pos: QPointF, global_pos) -> None:
        menu = QMenu(view)
        menu.setStyleSheet(MENU)
        for cat, classes in NODE_CATEGORIES.items():
            sub = menu.addMenu(cat)
            for cls in classes:
                act = sub.addAction(cls.title)
                def _trigger(checked, c=cls, p=scene_pos):
                    scene.add_node(c(), p)
                act.triggered.connect(_trigger)
        menu.exec(global_pos)


# -- Minimap widget ------------------------------------------------------------

class MinimapWidget(QWidget):
    closed = Signal()

    def __init__(self, view: "NodeEditorView", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.show_node_colors  = True
        self.show_links        = True
        self.render_error_state = True
        self.view              = view
        self.setMouseTracking(True)
        self.setMinimumSize(100, 80)
        # Cache QPainterPath per connection; only rebuild when endpoints/style change.
        self._conn_path_cache:     dict[tuple, QPainterPath] = {}
        self._conn_endpoint_cache: dict[tuple, tuple]        = {}

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg = QColor(0, 0, 0, 80)
        painter.setBrush(bg)
        painter.setPen(QPen(bg, 1))
        painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

        scene = self.view.scene()
        if scene is None:
            self._draw_controls(painter)
            painter.end()
            return

        try:
            nodes = [i for i in scene.items() if isinstance(i, NodeItem)]
        except RuntimeError:
            self._draw_controls(painter)
            painter.end()
            return

        if not nodes:
            self._draw_controls(painter)
            painter.end()
            return

        rect = nodes[0].sceneBoundingRect()
        for n in nodes[1:]:
            rect = rect.united(n.sceneBoundingRect())
        margin = max(rect.width(), rect.height()) * 0.15
        rect.adjust(-margin, -margin, margin, margin)

        w_rect = self.rect().adjusted(10, 10, -10, -10)
        if rect.width() == 0 or rect.height() == 0:
            painter.end()
            return

        scale = min(w_rect.width() / rect.width(), w_rect.height() / rect.height())
        painter.save()
        painter.translate(w_rect.center())
        painter.scale(scale, scale)
        painter.translate(-rect.center())

        if self.show_links:
            painter.setPen(QPen(QColor(100, 100, 100, 150), 2.0 / scale))
            wire_style = ConnectionItem.wire_style
            for conn, ci in scene._conn_items:
                if ci.isVisible():
                    src_ni = scene._node_items.get(conn.src_node)
                    dst_ni = scene._node_items.get(conn.dst_node)
                    if src_ni and dst_ni:
                        sp = src_ni.port_item(conn.src_port)
                        dp = dst_ni.port_item(conn.dst_port)
                        if sp and dp:
                            s = sp.scene_center()
                            e = dp.scene_center()
                            cache_key = (conn.src_node, conn.src_port, conn.dst_node, conn.dst_port)
                            endpoints  = (s.x(), s.y(), e.x(), e.y(), wire_style)
                            if self._conn_endpoint_cache.get(cache_key) != endpoints:
                                path = QPainterPath(s)
                                if wire_style == "linear":
                                    path.lineTo(e)
                                elif wire_style == "straight":
                                    mx = s.x() + (e.x() - s.x()) * 0.5
                                    path.lineTo(mx, s.y())
                                    path.lineTo(mx, e.y())
                                    path.lineTo(e)
                                else:
                                    dx = max(abs(e.x() - s.x()) * 0.5, 60.0)
                                    path.cubicTo(s + QPointF(dx, 0), e - QPointF(dx, 0), e)
                                self._conn_path_cache[cache_key]     = path
                                self._conn_endpoint_cache[cache_key] = endpoints
                            painter.drawPath(self._conn_path_cache[cache_key])

        painter.setPen(Qt.NoPen)
        for n in nodes:
            color = QColor(n.node.color).darker(150)
            if not self.show_node_colors:
                g     = qGray(color.rgb())
                color = QColor(g, g, g)
            if self.render_error_state and (n.node.error_msg or n._has_required_error()):
                color = QColor(255, 50, 50, 200)
            painter.setBrush(color)
            painter.drawRect(n.sceneBoundingRect())

        view_rect = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        painter.setPen(QPen(QColor(MINIMAP_VIEW), 1.5 / scale))
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.drawRect(view_rect)
        painter.restore()

        self._draw_controls(painter)
        painter.end()

    def _draw_controls(self, painter: QPainter) -> None:
        painter.setPen(QColor(200, 200, 200))
        x_rect = QRectF(self.width() - 22, 8, 10, 10)
        painter.drawLine(x_rect.topLeft(), x_rect.bottomRight())
        painter.drawLine(x_rect.topRight(), x_rect.bottomLeft())

    def mousePressEvent(self, event) -> None:
        pos   = event.position()
        scene = self.view.scene()
        if scene is None:
            event.ignore()
            return

        if pos.x() > self.width() - 30 and pos.y() < 30:
            self.hide()
            self.closed.emit()
            return

        nodes = [i for i in scene.items() if isinstance(i, NodeItem)]
        valid = [n for n in nodes if not n.sceneBoundingRect().isEmpty()]
        if not valid:
            return

        rect = valid[0].sceneBoundingRect()
        for n in valid[1:]:
            nr = n.sceneBoundingRect()
            if not nr.isEmpty():
                rect = rect.united(nr)
        margin = max(rect.width(), rect.height()) * 0.15
        rect.adjust(-margin, -margin, margin, margin)
        if rect.width() == 0 or rect.height() == 0:
            return

        w_rect     = self.rect().adjusted(10, 10, -10, -10)
        scale      = min(w_rect.width() / rect.width(), w_rect.height() / rect.height())
        local_pos  = event.position() - w_rect.topLeft()
        self.view.centerOn(QPointF(
            rect.left() + local_pos.x() / scale,
            rect.top()  + local_pos.y() / scale,
        ))
        self.view.view_changed.emit()
        self.update()


# -- Notification popup --------------------------------------------------------

class NotificationPopup(QLabel):
    def __init__(self, parent: QWidget, message: str, is_error: bool = False) -> None:
        super().__init__(message, parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        bg = COLOR_INVALID if is_error else COLOR_VALID
        self.setStyleSheet(NOTIFICATION_STYLE.replace("{bg_color}", bg))

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(800)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.finished.connect(self.deleteLater)

        QTimer.singleShot(3000, self.animation.start)
        self.adjustSize()

    def position_in_parent(self) -> None:
        if self.parentWidget():
            self.move(20, 20)


# -----------------------------------------------------------------------------
#  Scene
# -----------------------------------------------------------------------------

class NodeEditorScene(QGraphicsScene):
    graph_changed = Signal()

    def __init__(self, graph: Graph) -> None:
        super().__init__()
        self.graph         = graph
        self._undo_manager = create_history_manager(self.graph)
        self.graph.on_changed.append(self.graph_changed.emit)

        self._undo_manager.set_node_registry(NODE_CLASS_MAPPINGS)
        self._undo_manager.attach(self)

        self.undo_stack = self._undo_manager.undo_stack
        self.undo_stack.setUndoLimit(1536)

        self.graph._scene_ref = weakref.ref(self)

        # Public attributes expected by core/commands.py and gui/commands.py
        self._suppress_bus: bool                                    = False
        self._node_items:   dict[str, NodeItem]                     = {}
        self._conn_items:   list[tuple[Connection, ConnectionItem]] = []
        self._dirty_nodes:  set[str]                                = set()
        self._flushing:     bool                                    = False

        # Internal drag / move state
        self._wire_drag    = WireDragState()
        self._move_tracker = SelectionMoveTracker()

        # Throttle wire-drag redraws to ~60 fps; avoids Bezier recalc on every
        # raw mouseMoveEvent which can fire at 200+ Hz on high-DPI displays.
        self._drag_timer       = QTimer(self)
        self._drag_timer.setInterval(16)
        self._drag_timer.timeout.connect(self._flush_wire_drag)
        self._pending_drag_pos: QPointF | None = None

        # Execution lock - blocks all graph-mutation interactions while True
        self._execution_locked: bool = False

        self.setSceneRect(-4000, -4000, 8000, 8000)
        self._subscribe_to_bus()

    def set_execution_lock(self, locked: bool) -> None:
        self._execution_locked = locked
        if locked:
            if self._wire_drag.active():
                self._wire_drag.clear(self)
            self._move_tracker.clear()
        self.update()

    # -- external state (used by main_window for view-state round-trips) -------

    def get_external_state(self) -> dict:
        views  = self.views()
        view   = views[0] if views else None
        window = view.window() if view else None
        if window and hasattr(window, "get_external_state"):
            return window.get_external_state()
        return {}

    def set_external_state(self, state: dict) -> None:
        views  = self.views()
        view   = views[0] if views else None
        window = view.window() if view else None
        if window and hasattr(window, "set_external_state"):
            window.set_external_state(state)

    # -- dirty / flush ---------------------------------------------------------

    def _after_node_mutation(self, node_id: str) -> None:
        self._dirty_nodes.add(node_id)
        for conn in self.graph.connections:
            if conn.src_node == node_id:
                self._dirty_nodes.add(conn.dst_node)

    def _emit_graph_changed(self) -> None:
        self._flush_updates()
        self.graph_changed.emit()

    def _flush_updates(self) -> None:
        if self._flushing or not self._dirty_nodes:
            return
        self._flushing = True
        try:
            while self._dirty_nodes:
                dirty = list(self._dirty_nodes)
                self._dirty_nodes.clear()
                for node_id in dirty:
                    node = self.graph.nodes.get(node_id)
                    item = self._node_items.get(node_id)
                    if not node or not item:
                        continue
                    if hasattr(node, "on_property_changed"):
                        node.on_property_changed()
                    if node.dynamic_input_prefix or node.dynamic_output_prefix:
                        node.sync_dynamic_ports(allow_value_extra_slot=True)
                    sig = item.layout_row_signature()
                    if sig != getattr(item, "_layout_rows", None):
                        item._layout_rows = sig
                        item.refresh_ports()
                        self.refresh_connections(item)
                    else:
                        item.refresh()
                    item.update()
        finally:
            self._flushing = False

    # -- event bus subscriptions -----------------------------------------------

    def _subscribe_to_bus(self) -> None:
        bus = self.graph.bus
        bus.subscribe(NodeAddedEvent,        self._on_node_added)
        bus.subscribe(NodeRemovedEvent,      self._on_node_removed)
        bus.subscribe(ConnectionAddedEvent,  self._on_connection_added)
        bus.subscribe(ConnectionRemovedEvent,self._on_connection_removed)
        bus.subscribe(GraphLoadedEvent,      self._on_graph_loaded)

    def _on_node_added(self, e: NodeAddedEvent) -> None:
        if self._suppress_bus or e.node_id in self._node_items:
            return
        node = self.graph.nodes.get(e.node_id)
        if node is None:
            return
        item = NodeItem(node)
        self._node_items[e.node_id] = item
        self.addItem(item)
        self._after_node_mutation(e.node_id)
        self._flush_updates()
        self.graph_changed.emit()

    def _on_node_removed(self, e: NodeRemovedEvent) -> None:
        if self._suppress_bus:
            return
        stale = [(c, ci) for c, ci in self._conn_items
                 if c.src_node == e.node_id or c.dst_node == e.node_id]
        for c, ci in stale:
            try:
                self.removeItem(ci)
            except RuntimeError:
                pass
            self._conn_items.remove((c, ci))
        item = self._node_items.pop(e.node_id, None)
        if item is not None:
            try:
                self.removeItem(item)
            except RuntimeError:
                pass
        self.graph_changed.emit()

    def _on_connection_added(self, e: ConnectionAddedEvent) -> None:
        if self._suppress_bus:
            return
        self._cleanup_ghost_connections()
        conn = self.graph.get_input_connection(e.dst_node, e.dst_port)
        if conn:
            self._materialise_conn(conn)
        self.graph_changed.emit()

    def _on_connection_removed(self, e: ConnectionRemovedEvent) -> None:
        if self._suppress_bus:
            return
        key = (e.src_node, e.src_port, e.dst_node, e.dst_port)
        for pair in list(self._conn_items):
            c, ci = pair
            if (c.src_node, c.src_port, c.dst_node, c.dst_port) == key:
                try:
                    self.removeItem(ci)
                except RuntimeError:
                    pass
                self._conn_items.remove(pair)
                # Invalidate destination node's paint cache for this port
                dst_ni = self._node_items.get(e.dst_node)
                if dst_ni and e.dst_port in dst_ni._conn_cache:
                    dst_ni._conn_cache[e.dst_port] = None
                break
        self.graph_changed.emit()

    def _on_graph_loaded(self, e: GraphLoadedEvent) -> None:
        pass

    def _cleanup_ghost_connections(self) -> None:
        live = {(c.src_node, c.src_port, c.dst_node, c.dst_port) for c in self.graph.connections}
        for pair in list(self._conn_items):
            c_obj, ci = pair
            if (c_obj.src_node, c_obj.src_port, c_obj.dst_node, c_obj.dst_port) not in live:
                try:
                    self.removeItem(ci)
                except RuntimeError:
                    pass
                self._conn_items.remove(pair)

    # -- node management -------------------------------------------------------

    def add_node(self, node, pos: QPointF | None = None) -> None:
        node.graph = self.graph
        if pos:
            node.x, node.y = pos.x(), pos.y()
        node.sync_dynamic_ports()
        add_recent_node(type(node))
        cmd = AddNodeCommand(self.graph, node, weakref.ref(self), self._undo_manager.node_registry)
        self._undo_manager._cmd_stack.push(cmd)

    def on_asset_removed(self, path: str) -> None:
        changed = False
        for node in self.graph.nodes.values():
            for pname, port in node.inputs.items():
                if port.value == path:
                    port.value = None
                    self._after_node_mutation(node.id)
                    changed = True
        if changed:
            self._emit_graph_changed()

    def on_variable_removed(self, var_name: str) -> None:
        changed = False
        for node in self.graph.nodes.values():
            for pname, port in node.inputs.items():
                if port_uses_graph_variables(port) and port.value == var_name:
                    port.value = ""
                    self._after_node_mutation(node.id)
                    changed = True
        if changed:
            self._emit_graph_changed()

    def _start_rename(self, item: NodeItem) -> None:
        if item.node.locked_title:
            return
        dialog = RenameDialog("Rename Node", item.node.display_name)
        if dialog.exec() == QDialog.Accepted:
            new_name = dialog.get_name()
            if not new_name or not new_name.strip():
                if item.node.custom_name is not None:
                    with self._undo_manager.transaction("Reset Node Name"):
                        item.node.custom_name = None
                        item.update()
                        self._emit_graph_changed()
            elif new_name != item.node.display_name:
                with self._undo_manager.transaction(f"Rename {new_name}"):
                    item.node.custom_name = new_name
                    item.update()
                    self._emit_graph_changed()

    def _convert_to_subgraph(self, items: list[NodeItem]) -> None:
        if not items:
            return

        path, _ = QFileDialog.getSaveFileName(
            None, "Save Subgraph", "", "SrcSubgraph (*.srcsubgraph)"
        )
        if not path:
            return

        selected_ids = {it.node.id for it in items}
        avg_pos = QPointF(
            sum(it.x() for it in items) / len(items),
            sum(it.y() for it in items) / len(items),
        )

        all_conns = list(self.graph.connections)
        sub_graph = Graph()
        for it in items:
            sub_graph.add_node(it.node)

        ext_to_iface: dict[tuple, SubgraphInputNode]  = {}
        int_to_iface: dict[tuple, SubgraphOutputNode] = {}
        parent_in:  list[tuple[str, str, str]] = []
        parent_out: list[tuple[str, str, str]] = []
        used_names: set[str] = set()

        def _unique(base: str) -> str:
            if base not in used_names:
                used_names.add(base)
                return base
            n = 2
            while f"{base}_{n}" in used_names:
                n += 1
            r = f"{base}_{n}"
            used_names.add(r)
            return r

        for c in all_conns:
            src_sel = c.src_node in selected_ids
            dst_sel = c.dst_node in selected_ids
            if src_sel and dst_sel:
                sub_graph.connect(c.src_node, c.src_port, c.dst_node, c.dst_port)
            elif not src_sel and dst_sel:
                key = (c.src_node, c.src_port)
                if key not in ext_to_iface:
                    iface = SubgraphInputNode()
                    pname = _unique(c.dst_port)
                    iface.inputs["port_name"].value = pname
                    iface.x = avg_pos.x() - 500.0
                    iface.y = avg_pos.y() + len(ext_to_iface) * 120.0
                    sub_graph.add_node(iface)
                    ext_to_iface[key] = iface
                    parent_in.append((pname, c.src_node, c.src_port))
                sub_graph.connect(ext_to_iface[key].id, "value", c.dst_node, c.dst_port)
            elif src_sel and not dst_sel:
                key = (c.src_node, c.src_port)
                if key not in int_to_iface:
                    iface = SubgraphOutputNode()
                    pname = _unique(c.src_port)
                    iface.inputs["port_name"].value = pname
                    iface.x = avg_pos.x() + 500.0
                    iface.y = avg_pos.y() + len(int_to_iface) * 120.0
                    sub_graph.add_node(iface)
                    int_to_iface[key] = iface
                    sub_graph.connect(c.src_node, c.src_port, iface.id, "value")
                parent_out.append((int_to_iface[key].inputs["port_name"].value, c.dst_node, c.dst_port))

        with self._undo_manager.skip_undo():
            sub_graph.save(path)
            views = self.views()
            if views:
                window = views[0].window()
                if window and hasattr(window, "panel_manager"):
                    asset_panel = window.panel_manager.get_widget("AssetDock")
                    if asset_panel:
                        existing = set(asset_panel.tree_widget.all_paths())
                        if path not in existing:
                            asset_panel.tree_widget.add_asset(path)
                            asset_panel._sync_to_graph()
                            asset_panel.refresh_status()

        with self._undo_manager.transaction("Convert to Subgraph"):
            for it in items:
                self._delete_node(it, push_undo=False)
            proxy = SubgraphNode()
            proxy.inputs["graph_path"].value = path
            proxy.on_property_changed()
            proxy.x, proxy.y = avg_pos.x(), avg_pos.y()
            self.add_node(proxy)
            for pname, ext_nid, ext_port in parent_in:
                existing = self.graph.get_input_connection(proxy.id, pname)
                self._undo_manager._cmd_stack.push(
                    ConnectCommand(self.graph, ext_nid, ext_port, proxy.id, pname,
                                   existing, weakref.ref(self))
                )
            for pname, ext_nid, ext_port in parent_out:
                existing = self.graph.get_input_connection(ext_nid, ext_port)
                self._undo_manager._cmd_stack.push(
                    ConnectCommand(self.graph, proxy.id, pname, ext_nid, ext_port,
                                   existing, weakref.ref(self))
                )
            self._flush_updates()
        self._emit_graph_changed()

    # -- clipboard wrappers (thin delegation) ---------------------------------

    def copy_selection(self) -> None:
        ClipboardManager.copy(self, [i for i in self.selectedItems() if isinstance(i, NodeItem)])

    def cut_selection(self) -> None:
        ClipboardManager.cut(self, [i for i in self.selectedItems() if isinstance(i, NodeItem)])

    def paste_from_clipboard(self, scene_pos: QPointF | None = None) -> None:
        ClipboardManager.paste(self, scene_pos)

    def duplicate_selection(self, scene_pos: QPointF | None = None) -> None:
        ClipboardManager.duplicate(
            self, [i for i in self.selectedItems() if isinstance(i, NodeItem)], scene_pos
        )

    def remove_selected(self) -> None:
        with self._undo_manager.transaction("Delete Selection"):
            selected = list(self.selectedItems())
            count = 0
            for item in selected:
                if isinstance(item, NodeItem):
                    self._delete_node(item, push_undo=False)
                    count += 1
                elif isinstance(item, ConnectionItem):
                    self._delete_conn(item, push_undo=False)
        self._emit_graph_changed()
        if count > 0:
            log.debug(f"Removed {count} nodes")

    # -- graph load / rebuild --------------------------------------------------

    def load_from_graph(self) -> None:
        with self._undo_manager.skip_undo():
            self.clear()
            self._node_items.clear()
            self._conn_items.clear()
            for node in self.graph.nodes.values():
                node.graph = self.graph
                item = NodeItem(node)
                self._node_items[node.id] = item
                self.addItem(item)
                self._dirty_nodes.add(node.id)
            for conn in self.graph.connections:
                self._materialise_conn(conn)
        self._undo_manager.clear()
        self._emit_graph_changed()

    def _rebuild_from_graph(self, selected_ids: set[str] | None = None) -> None:
        self.clear()
        self._node_items.clear()
        self._conn_items.clear()
        for node in self.graph.nodes.values():
            item = NodeItem(node)
            self._node_items[node.id] = item
            self.addItem(item)
            if selected_ids and node.id in selected_ids:
                item.setSelected(True)
            self._dirty_nodes.add(node.id)
        for conn in self.graph.connections:
            self._materialise_conn(conn)
        self._emit_graph_changed()

    # -- connection management -------------------------------------------------

    def _materialise_conn(self, conn: Connection) -> ConnectionItem | None:
        src_ni = self._node_items.get(conn.src_node)
        dst_ni = self._node_items.get(conn.dst_node)
        if not (src_ni and dst_ni):
            return None
        sp = src_ni.port_item(conn.src_port)
        dp = dst_ni.port_item(conn.dst_port)
        if not (sp and dp):
            return None
        ci = ConnectionItem(sp.scene_center(), dp.scene_center(),
                            src_port_type=sp.port.port_type)
        self._conn_items.append((conn, ci))
        self.addItem(ci)
        dst_ni.set_port_connected(conn.dst_port, True, sp.port.port_type)
        dst_ni._conn_cache[conn.dst_port] = sp.port  # keep paint cache in sync
        return ci

    def refresh_connections(self, node_item: NodeItem) -> None:
        nid = node_item.node.id
        for conn, ci in self._conn_items:
            if conn.src_node == nid or conn.dst_node == nid:
                src_ni = self._node_items.get(conn.src_node)
                dst_ni = self._node_items.get(conn.dst_node)
                if src_ni and dst_ni:
                    sp = src_ni.port_item(conn.src_port)
                    dp = dst_ni.port_item(conn.dst_port)
                    if sp and dp:
                        ci.set_src(sp.scene_center())
                        ci.set_dst(dp.scene_center())
                        ci.setVisible(True)
                    else:
                        ci.setVisible(False)

    def _try_connect(self, a: PortItem, b: PortItem) -> None:
        if a.port.is_input and not b.port.is_input:
            src, dst = b, a
        elif not a.port.is_input and b.port.is_input:
            src, dst = a, b
        else:
            return
        if not dst.port.can_connect_to(src.port):
            return
        existing = self.graph.get_input_connection(dst.port.node_id, dst.port.name)
        if existing and (existing.src_node, existing.src_port) == (src.port.node_id, src.port.name):
            return
        self._undo_manager._cmd_stack.push(
            ConnectCommand(self.graph, src.port.node_id, src.port.name,
                           dst.port.node_id, dst.port.name,
                           existing, weakref.ref(self))
        )

    def _delete_node(self, item: NodeItem, push_undo: bool = True) -> None:
        nid = item.node.id
        conn_snapshots = [c.to_dict() for c in self.graph.connections
                          if c.src_node == nid or c.dst_node == nid]
        snapshot = self.graph.nodes[nid].to_dict() if nid in self.graph.nodes else {}
        self._undo_manager._cmd_stack.push(
            RemoveNodeCommand(self.graph, nid, snapshot, conn_snapshots,
                              self._undo_manager.node_registry, weakref.ref(self))
        )

    def _delete_conn(self, ci: ConnectionItem, push_undo: bool = True) -> None:
        for pair in list(self._conn_items):
            conn, item = pair
            if item is ci:
                self._undo_manager._cmd_stack.push(
                    DisconnectCommand(self.graph, conn.src_node, conn.src_port,
                                      conn.dst_node, conn.dst_port, weakref.ref(self))
                )
                return

    # -- scene-level mouse events ----------------------------------------------

    def mousePressEvent(self, event) -> None:
        if self.graph is None:
            event.ignore()
            return
        if self._execution_locked:
            event.ignore()
            return

        if event.button() == Qt.LeftButton:
            items    = self.items(event.scenePos())
            port_hit = next((i for i in items if isinstance(i, PortItem)), None)

            if port_hit:
                wd = self._wire_drag
                if port_hit.port.is_input:
                    conn = self.graph.get_input_connection(
                        port_hit.port.node_id, port_hit.port.name)
                    if conn:
                        src_ni       = self._node_items.get(conn.src_node)
                        src_p_item   = src_ni.port_item(conn.src_port) if src_ni else None
                        ci_to_delete = next((ci for c, ci in self._conn_items if c == conn), None)
                        if ci_to_delete and src_p_item:
                            wd.moving_conn = (conn, ci_to_delete)
                            ci_to_delete.hide()
                            wd.drag_port = src_p_item
                            wd.drag_conn = ConnectionItem(
                                src_p_item.scene_center(),
                                src_port_type=src_p_item.port.port_type)
                            self.addItem(wd.drag_conn)
                            return
                wd.drag_port = port_hit
                wd.drag_conn = ConnectionItem(
                    port_hit.scene_center(), src_port_type=port_hit.port.port_type)
                self.addItem(wd.drag_conn)
                return

            if any(isinstance(i, ResizeHandle) for i in items):
                super().mousePressEvent(event)
                return

            node_hit = next((i for i in items if isinstance(i, NodeItem)), None)
            if node_hit:
                if event.modifiers() & Qt.AltModifier:
                    node_hit.setSelected(False)
                    return
                if event.modifiers() & Qt.ShiftModifier:
                    node_hit.setSelected(not node_hit.isSelected())
                    self._move_tracker.begin(self.selectedItems())
                    return
                if not node_hit.isSelected():
                    self.clearSelection()
                    node_hit.setSelected(True)
                self._move_tracker.begin(self.selectedItems())

        super().mousePressEvent(event)

    def _update_wire_hover(self, scene_pos: QPointF) -> None:
        wd = self._wire_drag
        if not wd.active():
            return
        items  = self.items(scene_pos)
        target = next(
            (i for i in items if isinstance(i, PortItem) and i is not wd.drag_port), None)
        if target != wd.hover_port:
            if wd.hover_port:
                wd.hover_port.set_highlight(False)
            wd.hover_port = target
            if wd.hover_port:
                is_valid = wd.hover_port.port.can_connect_to(wd.drag_port.port)
                wd.hover_port.set_highlight(True, is_valid)
                wd.drag_conn.set_drag_status(is_valid)
            else:
                wd.drag_conn.set_drag_status(None)

    def mouseMoveEvent(self, event) -> None:
        if self._execution_locked:
            event.ignore()
            return
        wd = self._wire_drag
        if wd.active():
            self._pending_drag_pos = event.scenePos()
            if not self._drag_timer.isActive():
                self._drag_timer.start()
            return
        super().mouseMoveEvent(event)

    def _flush_wire_drag(self) -> None:
        """Timer callback: apply the latest buffered drag position."""
        wd  = self._wire_drag
        pos = self._pending_drag_pos
        if pos is not None and wd.active():
            self._pending_drag_pos = None
            try:
                wd.drag_conn.set_dst(pos)
                self._update_wire_hover(pos)
            except RuntimeError:
                wd.drag_conn = None
        else:
            self._drag_timer.stop()

    def mouseReleaseEvent(self, event) -> None:
        if self.graph is None:
            event.ignore()
            return
        if self._execution_locked:
            event.ignore()
            return

        self._move_tracker.commit(self)
        self._drag_timer.stop()
        self._pending_drag_pos = None

        wd = self._wire_drag
        if wd.active() and wd.drag_port:
            if wd.hover_port:
                try:
                    wd.hover_port.set_highlight(False)
                except RuntimeError:
                    pass
                wd.hover_port = None

            target = next(
                (i for i in self.items(event.scenePos())
                 if isinstance(i, PortItem) and i is not wd.drag_port),
                None,
            )

            if wd.moving_conn:
                old_conn, old_ci = wd.moving_conn
                wd.moving_conn   = None

                if (target and target.port.node_id == old_conn.dst_node
                        and target.port.name == old_conn.dst_port):
                    try:
                        old_ci.show()
                        self.removeItem(wd.drag_conn)
                    except RuntimeError:
                        pass
                    wd.drag_conn = wd.drag_port = None
                    return

                if target:
                    with self._undo_manager.transaction("Move Connection"):
                        self._delete_conn(old_ci)
                        self._try_connect(wd.drag_port, target)
                    try:
                        self.removeItem(wd.drag_conn)
                    except RuntimeError:
                        pass
                    wd.drag_conn = wd.drag_port = None
                    return
                else:
                    self._delete_conn(old_ci)

            if target:
                self._try_connect(wd.drag_port, target)
            else:
                dlg = NodeSearchDialog(None, wd.drag_port.port)
                dlg.setStyleSheet(MENU)
                dlg.move(QCursor.pos())
                if dlg.exec() and dlg.selected_class:
                    with self._undo_manager.transaction(f"Add {dlg.selected_class.__name__}"):
                        new_node = dlg.selected_class()
                        self.add_node(new_node, event.scenePos())
                        new_item = self._node_items.get(new_node.id)
                        self.clearSelection()
                        if new_item:
                            new_item.setSelected(True)
                        src_p = wd.drag_port.port
                        if not src_p.is_input:
                            for p_name, p_obj in new_node.inputs.items():
                                if p_obj.can_connect_to(src_p):
                                    dst_p_item = new_item.port_item(p_name) if new_item else None
                                    if dst_p_item:
                                        self._try_connect(wd.drag_port, dst_p_item)
                                    break
                        else:
                            for p_name, p_obj in new_node.outputs.items():
                                if src_p.can_connect_to(p_obj):
                                    src_p_item = new_item.port_item(p_name) if new_item else None
                                    if src_p_item:
                                        self._try_connect(src_p_item, wd.drag_port)
                                    break

            try:
                self.removeItem(wd.drag_conn)
            except RuntimeError:
                pass
            wd.drag_conn = wd.drag_port = None
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self._execution_locked:
            return
        if event.key() == Qt.Key_Delete:
            self.remove_selected()
        elif event.key() == Qt.Key_Escape:
            if self._wire_drag.active():
                self._wire_drag.clear(self)
            else:
                self.clearSelection()
            return
        elif event.key() == Qt.Key_F2:
            selected = [i for i in self.selectedItems() if isinstance(i, NodeItem)]
            if selected and not selected[0].node.locked_title:
                self._start_rename(selected[0])
        super().keyPressEvent(event)


# -----------------------------------------------------------------------------
#  View
# -----------------------------------------------------------------------------

class NodeEditorView(SafeGraphicsView):
    compile_requested  = Signal()
    subgraph_requested = Signal(str)
    view_changed       = Signal()

    def __init__(self, scene: NodeEditorScene) -> None:
        super().__init__(scene)

        gl_widget = QOpenGLWidget()
        fmt = QSurfaceFormat.defaultFormat()
        fmt.setSamples(4)
        gl_widget.setFormat(fmt)
        self.setViewport(gl_widget)

        self.setRenderHints(
            QPainter.Antialiasing |
            QPainter.SmoothPixmapTransform |
            QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setOptimizationFlags(
            QGraphicsView.DontAdjustForAntialiasing |
            QGraphicsView.DontSavePainterState)
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(BG_DARKER)))
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)

        self._panning    = False
        self._pan_start  = QPoint()
        self._notification: NotificationPopup | None = None

        self.allow_zoom  = True
        self.allow_pan   = True
        self.show_grid   = True
        self._bg_color   = QColor(BG_DARKER)

        # Pluggable background renderer
        self._bg_renderer: BackgroundRenderer = GridBackgroundRenderer()

        # Rubber-band mode tracking
        self._rb_mode:          RubberBandMode = RubberBandMode.REPLACE
        self._rb_pre_selection: set            = set()
        self._rb_press_pos:     QPoint         = QPoint()

        # Keyboard shortcut registry
        self._shortcuts = ShortcutRegistry()
        self._register_shortcuts()

    def set_background_renderer(self, renderer: BackgroundRenderer) -> None:
        """Hot-swap the background renderer at runtime."""
        self._bg_renderer.cleanup()
        self._bg_renderer = renderer
        self.viewport().update()

    # -- shortcuts -------------------------------------------------------------

    def _register_shortcuts(self) -> None:
        reg = self._shortcuts
        NO_MOD  = Qt.NoModifier
        SHIFT   = Qt.ShiftModifier
        CTRL    = Qt.ControlModifier
        CTRL_SH = Qt.ControlModifier | Qt.ShiftModifier

        # Node search
        reg.register(Qt.Key_A,      SHIFT,   self._open_node_search,    "Node search")
        reg.register(Qt.Key_Tab,    NO_MOD,  self._open_node_search,    "Node search")

        # Navigation
        reg.register(Qt.Key_F,      NO_MOD,  self._frame_selection,     "Frame selection")
        reg.register(Qt.Key_Home,   NO_MOD,  self._frame_all,           "Frame all")

        # Node operations
        reg.register(Qt.Key_H,      NO_MOD,  self._toggle_fold,         "Toggle fold")
        reg.register(Qt.Key_G,      CTRL,    self._convert_to_subgraph, "Convert to subgraph")

        # Clipboard
        reg.register(Qt.Key_C,      CTRL,    lambda: self.scene().copy_selection(),              "Copy")
        reg.register(Qt.Key_X,      CTRL,    lambda: self.scene().cut_selection(),               "Cut")
        reg.register(Qt.Key_V,      CTRL,    lambda: self.scene().paste_from_clipboard(
                                                 self._mouse_scene_pos()),                       "Paste")
        reg.register(Qt.Key_D,      SHIFT,   lambda: self.scene().duplicate_selection(
                                                 self._mouse_scene_pos()),                       "Duplicate")

        # Property clipboard
        reg.register(Qt.Key_C,      CTRL_SH, self._copy_properties,     "Copy properties")
        reg.register(Qt.Key_V,      CTRL_SH, self._paste_properties,    "Paste properties")

        # Selection
        reg.register(Qt.Key_A,      CTRL,    self._select_all,          "Select all")

        # Compile
        reg.register(Qt.Key_F5,     NO_MOD,  self.compile_requested.emit, "Compile")

    def _open_node_search(self) -> None:
        pos = QCursor.pos()
        dlg = NodeSearchDialog(None)
        dlg.setStyleSheet(MENU)
        dlg.move(pos)
        if dlg.exec() and dlg.selected_class:
            new_node = dlg.selected_class()
            self.scene().add_node(new_node, self.mapToScene(self.mapFromGlobal(pos)))
            self.scene().clearSelection()
            item = self.scene()._node_items.get(new_node.id)
            if item:
                item.setSelected(True)

    def _frame_selection(self) -> None:
        selected = [i for i in self.scene().selectedItems() if isinstance(i, NodeItem)]
        if not selected:
            self._frame_all()
            return
        rect = selected[0].sceneBoundingRect()
        for item in selected[1:]:
            rect = rect.united(item.sceneBoundingRect())
        rect = rect.adjusted(-60, -60, 60, 60)
        self.fitInView(rect, Qt.KeepAspectRatio)
        self.view_changed.emit()

    def _frame_all(self) -> None:
        nodes = [i for i in self.scene().items() if isinstance(i, NodeItem)]
        if not nodes:
            return
        rect = nodes[0].sceneBoundingRect()
        for n in nodes[1:]:
            rect = rect.united(n.sceneBoundingRect())
        rect = rect.adjusted(-80, -80, 80, 80)
        self.fitInView(rect, Qt.KeepAspectRatio)
        self.view_changed.emit()

    def _toggle_fold(self) -> None:
        selected = [i for i in self.scene().selectedItems() if isinstance(i, NodeItem)]
        if not selected:
            return
        any_unfolded = any(not n.node.folded for n in selected)
        with self.scene()._undo_manager.transaction("Toggle Fold"):
            for item in selected:
                if item.node.folded != any_unfolded:
                    self.scene()._undo_manager.push(
                        FoldCommand(item, item.node.folded, any_unfolded)
                    )

    def _convert_to_subgraph(self) -> None:
        targets = [i for i in self.scene().selectedItems() if isinstance(i, NodeItem)]
        if targets:
            self.scene()._convert_to_subgraph(targets)

    def _copy_properties(self) -> None:
        selected = [i for i in self.scene().selectedItems() if isinstance(i, NodeItem)]
        if selected:
            ClipboardManager.copy_properties(selected[0])

    def _paste_properties(self) -> None:
        selected = [i for i in self.scene().selectedItems() if isinstance(i, NodeItem)]
        if selected and ClipboardManager._property_data:
            ClipboardManager.paste_properties(self.scene(), selected[0])
        else:
            ClipboardManager.try_paste_from_os_clipboard(
                self.scene(), self._mouse_scene_pos())

    def _select_all(self) -> None:
        for item in self.scene().items():
            if isinstance(item, NodeItem):
                item.setSelected(True)

    def _mouse_scene_pos(self) -> QPointF:
        local = self.viewport().mapFromGlobal(QCursor.pos())
        if self.viewport().rect().contains(local):
            return self.mapToScene(local)
        return self.mapToScene(self.viewport().rect().center())

    # -- background ------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        if not self.show_grid:
            painter.fillRect(rect, self._bg_color)
            return
        zoom   = self.transform().m11()
        vp     = self.viewport().size()
        origin = self.mapToScene(QPoint(0, 0))
        self._bg_renderer.render(painter, rect, zoom, vp, QPointF(origin))

    # -- notification ----------------------------------------------------------

    def show_notification(self, message: str, is_error: bool = False) -> None:
        try:
            if self._notification:
                self._notification.deleteLater()
        except RuntimeError:
            pass
        self._notification = NotificationPopup(self.viewport(), message, is_error)
        self._notification.position_in_parent()
        self._notification.show()

    def _position_notification(self) -> None:
        try:
            if self._notification and self._notification.isVisible():
                self._notification.position_in_parent()
        except RuntimeError:
            self._notification = None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._position_notification)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)

    # -- drag-drop -------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        if getattr(self.scene(), "_execution_locked", False):
            event.ignore()
            return
        text      = event.mimeData().text()
        scene_pos = self.mapToScene(event.position().toPoint())
        items_to_process = []

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                if data.get("type") == "assets":
                    for p in data.get("paths", []):
                        items_to_process.append(("asset", p))
                elif data.get("type") == "variables":
                    for n in data.get("names", []):
                        items_to_process.append(("variable", n))
        except (json.JSONDecodeError, TypeError):
            if text.startswith("variable:"):
                items_to_process.append(("variable", text.split(":", 1)[1]))
            else:
                items_to_process.append(("asset", text))

        if not items_to_process:
            return

        with self.scene()._undo_manager.transaction("Drop Items"):
            self.scene().clearSelection()
            current_pos = QPointF(scene_pos)
            for kind, value in items_to_process:
                from core.registry import dispatch
                dispatch(kind, self.scene(), current_pos, value, event.modifiers())
                current_pos += QPointF(0, 120)

        event.acceptProposedAction()

    # -- zoom / pan ------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self.allow_zoom:
            return
        f = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        self.scale(f, f)
        self.view_changed.emit()

    # -- mouse -----------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events():
            event.ignore()
            return

        if event.button() == Qt.MiddleButton and self.allow_pan:
            self._panning   = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        sc = self.scene()
        if sc and getattr(sc, "_execution_locked", False):
            event.ignore()
            return

        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item:
                self.setDragMode(QGraphicsView.NoDrag)
                self._rb_mode = RubberBandMode.REPLACE
            else:
                self.setDragMode(QGraphicsView.RubberBandDrag)
                self._rb_press_pos = event.pos()
                mods = event.modifiers()
                if mods & Qt.ShiftModifier:
                    self._rb_mode         = RubberBandMode.ADD
                    self._rb_pre_selection = set(self.scene().selectedItems())
                elif mods & Qt.ControlModifier:
                    self._rb_mode         = RubberBandMode.SUBTRACT
                    self._rb_pre_selection = set(self.scene().selectedItems())
                else:
                    self._rb_mode         = RubberBandMode.REPLACE
                    self._rb_pre_selection = set()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events():
            return
        if self._panning:
            d               = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events():
            return

        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            return

        if event.button() == Qt.LeftButton and self._rb_mode != RubberBandMode.REPLACE:
            # Compute items inside the rubber band geometrically BEFORE super() applies
            # Qt's Ctrl-ToggleSelection, which would corrupt selectedItems().
            vp_rect    = QRect(self._rb_press_pos, event.pos()).normalized()
            scene_rect = self.mapToScene(vp_rect).boundingRect()
            rb_items   = {
                i for i in self.scene().items(scene_rect, Qt.IntersectsItemShape)
                if isinstance(i, NodeItem)
            }
            super().mouseReleaseEvent(event)
            if self._rb_mode == RubberBandMode.ADD:
                final = self._rb_pre_selection | rb_items
            else:  # SUBTRACT
                final = self._rb_pre_selection - rb_items
            self.scene().clearSelection()
            for item in final:
                item.setSelected(True)
            self._rb_mode          = RubberBandMode.REPLACE
            self._rb_pre_selection = set()
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events():
            event.ignore()
            return
        if getattr(self.scene(), "_execution_locked", False):
            event.ignore()
            return

        item = self.itemAt(event.pos())
        if isinstance(item, NodeItem) and isinstance(item.node, SubgraphNode):
            path = item.node.inputs.get("graph_path").value
            if path:
                if not os.path.isabs(path) and self.scene().graph.project_dir:
                    path = os.path.abspath(
                        os.path.join(self.scene().graph.project_dir, path))
                self.subgraph_requested.emit(path)
                return
        elif item is None:
            self._open_node_search()
            return
        super().mouseDoubleClickEvent(event)

    # -- keyboard --------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self.is_ready_for_events():
            return
        if getattr(self.scene(), "_execution_locked", False):
            return

        focus_widget  = QApplication.focusWidget()
        scene_focused = self.scene().focusItem() is not None
        is_editing    = (focus_widget is not None and focus_widget is not self) or scene_focused

        if is_editing:
            self.scene().clearSelection()
            if event.key() == Qt.Key_F5:
                self.compile_requested.emit()
                return
            super().keyPressEvent(event)
            return

        if self._shortcuts.handle(event):
            return
        super().keyPressEvent(event)

    # -- context menu ----------------------------------------------------------

    def contextMenuEvent(self, event) -> None:
        if getattr(self.scene(), "_execution_locked", False):
            return
        item = self.itemAt(event.pos())
        if isinstance(item, PortItem):
            if item.port.is_input:
                ContextMenuFactory.exec_port_menu(
                    self.scene(), self, item, event.globalPos())
            return
        if isinstance(item, NodeItem):
            ContextMenuFactory.exec_node_menu(
                self.scene(), self, item, event.globalPos())
            return
        ContextMenuFactory.exec_background_menu(
            self.scene(), self,
            self.mapToScene(event.pos()), event.globalPos())

    # -- view state persistence ------------------------------------------------

    def get_view_state(self) -> dict:
        t       = self.transform()
        h_scroll = self.horizontalScrollBar()
        v_scroll = self.verticalScrollBar()
        return {
            "zoom":          t.m11(),
            "scroll_x":      h_scroll.value(),
            "scroll_y":      v_scroll.value(),
            "scroll_max_x":  h_scroll.maximum(),
            "scroll_max_y":  v_scroll.maximum(),
            "transform_m11": t.m11(),
            "transform_m12": t.m12(),
            "transform_m21": t.m21(),
            "transform_m22": t.m22(),
            "transform_dx":  t.dx(),
            "transform_dy":  t.dy(),
        }

    def set_view_state(self, state: dict) -> None:
        if not state:
            return
        if "transform_m11" in state:
            self.setTransform(QTransform(
                state["transform_m11"], state["transform_m12"],
                state["transform_m21"], state["transform_m22"],
                state["transform_dx"],  state["transform_dy"],
            ))
        else:
            zoom = state.get("zoom", 1.0)
            self.resetTransform()
            self.scale(zoom, zoom)

        if "scroll_x" in state and "scroll_y" in state:
            def _restore():
                self.horizontalScrollBar().setValue(state["scroll_x"])
                self.verticalScrollBar().setValue(state["scroll_y"])
            QTimer.singleShot(50, _restore)
