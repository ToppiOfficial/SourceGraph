from __future__ import annotations
import os
import json
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGraphicsItem
from PySide6.QtCore import Qt, QEvent, QTimer, QRectF, QPointF
from PySide6.QtGui import (QKeyEvent, QKeySequence, QPainter, QWheelEvent,
                            QPainterPath, QFont, QPen, QColor, QBrush, QLinearGradient, QTransform)

from gui.panels.base_panel import BasePanel
from core.node import BaseNode, Port, PortType
from core.graph import Graph
from gui.node_editor import NodeEditorScene, NodeEditorView
from gui.theme import ACCENT, BG_RAISED, COLOR_ERROR, FG_MAIN
from gui.logger import log
from gui.widgets.safe_graphics_view import SafeGraphicsView
from gui.items.node import NodeItem, PortItem, _folded_height
from gui.items.wire import ConnectionItem

class GraphMapNodeItem(NodeItem):
    """Custom node item for graph map with larger folded header and read-only ports."""
    GRAPH_MAP_TITLE_H = 32

    def _calculate_height(self):
        """Override to use larger title height for folded nodes in graph map."""
        if self.node.folded:
            visible_outputs = sum(1 for p in self.node.outputs.values() if p.allow_connection)
            visible_inputs = sum(1 for p in self.node.inputs.values()
                               if p.allow_connection)
            min_h = _folded_height(max(visible_outputs, visible_inputs))
            return max(min_h, self.GRAPH_MAP_TITLE_H)
        return super()._calculate_height()

    def _build(self):
        """Build node and make ports non-interactive."""
        super()._build()
        # Disable all port interaction after building
        self._make_ports_readonly()

    def _make_ports_readonly(self):
        """Make all port items completely non-interactive."""
        for port_item in self._port_items.values():
            port_item.setFlag(QGraphicsItem.ItemIsSelectable, False)
            port_item.setFlag(QGraphicsItem.ItemIsFocusable, False)
            port_item.setAcceptDrops(False)
            port_item.setAcceptHoverEvents(False)
            port_item.setAcceptedMouseButtons(Qt.NoButton)  # Ignore all mouse events
            port_item.setCursor(Qt.ArrowCursor)



class GraphMapScene(NodeEditorScene):
    """Custom scene for graph map that uses straight connection wires and larger headers."""
    def load_from_graph(self):
        with self._undo_manager.skip_undo():
            self.clear()
            self._node_items.clear()
            self._conn_items.clear()
            for node in self.graph.nodes.values():
                node.graph = self.graph
                item = GraphMapNodeItem(node)
                self._node_items[node.id] = item
                self.addItem(item)
                self._dirty_nodes.add(node.id)
            for conn in self.graph.connections:
                self._materialise_conn(conn)
        self._undo_manager.clear()
        self._emit_graph_changed()

    def mousePressEvent(self, event):
        """Block wire creation while allowing node selection for navigation."""
        item = self.itemAt(event.scenePos(), QTransform())

        # Block port clicks (prevents wire creation)
        if isinstance(item, PortItem):
            event.accept()
            return

        # Allow node clicks and empty space for normal selection behavior
        super().mousePressEvent(event)

    def _materialise_conn(self, conn):
        src_ni = self._node_items.get(conn.src_node)
        dst_ni = self._node_items.get(conn.dst_node)
        if not (src_ni and dst_ni):
            return None
        sp = src_ni.port_item(conn.src_port)
        dp = dst_ni.port_item(conn.dst_port)
        if not (sp and dp):
            return None
        
        old_style = ConnectionItem.wire_style
        ConnectionItem.wire_style = "straight"
        ci = ConnectionItem(sp.scene_center(), dp.scene_center())
        ConnectionItem.wire_style = old_style
        
        self._conn_items.append((conn, ci))
        self.addItem(ci)
        dst_ni.set_port_connected(conn.dst_port, True, sp.port.port_type)
        return ci

class NavGraphNode(BaseNode):
    """Minimal node for the hierarchy navigation graph."""
    def __init__(self, nav_node=None):
        super().__init__()
        self.nav_node = nav_node
        self.locked_title = True
        self.allow_folding = False
        self.inputs = {"in": Port("in", True, PortType.SIGNAL, self.id)}
        self.outputs = {"out": Port("out", False, PortType.SIGNAL, self.id)}
        if nav_node:
            name = os.path.basename(nav_node.path) or "Root"
            self.title = name.upper()
            if nav_node.graph._is_dirty:
                self.title += " (!)"

class GraphMapView(SafeGraphicsView):
    """Custom view for the Graph Map that blocks editing shortcuts."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform | QPainter.TextAntialiasing)
        self.allow_zoom = False
        self.allow_pan = False

    def wheelEvent(self, event: QWheelEvent) -> None:
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Delete or event.matches(QKeySequence.Copy) or \
           event.matches(QKeySequence.Paste) or (event.key() == Qt.Key_D and event.modifiers() & Qt.ShiftModifier):
            event.accept()
            return
        super().keyPressEvent(event)
        
class GraphMapPanel(BasePanel):
    """Panel that displays the project file hierarchy as a node graph."""
    ID = "GraphMapDock"
    TITLE = "Graph Map"
    DEFAULT_AREA = Qt.BottomDockWidgetArea

    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self._widget = QWidget()
        layout = QVBoxLayout(self._widget)
        layout.setContentsMargins(0, 0, 0, 0)

        self.map_graph = Graph()
        self.map_scene = GraphMapScene(self.map_graph)
        self.map_scene.selectionChanged.connect(self._on_selection_changed)

        self.map_view = GraphMapView(self.map_scene)
        self.map_view.show_grid = False
        self.map_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.map_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.map_view.setDragMode(NodeEditorView.NoDrag)
        self.map_view.setContextMenuPolicy(Qt.NoContextMenu)
        
        layout.addWidget(self.map_view)
        self.setWidget(self._widget)
        
        # Event filter for resizing
        self.map_view.installEventFilter(self)

    def eventFilter(self, watched, event):
        if watched == self.map_view and event.type() == QEvent.Resize:
            self._fit_view()
        return super().eventFilter(watched, event)

    def setup(self) -> None:
        self.visibilityChanged.connect(self._on_visibility_changed)
        self.refresh()

    def _on_visibility_changed(self, visible: bool):
        if visible:
            QTimer.singleShot(50, self._fit_view)

    def update_context(self, graph, scene) -> None:
        if self._active_scene:
            try: self._active_scene.graph_changed.disconnect(self.refresh)
            except (TypeError, RuntimeError): pass
            
        self._active_scene = scene
        scene.graph_changed.connect(self.refresh)
        self.refresh()

    def _on_selection_changed(self):
        if self.main_window._is_switching: return

        try:
            selected = self.map_scene.selectedItems()
        except RuntimeError:
            return
            
        if len(selected) == 1:
            item = selected[0]
            if isinstance(item, NodeItem) and hasattr(item.node, "nav_node"):
                nav = item.node.nav_node
                if nav and nav != self.main_window._current_nav:
                    self.switch_context_safe(nav)

    def _fit_view(self):
        rect = self.map_scene.itemsBoundingRect()
        if not rect.isEmpty():
            self.map_view.fitInView(rect, Qt.KeepAspectRatio)

    def update_execution_errors(self) -> None:
        """Mark nav nodes whose subgraph had an execution error, then refresh."""
        mw = self.main_window
        graph = getattr(mw, 'graph', None)
        current_nav = getattr(mw, '_current_nav', None)
        if not graph or not current_nav:
            return
        for node in graph.nodes.values():
            if node.__class__.__name__ != "SubgraphNode":
                continue
            if not node.error_msg:
                continue
            path = node.inputs.get("graph_path", {}).value if "graph_path" in node.inputs else ""
            if not path:
                continue
            if not os.path.isabs(path) and graph.project_dir:
                path = os.path.normpath(os.path.join(graph.project_dir, path))
            abs_path = os.path.abspath(path)
            child_nav = current_nav.children.get(abs_path)
            if child_nav:
                child_nav.exec_error = True
                log.error(f"[GraphMap] Subgraph execution error in: {os.path.basename(abs_path)}")
        self.refresh()

    def refresh(self) -> None:
        if not self.main_window._nav_root or not self.main_window._current_nav:
            self.map_scene.clear()
            return

        self.map_scene.blockSignals(True)
        with self.map_scene._undo_manager.skip_undo():
            self.map_graph.nodes.clear()
            self.map_graph.connections.clear()
            
            node_map = {}
            def _build(nav, x, y):
                gn = NavGraphNode(nav)
                gn.x, gn.y = x, y
                gn.folded = True
                if nav == self.main_window._current_nav:
                    gn.color = ACCENT
                elif getattr(nav, 'exec_error', False):
                    gn.color = COLOR_ERROR
                elif getattr(nav, 'has_cycle', False):
                    gn.color = COLOR_ERROR
                else:
                    gn.color = BG_RAISED
                self.map_graph.add_node(gn)
                node_map[nav] = gn
                if not nav.children: return 50
                total_h = 0
                for child in nav.children.values():
                    total_h += _build(child, x + 220, y + total_h)
                return total_h

            _build(self.main_window._nav_root, 0, 0)
            for nav, gn in node_map.items():
                for child in nav.children.values():
                    if child in node_map: self.map_graph.connect(gn.id, "out", node_map[child].id, "in")
            self.map_scene.load_from_graph()

        self.map_scene.blockSignals(False)

        # Make all items read-only and non-interactive
        for item in self.map_scene.items():
            item.setFlag(QGraphicsItem.ItemIsMovable, False)
            item.setFlag(QGraphicsItem.ItemIsFocusable, False)
            item.setAcceptDrops(False)
            item.setAcceptHoverEvents(False)

            if isinstance(item, NodeItem):
                item.setFlag(QGraphicsItem.ItemIsSelectable, True)

                # Disable all port interaction
                for port_item in item._port_items.values():
                    port_item.setFlag(QGraphicsItem.ItemIsSelectable, False)
                    port_item.setFlag(QGraphicsItem.ItemIsFocusable, False)
                    port_item.setAcceptDrops(False)
                    port_item.setAcceptHoverEvents(False)
                    port_item.setCursor(Qt.ArrowCursor)  # Reset cursor

                if getattr(item.node, "nav_node", None) == self.main_window._current_nav:
                    item.setSelected(False)  # Don't select, just color shows which is current
            else:
                item.setFlag(QGraphicsItem.ItemIsSelectable, False)

        QTimer.singleShot(50, self._fit_view)