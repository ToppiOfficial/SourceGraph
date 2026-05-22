"""NodeEditorScene - QGraphicsScene that renders and manages a Graph.

Handles node/connection CRUD, wire-drag interactions, undo/redo, and
communicates graph changes via the graph_changed signal.
"""
from __future__ import annotations

import weakref
from typing import TYPE_CHECKING

from PySide6.QtWidgets import QGraphicsScene, QFileDialog, QDialog
from PySide6.QtGui import QKeyEvent
from PySide6.QtCore import Qt, QPointF, Signal, QTimer

from sourcegraph.sys.graph import Graph, Connection
from sourcegraph.sys.node import port_uses_graph_variables
from sourcegraph.sys.history import create_history_manager, HistoryManager
from sourcegraph.sys.events import (
    NodeAddedEvent, NodeRemovedEvent,
    ConnectionAddedEvent, ConnectionRemovedEvent,
    GraphLoadedEvent,
)
from sourcegraph.sys.history import (
    AddNodeCommand, RemoveNodeCommand, ConnectCommand,
    DisconnectCommand,
)
from sourcegraph.sys.recent_nodes import add_recent_node
from sourcegraph.sys.registry import NODE_CLASS_MAPPINGS

from sourcegraph.nodes.subgraph.subgraph import SubgraphNode, SubgraphInputNode, SubgraphOutputNode

from sourcegraph.gui.items.node import NodeItem, ResizeHandle, PortItem
from sourcegraph.gui.items.wire import ConnectionItem
from sourcegraph.gui.commands import PropertyCommand, FoldCommand, ResizeNodeCommand
from sourcegraph.gui.dialogs import RenameDialog
from sourcegraph.gui.theme import MENU
from sourcegraph.gui.logger import log
from sourcegraph.gui.menu.node_search_dialog import NodeSearchDialog
from sourcegraph.gui.node_editor.state import WireDragState, SelectionMoveTracker, ClipboardManager


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

    # -- clipboard wrappers (thin delegation to ClipboardManager) --------------

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
        dst_ni._conn_cache[conn.dst_port] = sp.port
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
                from PySide6.QtGui import QCursor
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
