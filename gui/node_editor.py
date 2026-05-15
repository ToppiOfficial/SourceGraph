from __future__ import annotations
import os
import math
import json
import weakref
import numpy as np
import uuid

from PySide6.QtWidgets import (QGraphicsScene, QGraphicsView, QMenu,
                                QWidget, QPushButton, QFileDialog, QLabel,
                                QGraphicsOpacityEffect, QDialog)
from PySide6.QtGui     import (QColor, QPainter, QBrush, QPen, QKeySequence,
                                QKeyEvent, QWheelEvent, QMouseEvent, QCursor,
                                QUndoCommand, QUndoStack, QDragEnterEvent, QDropEvent, qGray,
                                QDragMoveEvent, QAction, QFont, QPixmap,
                                QSurfaceFormat, QPainterPath)
from PySide6.QtCore    import Qt, QPointF, QPoint, Signal, QRectF, QTimer, QPropertyAnimation, QLineF
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from core.graph import Graph, Connection
from core.node import PortType, port_uses_graph_variables
from core.history import create_history_manager, HistoryManager
from core.events import (
    NodeAddedEvent, NodeRemovedEvent,
    ConnectionAddedEvent, ConnectionRemovedEvent,
    GraphLoadedEvent,
)
from core.commands import (
    AddNodeCommand, RemoveNodeCommand, ConnectCommand,
    DisconnectCommand, MoveNodesCommand,
)
from core.recent_nodes import add_recent_node
from gui.widgets.icon_provider import load_pixmap
from gui.widgets.safe_graphics_view import SafeGraphicsView
from nodes import NODE_CLASS_MAPPINGS, NODE_CATEGORIES
from nodes.subgraph.subgraph import SubgraphNode, SubgraphInputNode, SubgraphOutputNode
from gui.items.node       import NodeItem, ResizeHandle, PortItem, DEFAULT_W
from gui.items.wire import ConnectionItem
from gui.dialogs import RenameDialog
from gui.theme import *
from gui.logger import log
from gui.widgets.basic_shapes import ShapeDrawer
from gui.menu.node_search_dialog import NodeSearchDialog


class MinimapWidget(QWidget):
    closed = Signal()

    def __init__(self, view: NodeEditorView, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self.show_node_colors = True
        self.show_links = True
        self.render_error_state = True

        self.view = view
        self.setMouseTracking(True)
        self.setMinimumSize(100, 80)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg_color = QColor(0, 0, 0, 80)
        painter.setBrush(bg_color)
        painter.setPen(QPen(QColor(bg_color), 1))
        painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

        scene = self.view.scene()
        if scene is None:
            self._draw_overlay_controls(painter)
            painter.end()
            return

        try: nodes = [i for i in scene.items() if isinstance(i, NodeItem)]
        except RuntimeError:
            self._draw_overlay_controls(painter)
            painter.end()
            return

        # without this, subgraph editing will result in a fatal error
        if not nodes:
            self._draw_overlay_controls(painter)
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
            
        scale  = min(w_rect.width() / rect.width(), w_rect.height() / rect.height())
        
        painter.save()
        painter.translate(w_rect.center())
        painter.scale(scale, scale)
        painter.translate(-rect.center())

        if self.show_links:
            painter.setPen(QPen(QColor(100, 100, 100, 150), 2.0 / scale))
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
                            
                            path = QPainterPath(s)
                            if ConnectionItem.wire_style == "linear":
                                path.lineTo(e)
                            elif ConnectionItem.wire_style == "straight":
                                mid_x = s.x() + (e.x() - s.x()) * 0.5
                                path.lineTo(mid_x, s.y())
                                path.lineTo(mid_x, e.y())
                                path.lineTo(e)
                            else:
                                dx = max(abs(e.x() - s.x()) * 0.5, 60.0)
                                path.cubicTo(s + QPointF(dx, 0), e - QPointF(dx, 0), e)
                            
                            painter.drawPath(path)

        # Draw Nodes
        painter.setPen(Qt.NoPen)
        for n in nodes:
            color = QColor(n.node.color).darker(150)
            
            # Apply Grayscale if node colors are off
            if not self.show_node_colors:
                gray = qGray(color.rgb())
                color = QColor(gray, gray, gray)
            
            # Apply Error Tint
            if self.render_error_state and (n.node.error_msg or n._has_required_error()):
                color = QColor(255, 50, 50, 200)
                
            painter.setBrush(color)
            painter.drawRect(n.sceneBoundingRect())

        view_rect = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        painter.setPen(QPen(QColor(MINIMAP_VIEW), 1.5 / scale))
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.drawRect(view_rect)
        painter.restore()

        # Draw Overlay Controls (Settings/Close)
        self._draw_overlay_controls(painter)

        painter.end()

    def _draw_overlay_controls(self, painter):
        """Draw the close 'X'."""
        # Close icon (top right)
        painter.setPen(QColor(200, 200, 200))
        x_rect = QRectF(self.width() - 22, 8, 10, 10)
        painter.drawLine(x_rect.topLeft(), x_rect.bottomRight())
        painter.drawLine(x_rect.topRight(), x_rect.bottomLeft())

    def mousePressEvent(self, event) -> None:
        pos = event.position()
        
        scene = self.view.scene()
        
        if scene is None: # Guard against scene being None during transitions
            event.ignore()
            return

        # Check Close Button (top right) - moved after scene check
        if pos.x() > self.width() - 30 and pos.y() < 30:
            self.hide()
            self.closed.emit()
            return
        
        nodes = [i for i in scene.items() if isinstance(i, NodeItem)]
        if not nodes:
            return
        
        # Filter out nodes that don't have valid geometry yet
        valid_nodes = [n for n in nodes if not n.sceneBoundingRect().isEmpty()]
        if not valid_nodes:
            return
            
        rect = valid_nodes[0].sceneBoundingRect()
        for n in valid_nodes[1:]:
            nr = n.sceneBoundingRect()
            if not nr.isEmpty():
                rect = rect.united(nr)
                
        margin = max(rect.width(), rect.height()) * 0.15
        rect.adjust(-margin, -margin, margin, margin)
        
        if rect.width() == 0 or rect.height() == 0:
            return

        w_rect     = self.rect().adjusted(10, 10, -10, -10)
        scale      = min(w_rect.width() / rect.width(), w_rect.height() / rect.height())
        local_click = event.position() - w_rect.topLeft()
        self.view.centerOn(QPointF(
            rect.left() + local_click.x() / scale,
            rect.top()  + local_click.y() / scale,
        ))
        self.view.view_changed.emit()
        self.update()

class NotificationPopup(QLabel):
    """A self-fading notification overlay for the editor."""
    def __init__(self, parent: QWidget, message: str, is_error: bool = False):
        super().__init__(message, parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        
        bg_color = COLOR_INVALID if is_error else COLOR_VALID
        self.setStyleSheet(NOTIFICATION_STYLE.replace("{bg_color}", bg_color))
        
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        
        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(800)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.finished.connect(self.deleteLater)
        
        QTimer.singleShot(3000, self.animation.start)
        
        self.adjustSize()

    def position_in_parent(self):
        if not self.parentWidget(): return
        parent_rect = self.parentWidget().rect()
        x = 20
        y = 20
        self.move(x, y)


#  Scene 

class NodeEditorScene(QGraphicsScene):
    graph_changed = Signal()

    _clipboard: dict | None = None

    def __init__(self, graph: Graph) -> None:
        super().__init__()
        self.graph = graph
        self._undo_manager = create_history_manager(self.graph)
        self.graph.on_changed.append(self.graph_changed.emit)

        self._undo_manager.set_node_registry(NODE_CLASS_MAPPINGS)

        # Wire auto-capture: from this point every graph_changed emission is
        # tracked automatically — no per-panel or per-node boilerplate needed.
        self._undo_manager.attach(self)

        self.undo_stack = self._undo_manager.undo_stack
        self.undo_stack.setUndoLimit(1536)

        self.graph._scene_ref = weakref.ref(self)

        self._suppress_bus: bool                                      = False
        self._drag_start_states: dict                                 = {}
        self._node_items:  dict[str, NodeItem]                        = {}
        self._conn_items:  list[tuple[Connection, ConnectionItem]]    = []
        self._drag_conn:   ConnectionItem | None                      = None
        self._drag_port:   PortItem       | None                      = None
        self._hover_port:  PortItem       | None                      = None
        self._dirty_nodes: set[str]                                   = set()
        self._moving_conn: tuple[Connection, ConnectionItem] | None   = None
        self._flushing:    bool                                       = False
        self.setSceneRect(-4000, -4000, 8000, 8000)

        self._subscribe_to_bus()

    #  node management 

    def get_external_state(self) -> dict:
        views = self.views()
        view = views[0] if views else None
        window = view.window() if view else None
        if window and hasattr(window, "get_external_state"):
            return window.get_external_state()
        return {}

    def set_external_state(self, state: dict) -> None:
        views = self.views()
        view = views[0] if views else None
        window = view.window() if view else None
        if window and hasattr(window, "set_external_state"):
            window.set_external_state(state)

    def _after_node_mutation(self, node_id: str) -> None:
        self._dirty_nodes.add(node_id)
        for conn in self.graph.connections:
            if conn.src_node == node_id:
                self._dirty_nodes.add(conn.dst_node)

    def _emit_graph_changed(self) -> None:
        """Emit graph_changed signal after flushing visual updates."""
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
                        node.sync_dynamic_ports()
                        
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

    def _subscribe_to_bus(self) -> None:
        bus = self.graph.bus
        bus.subscribe(NodeAddedEvent, self._on_node_added)
        bus.subscribe(NodeRemovedEvent, self._on_node_removed)
        bus.subscribe(ConnectionAddedEvent, self._on_connection_added)
        bus.subscribe(ConnectionRemovedEvent, self._on_connection_removed)
        bus.subscribe(GraphLoadedEvent, self._on_graph_loaded)

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
                break
        self.graph_changed.emit()

    def _on_graph_loaded(self, e: GraphLoadedEvent) -> None:
        # load_from_graph() handles visual rebuild explicitly; no action needed here.
        pass

    def _cleanup_ghost_connections(self) -> None:
        """Remove visual connection items whose backing Connection is no longer live."""
        live_keys = {(c.src_node, c.src_port, c.dst_node, c.dst_port)
                     for c in self.graph.connections}
        for pair in list(self._conn_items):
            c_obj, ci = pair
            if (c_obj.src_node, c_obj.src_port, c_obj.dst_node, c_obj.dst_port) not in live_keys:
                try:
                    self.removeItem(ci)
                except RuntimeError:
                    pass
                self._conn_items.remove(pair)

    def add_node(self, node, pos: QPointF | None = None) -> None:
        node.graph = self.graph
        if pos:
            node.x, node.y = pos.x(), pos.y()
        node.sync_dynamic_ports()
        add_recent_node(type(node))
        cmd = AddNodeCommand(self.graph, node, weakref.ref(self), self._undo_manager.node_registry)
        self._undo_manager._cmd_stack.push(cmd)

    def on_asset_removed(self, path: str) -> None:
        """Clear any node ports referencing the removed asset and refresh."""
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
        """Clear any node ports referencing the removed variable and refresh."""
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
            # If empty or whitespace, clear custom name to revert to default
            if not new_name or not new_name.strip():
                if item.node.custom_name is not None:
                    with self._undo_manager.transaction("Reset Node Name"):
                        item.node.custom_name = None
                        item.update()
                        self._emit_graph_changed()
            # If different from current display name, set custom name
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
                    iface.y = avg_pos.y() + (len(ext_to_iface) * 120.0)
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
                    iface.y = avg_pos.y() + (len(int_to_iface) * 120.0)
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
            self.add_node(proxy)  # pushes AddNodeCommand → _on_node_added creates item

            for pname, ext_nid, ext_port in parent_in:
                existing = self.graph.get_input_connection(proxy.id, pname)
                cmd = ConnectCommand(
                    self.graph, ext_nid, ext_port, proxy.id, pname,
                    existing, weakref.ref(self)
                )
                self._undo_manager._cmd_stack.push(cmd)

            for pname, ext_nid, ext_port in parent_out:
                existing = self.graph.get_input_connection(ext_nid, ext_port)
                cmd = ConnectCommand(
                    self.graph, proxy.id, pname, ext_nid, ext_port,
                    existing, weakref.ref(self)
                )
                self._undo_manager._cmd_stack.push(cmd)

            self._flush_updates()

        self._emit_graph_changed()
        log.debug(f"Converted {len(items)} nodes to subgraph: {path}")

    def copy_selection(self) -> None:
        selected = [i for i in self.selectedItems() if isinstance(i, NodeItem)]
        if not selected: return
        node_ids = {n.node.id for n in selected}
        data = {
            "nodes": [n.node.to_dict() for n in selected],
            "connections": []
        }
        for c in self.graph.connections:
            if c.src_node in node_ids and c.dst_node in node_ids:
                data["connections"].append({
                    "src_node": c.src_node, "src_port": c.src_port,
                    "dst_node": c.dst_node, "dst_port": c.dst_port
                })
        NodeEditorScene._clipboard = data

    def cut_selection(self) -> None:
        selected = [i for i in self.selectedItems() if isinstance(i, NodeItem)]
        if not selected: return
        with self._undo_manager.transaction("Cut Selection"):
            self.copy_selection()
            node_count = 0
            for item in list(selected):
                if isinstance(item, NodeItem):
                    self._delete_node(item, push_undo=False)
                    node_count += 1
            if node_count > 0:
                log.debug(f"Cut {node_count} nodes")
            self._emit_graph_changed()

    def paste_from_clipboard(self, scene_pos: QPointF | None = None) -> None:
        if not NodeEditorScene._clipboard:
            return
        nodes_data = NodeEditorScene._clipboard.get("nodes", [])
        if not nodes_data:
            return

        if scene_pos is not None:
            min_x = min(n["x"] for n in nodes_data)
            min_y = min(n["y"] for n in nodes_data)
            offset = scene_pos - QPointF(min_x, min_y)
        else:
            offset = QPointF(32, 32)
            
        if NodeEditorScene._clipboard:
            self._suppress_bus = True
            try:
                with self._undo_manager.transaction("Paste Nodes"):
                    id_map = {}
                    nodes_to_paste = []

                    for n_dict in NodeEditorScene._clipboard.get("nodes", []):
                        cls = NODE_CLASS_MAPPINGS.get(n_dict["type"])
                        if not cls: continue
                        new_dict = n_dict.copy()
                        old_id = new_dict["id"]
                        new_id = str(uuid.uuid4())
                        id_map[old_id] = new_id
                        new_dict["id"] = new_id
                        new_dict["x"] += offset.x()
                        new_dict["y"] += offset.y()
                        node = cls.from_dict(new_dict)
                        node.graph = self.graph
                        nodes_to_paste.append(node)

                    self.clearSelection()
                    for node in nodes_to_paste:
                        self.graph.add_node(node)
                        item = NodeItem(node)
                        self._node_items[node.id] = item
                        self.addItem(item)
                        item.setSelected(True)
                        self._after_node_mutation(node.id)

                    for c_dict in NodeEditorScene._clipboard.get("connections", []):
                        sn, dn = id_map.get(c_dict["src_node"]), id_map.get(c_dict["dst_node"])
                        if sn and dn:
                            self.graph.connect(sn, c_dict["src_port"], dn, c_dict["dst_port"])
                            conn = self.graph.get_input_connection(dn, c_dict["dst_port"])
                            if conn:
                                self._materialise_conn(conn)
            finally:
                self._suppress_bus = False

            # Force immediate visual update for dynamic ports after paste
            self._flush_updates()

    def duplicate_selection(self, scene_pos: QPointF | None = None) -> None:
        prev_clip = NodeEditorScene._clipboard
        self.copy_selection()
        if NodeEditorScene._clipboard:
            self.paste_from_clipboard(scene_pos=scene_pos)
        NodeEditorScene._clipboard = prev_clip

    def remove_selected(self) -> None:
        with self._undo_manager.transaction("Delete Selection"):
            selected = list(self.selectedItems())
            node_count = 0
            for item in selected:
                if isinstance(item, NodeItem):
                    self._delete_node(item, push_undo=False)
                    node_count += 1
                elif isinstance(item, ConnectionItem):
                    self._delete_conn(item, push_undo=False)
        self._emit_graph_changed()
        if node_count > 0: log.debug(f"Removed {node_count} nodes")

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

    #  connection management 

    def _materialise_conn(self, conn: Connection) -> ConnectionItem | None:
        src_ni = self._node_items.get(conn.src_node)
        dst_ni = self._node_items.get(conn.dst_node)
        if not (src_ni and dst_ni):
            return None
        sp = src_ni.port_item(conn.src_port)
        dp = dst_ni.port_item(conn.dst_port)
        if not (sp and dp):
            return None
        ci = ConnectionItem(sp.scene_center(), dp.scene_center())
        self._conn_items.append((conn, ci))
        self.addItem(ci)
        dst_ni.set_port_connected(conn.dst_port, True, sp.port.port_type)
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

        cmd = ConnectCommand(
            self.graph, src.port.node_id, src.port.name,
            dst.port.node_id, dst.port.name,
            existing, weakref.ref(self)
        )
        self._undo_manager._cmd_stack.push(cmd)

    def _delete_node(self, item: NodeItem, push_undo: bool = True) -> None:
        nid = item.node.id
        conn_snapshots = [c.to_dict() for c in self.graph.connections
                          if c.src_node == nid or c.dst_node == nid]
        snapshot = self.graph.nodes[nid].to_dict() if nid in self.graph.nodes else {}
        cmd = RemoveNodeCommand(
            self.graph, nid, snapshot, conn_snapshots,
            self._undo_manager.node_registry, weakref.ref(self)
        )
        self._undo_manager._cmd_stack.push(cmd)

    def _delete_conn(self, ci: ConnectionItem, push_undo: bool = True) -> None:
        for pair in list(self._conn_items):
            conn, item = pair
            if item is ci:
                cmd = DisconnectCommand(
                    self.graph, conn.src_node, conn.src_port,
                    conn.dst_node, conn.dst_port, weakref.ref(self)
                )
                self._undo_manager._cmd_stack.push(cmd)
                return
    
    #  mouse events (scene-level) 

    def mousePressEvent(self, event) -> None:
        # Scene-level guard: if graph is None, the scene is a zombie or in teardown
        if self.graph is None:
            event.ignore()
            return

        if event.button() == Qt.LeftButton:
            items = self.items(event.scenePos())
            port_item = next((i for i in items if isinstance(i, PortItem)), None)
            if port_item:
                if port_item.port.is_input:
                    conn = self.graph.get_input_connection(
                        port_item.port.node_id, port_item.port.name
                    )
                    if conn:
                        src_ni       = self._node_items.get(conn.src_node)
                        src_port_item = src_ni.port_item(conn.src_port) if src_ni else None
                        ci_to_delete = next((ci for c, ci in self._conn_items if c == conn), None)
                        
                        if ci_to_delete and src_port_item:
                            self._moving_conn = (conn, ci_to_delete)
                            ci_to_delete.hide()
                            self._drag_port = src_port_item
                            self._drag_conn = ConnectionItem(src_port_item.scene_center())
                            self.addItem(self._drag_conn)
                            return
                self._drag_port = port_item
                self._drag_conn = ConnectionItem(port_item.scene_center())
                self.addItem(self._drag_conn)
                return

            if any(isinstance(i, ResizeHandle) for i in items):
                super().mousePressEvent(event)
                return

            node_item = next((i for i in items if isinstance(i, NodeItem)), None)
            if node_item:
                if event.modifiers() & Qt.AltModifier:
                    node_item.setSelected(False)
                    return
                if event.modifiers() & Qt.ShiftModifier:
                    node_item.setSelected(not node_item.isSelected())
                    self._drag_start_states = {
                        n.node.id: n.pos()
                        for n in self.selectedItems() if isinstance(n, NodeItem)
                    }
                    return
                if not node_item.isSelected():
                    self.clearSelection()
                    node_item.setSelected(True)
                self._drag_start_states = {
                    n.node.id: n.pos()
                    for n in self.selectedItems() if isinstance(n, NodeItem)
                }

        super().mousePressEvent(event)

    def _update_drag_interaction(self, scene_pos: QPointF) -> None:
        if not self._drag_conn:
            return

        items  = self.items(scene_pos)
        target = next(
            (i for i in items if isinstance(i, PortItem) and i is not self._drag_port),
            None,
        )
        if target != self._hover_port:
            if self._hover_port:
                self._hover_port.set_highlight(False)
            self._hover_port = target
            if self._hover_port:
                is_valid = self._hover_port.port.can_connect_to(self._drag_port.port)
                self._hover_port.set_highlight(True, is_valid)
                self._drag_conn.set_drag_status(is_valid)
            else:
                self._drag_conn.set_drag_status(None)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_conn:
            try:
                self._drag_conn.set_dst(event.scenePos())
                self._update_drag_interaction(event.scenePos())
                return
            except RuntimeError:
                self._drag_conn = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self.graph is None:
            event.ignore()
            return
        if self._drag_start_states:
            move_tuples = []
            for nid, start_p in self._drag_start_states.items():
                item = self._node_items.get(nid)
                if item and item.pos() != start_p:
                    move_tuples.append((nid, start_p.x(), start_p.y(), item.x(), item.y()))
            if move_tuples:
                cmd = MoveNodesCommand(self.graph, move_tuples, weakref.ref(self))
                self._undo_manager._cmd_stack.push(cmd)
            self._drag_start_states = {}
        if self._drag_conn and self._drag_port:
            if self._hover_port:
                try:
                    self._hover_port.set_highlight(False)
                except RuntimeError: pass
                self._hover_port = None

            target = next(
                (i for i in self.items(event.scenePos())
                 if isinstance(i, PortItem) and i is not self._drag_port),
                None,
            )

            if self._moving_conn:
                old_conn, old_ci = self._moving_conn
                self._moving_conn = None
                
                if target and target.port.node_id == old_conn.dst_node and target.port.name == old_conn.dst_port:
                    try:
                        old_ci.show()
                        self.removeItem(self._drag_conn)
                    except RuntimeError: pass
                    self._drag_conn = self._drag_port = None
                    return
                
                if target:
                    with self._undo_manager.transaction("Move Connection"):
                        self._delete_conn(old_ci)
                        self._try_connect(self._drag_port, target)
                    try: self.removeItem(self._drag_conn)
                    except RuntimeError: pass
                    self._drag_conn = self._drag_port = None
                    return
                else:
                    self._delete_conn(old_ci)

            if target:
                self._try_connect(self._drag_port, target)
            else:
                dlg = NodeSearchDialog(None, self._drag_port.port)
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
                        
                        src_p = self._drag_port.port
                        if not src_p.is_input:
                            for p_name, p_obj in new_node.inputs.items():
                                if p_obj.can_connect_to(src_p):
                                    dst_p_item = new_item.port_item(p_name)
                                    if dst_p_item:
                                        self._try_connect(self._drag_port, dst_p_item)
                                    break
                        else:
                            for p_name, p_obj in new_node.outputs.items():
                                if src_p.can_connect_to(p_obj):
                                    src_p_item = new_item.port_item(p_name)
                                    if src_p_item:
                                        self._try_connect(src_p_item, self._drag_port)
                                    break

            try:
                self.removeItem(self._drag_conn)
            except RuntimeError:
                pass
            self._drag_conn = None
            self._drag_port = None
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Delete:
            self.remove_selected()
        elif event.key() == Qt.Key_Escape:
            # Cancel wire creation if in progress
            if self._drag_conn:
                try:
                    self.removeItem(self._drag_conn)
                except RuntimeError:
                    pass
                self._drag_conn = None
                self._drag_port = None
                self._moving_conn = None
            return
        elif event.key() == Qt.Key_F2:
            selected = [i for i in self.selectedItems() if isinstance(i, NodeItem)]
            if selected and not selected[0].node.locked_title:
                self._start_rename(selected[0])
        super().keyPressEvent(event)



class ResizeNodeCommand(QUndoCommand):
    def __init__(self, item: NodeItem, old_w: float, old_h: float, new_w: float, new_h: float):
        super().__init__(f"Resize Node: {item.node.title}")
        self._scene   = item.scene()
        self._node_id = item.node.id
        self.old_w = old_w
        self.old_h = old_h
        self.new_w = new_w
        self.new_h = new_h

    def _get_item(self):
        return self._scene._node_items.get(self._node_id) if self._scene else None

    def undo(self):
        item = self._get_item()
        if item is None:
            return
        item.resize_to(self.old_w, self.old_h)
        sc = item.scene()
        if sc:
            sc._emit_graph_changed()
            sc._undo_manager.sync()

    def redo(self):
        item = self._get_item()
        if item is None:
            return
        item.resize_to(self.new_w, self.new_h)
        sc = item.scene()
        if sc:
            sc._emit_graph_changed()
            sc._undo_manager.sync()
        log.debug(f"Resized node to {self.new_w:.1f}x{self.new_h:.1f}")


class PropertyCommand(QUndoCommand):
    """Undo/redo a single port value change.  Works for both QLineEdit and QComboBox."""

    def __init__(self, node_item: NodeItem, port_name: str, old_val, new_val):
        super().__init__(f"Change {port_name}")
        self._scene   = node_item.scene()
        self._node_id = node_item.node.id
        self.port_name = port_name
        self.old_val   = old_val
        self.new_val   = new_val

    def _get_item(self):
        return self._scene._node_items.get(self._node_id) if self._scene else None

    def undo(self):
        item = self._get_item()
        if item is None:
            return
        self._apply(item, self.old_val)
        sc = item.scene()
        if sc:
            sc._undo_manager.sync()

    def redo(self):
        item = self._get_item()
        if item is None:
            return
        self._apply(item, self.new_val)
        sc = item.scene()
        if sc:
            sc._undo_manager.sync()

    def _apply(self, node_item, val) -> None:
        from gui.items.node import _coerce

        port = node_item.node.inputs.get(self.port_name)

        if port and port.port_type == PortType.FLOAT:
            try:
                val_str = f"{float(val):g}"
            except (ValueError, TypeError):
                val_str = str(val)
        else:
            val_str = str(val) if val is not None else ""

        if port:
            _coerce(port, val_str)

        scene = node_item.scene()
        if scene and port:
            scene._after_node_mutation(node_item.node.id)
            scene._emit_graph_changed()


class FoldCommand(QUndoCommand):
    """Undo/redo node fold/unfold operations."""

    def __init__(self, node_item: 'NodeItem', old_folded: bool, new_folded: bool):
        super().__init__(f"{'Fold' if new_folded else 'Unfold'} Node: {node_item.node.title}")
        self._scene   = node_item.scene()
        self._node_id = node_item.node.id
        self.old_folded = old_folded
        self.new_folded = new_folded
        self.old_height = node_item._unfolded_height

    def _get_item(self):
        return self._scene._node_items.get(self._node_id) if self._scene else None

    def undo(self):
        item = self._get_item()
        if item is None:
            return
        self._apply(item, self.old_folded)
        sc = item.scene()
        if sc:
            sc._undo_manager.sync()

    def redo(self):
        item = self._get_item()
        if item is None:
            return
        self._apply(item, self.new_folded)
        sc = item.scene()
        if sc:
            sc._undo_manager.sync()

    def _apply(self, node_item, folded: bool) -> None:
        if not node_item.node.folded and folded:
            node_item._unfolded_height = node_item._h

        node_item.node.folded = folded
        node_item.refresh_ports()

        if not folded and self.old_height is not None:
            node_item.prepareGeometryChange()
            node_item._h = self.old_height
            node_item.node.height = self.old_height
            node_item.handle.setPos(node_item._w, node_item._h)
            node_item._unfolded_height = None

        node_item.handle.setVisible(not folded)

        scene = node_item.scene()
        if scene:
            scene.refresh_connections(node_item)
            scene._emit_graph_changed()

#  View 

class NodeEditorView(SafeGraphicsView):
    compile_requested  = Signal()
    subgraph_requested = Signal(str)
    view_changed = Signal()

    def __init__(self, scene: NodeEditorScene) -> None:
        super().__init__(scene) # Pass scene to SafeGraphicsView
        
        gl_widget = QOpenGLWidget()
        fmt = QSurfaceFormat.defaultFormat()
        fmt.setSamples(4)
        gl_widget.setFormat(fmt)
        self.setViewport(gl_widget)

        self.setRenderHints(QPainter.Antialiasing | 
                           QPainter.SmoothPixmapTransform | 
                           QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setOptimizationFlags(QGraphicsView.DontAdjustForAntialiasing | 
                                  QGraphicsView.DontSavePainterState)
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(BG_DARKER)))
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)
        self._panning   = False
        self._pan_start = QPoint()

        self._notification: NotificationPopup | None = None
        
        self.allow_zoom = True
        self.allow_pan = True
        self.show_grid = True
        self._bg_color = QColor(BG_DARKER)

    def _get_mouse_scene_pos(self) -> QPointF:
        local_pos = self.viewport().mapFromGlobal(QCursor.pos())
        if self.viewport().rect().contains(local_pos):
            return self.mapToScene(local_pos)
        return self.mapToScene(self.viewport().rect().center())



    def show_notification(self, message: str, is_error: bool = False):
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
        if hasattr(self, "_position_notification"):
            QTimer.singleShot(0, self._position_notification)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        text = event.mimeData().text()
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
                from core.drop_registry import dispatch
                dispatch(kind, self.scene(), current_pos, value, event.modifiers())
                current_pos += QPointF(0, 120)

        event.acceptProposedAction()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        painter.fillRect(rect, self._bg_color)

        if not self.show_grid:
            return

        zoom = self.transform().m11()
        if zoom <= 0: return

        log_z = math.log10(100.0 / zoom)
        exp = math.floor(log_z)
        f = log_z - exp
        
        step_fine = 10.0 ** exp
        step_coarse = step_fine * 10.0
        
        alpha_fine = (1.0 - f) * 0.15
        alpha_coarse = 0.30

        def draw_grid_lines(step: float, alpha: float, color_str: str):
            if alpha <= 0.01:
                return
            l = math.floor(rect.left() / step) * step
            t = math.floor(rect.top() / step) * step
            max_lines = 100
            num_x = int((rect.right() - l) / step) + 1
            num_y = int((rect.bottom() - t) / step) + 1
            if num_x > max_lines or num_y > max_lines:
                return
            color = QColor(color_str)
            color.setAlphaF(alpha)
            pen = QPen(color)
            pen.setWidthF(1.0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            xs = np.arange(l, rect.right() + step, step)
            ys = np.arange(t, rect.bottom() + step, step)
            lines = []
            for x in xs:
                lines.append(QLineF(x, rect.top(), x, rect.bottom()))
            for y in ys:
                lines.append(QLineF(rect.left(), y, rect.right(), y))
            if lines:
                painter.drawLines(lines)

        draw_grid_lines(step_fine, alpha_fine, GRID_FINE)
        draw_grid_lines(step_coarse, alpha_coarse, GRID_COARSE)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self.allow_zoom:
            return
        f = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        self.scale(f, f)
        self.view_changed.emit()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        # Base class SafeGraphicsView guards this, but we override for custom pan/drag logic
        if not self.is_ready_for_events():
            event.ignore()
            return

        if event.button() == Qt.MiddleButton and self.allow_pan:
            self._panning   = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return
        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            self.setDragMode(
                QGraphicsView.NoDrag if item else QGraphicsView.RubberBandDrag
            )
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events():
            # Note: ignore() on mouseMove often propagates up; simply returning is cleaner
            return

        if self._panning:
            d = event.pos() - self._pan_start
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
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events():
            event.ignore()
            return

        item = self.itemAt(event.pos())
        if isinstance(item, NodeItem) and isinstance(item.node, SubgraphNode):
            path = item.node.inputs.get("graph_path").value
            if path:
                if not os.path.isabs(path) and self.scene().graph.project_dir:
                    path = os.path.abspath(
                        os.path.join(self.scene().graph.project_dir, path)
                    )
                self.subgraph_requested.emit(path)
                return
        elif item is None:
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
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        from PySide6.QtWidgets import QApplication

        # Check if focus is on a widget or if scene has a focused item (QGraphicsProxyWidget)
        focus_widget = QApplication.focusWidget()
        scene_focused = self.scene().focusItem() is not None
        is_editing = (focus_widget is not None and focus_widget is not self) or scene_focused

        # If editing in another widget or scene item, deselect nodes and skip all node shortcuts except F5
        if is_editing:
            self.scene().clearSelection()
            if event.key() != Qt.Key_F5:
                # Only handle F5 (compile) even when editing; let everything else pass through
                super().keyPressEvent(event)
                return

        if event.key() == Qt.Key_A and (event.modifiers() & Qt.ShiftModifier):
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
            return
        elif event.matches(QKeySequence.Copy):
            self.scene().copy_selection()
            return
        elif event.matches(QKeySequence.Cut):
            self.scene().cut_selection()
            return
        elif event.matches(QKeySequence.Paste):
            self.scene().paste_from_clipboard(self._get_mouse_scene_pos())
            return
        elif event.key() == Qt.Key_D and (event.modifiers() & Qt.ShiftModifier):
            self.scene().duplicate_selection(self._get_mouse_scene_pos())
            return
        elif event.matches(QKeySequence.SelectAll):
            # Select all nodes in the scene
            for item in self.scene().items():
                if isinstance(item, NodeItem):
                    item.setSelected(True)
            return
        elif event.key() == Qt.Key_F5:
            self.compile_requested.emit()
            return
        super().keyPressEvent(event)

    def get_view_state(self) -> dict:
        """Get the current view state (position and zoom)."""
        transform = self.transform()
        
        # Get scroll bar positions
        h_scroll = self.horizontalScrollBar()
        v_scroll = self.verticalScrollBar()
        scroll_x = h_scroll.value()
        scroll_y = v_scroll.value()
        h_max = h_scroll.maximum()
        v_max = v_scroll.maximum()
        
        return {
            "zoom": transform.m11(),  # Scale factor (m11() == m22() for uniform scaling)
            "scroll_x": scroll_x,
            "scroll_y": scroll_y,
            "scroll_max_x": h_max,
            "scroll_max_y": v_max,
            "transform_m11": transform.m11(),
            "transform_m12": transform.m12(),
            "transform_m21": transform.m21(),
            "transform_m22": transform.m22(),
            "transform_dx": transform.dx(),
            "transform_dy": transform.dy(),
        }

    def set_view_state(self, state: dict) -> None:
        """Restore the view state from saved data."""
        if not state:
            return
            
        # Use the complete transformation matrix if available
        if "transform_m11" in state:
            from PySide6.QtGui import QTransform
            transform = QTransform(
                state["transform_m11"], state["transform_m12"], state["transform_m21"],
                state["transform_m22"], state["transform_dx"], state["transform_dy"]
            )
            self.setTransform(transform)
        else:
            # Fallback to simple zoom
            zoom = state.get("zoom", 1.0)
            self.resetTransform()
            self.scale(zoom, zoom)
        
        # Restore scroll position if available, with delay to ensure proper layout
        if "scroll_x" in state and "scroll_y" in state:
            from PySide6.QtCore import QTimer
            def restore_scroll():
                self.horizontalScrollBar().setValue(state["scroll_x"])
                self.verticalScrollBar().setValue(state["scroll_y"])
            QTimer.singleShot(50, restore_scroll)  # Small delay to ensure layout is complete

    def contextMenuEvent(self, event) -> None:
        item = self.itemAt(event.pos())

        # Handle right-click on input ports
        if isinstance(item, PortItem) and item.port.is_input:
            # Check if there's a connection to delete
            conn = self.scene().graph.get_input_connection(item.port.node_id, item.port.name)
            
            menu = QMenu(self)
            menu.setStyleSheet(MENU)
            
            if conn:
                # Connected: show delete connection option
                delete_act = menu.addAction("Delete connection")
                def delete_connection():
                    with self.scene()._undo_manager.transaction("Delete Connection"):
                        for pair in list(self.scene()._conn_items):
                            if pair[0] == conn:
                                self.scene()._delete_conn(pair[1], push_undo=False)
                                break
                delete_act.triggered.connect(delete_connection)
            else:
                # Not connected: show create wire option
                create_wire_act = menu.addAction("Create wire")
                def create_wire():
                    # Start wire creation from this input port
                    scene = self.scene()
                    scene._drag_port = item
                    scene._drag_conn = ConnectionItem(item.scene_center())
                    scene.addItem(scene._drag_conn)
                    # Set the wire as active selection for immediate dragging
                    scene._drag_conn.setSelected(True)
                create_wire_act.triggered.connect(create_wire)
            
            menu.exec(event.globalPos())
            return

        if isinstance(item, NodeItem):
            # Auto-select the node when right-clicking
            item.setSelected(True)
            menu       = QMenu(self)
            menu.setStyleSheet(MENU)

            rename_act = None
            if not item.node.locked_title:
                rename_act = menu.addAction("Rename")

            open_act   = None
            if isinstance(item.node, SubgraphNode):
                open_act = menu.addAction("Open Subgraph")

            resize_act = menu.addAction("Resize")
            convert_act = menu.addAction("Convert to Subgraph")
            delete_act  = menu.addAction("Delete")
            
            menu.addSeparator()
            add_exec_act = menu.addAction("Add to Execution")
            
            is_loader = (item.node.__class__.__name__ == "FileLoader" or
                        any(k in item.node.outputs or k in item.node.inputs 
                            for k in ("file", "path", "asset")))
            
            mw = self.window()

            action      = menu.exec(event.globalPos())

            if not action:
                return

            if action == open_act:
                path = item.node.inputs.get("graph_path").value
                if path:
                    self.subgraph_requested.emit(path)
            elif action == rename_act:
                self.scene()._start_rename(item)
            elif action == resize_act:
                default_h = item._calculate_height()
                cmd = ResizeNodeCommand(item, item._w, item._h, DEFAULT_W, default_h)
                self.scene()._undo_manager.undo_stack.push(cmd)
            elif action == convert_act:
                targets = [i for i in self.scene().selectedItems() if isinstance(i, NodeItem)]
                if not targets:
                    targets = [item]
                self.scene()._convert_to_subgraph(targets)
            elif action == delete_act:
                self.scene().remove_selected()
            elif action == add_exec_act:
                exec_widget = mw.panel_manager.get_widget("ExecutionDock") if hasattr(mw, "panel_manager") else None
                if exec_widget:
                    with self.scene()._undo_manager.transaction("Add to Execution"):
                        if not item.isSelected():
                            self.scene().clearSelection()
                            item.setSelected(True)
                        exec_widget._add_selected_node()
                    exec_panel = mw.panel_manager.get_panel("ExecutionDock")
                    if exec_panel:
                        exec_panel.show()
                        exec_panel.raise_()
            return

        menu = QMenu(self)
        menu.setStyleSheet(MENU)
        for cat, classes in NODE_CATEGORIES.items():
            cat_menu = menu.addMenu(cat)
            for cls in classes:
                act = cat_menu.addAction(cls.title)
                def trigger(checked, c=cls, p=event.pos()):
                    self.scene().add_node(c(), self.mapToScene(p))
                act.triggered.connect(trigger)
        menu.exec(event.globalPos())