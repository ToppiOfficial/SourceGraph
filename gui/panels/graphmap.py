from __future__ import annotations
import os
import json
from PySide6.QtWidgets import QWidget, QVBoxLayout, QGraphicsItem
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QKeyEvent, QKeySequence, QPainter, QWheelEvent

from gui.panels.base_panel import BasePanel
from core.node import BaseNode, Port, PortType
from core.graph import Graph
from gui.node_editor import NodeEditorScene, NodeEditorView
from gui.theme import ACCENT, BG_RAISED
from gui.widgets.safe_graphics_view import SafeGraphicsView
from gui.items.node import NodeItem
from gui.items.wire import ConnectionItem

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
        self.allow_zoom = True
        self.allow_pan = True

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self.allow_zoom and not self.allow_pan:
            event.accept()
            return
        super().wheelEvent(event)

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
        self.map_scene = NodeEditorScene(self.map_graph)
        self.map_scene.selectionChanged.connect(self._on_selection_changed)

        self.map_view = GraphMapView(self.map_scene) # Pass scene to SafeGraphicsView
        self.map_view.allow_zoom = False
        self.map_view.allow_pan = False
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
        self.refresh()

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
            from gui.items.node import NodeItem
            item = selected[0]
            if isinstance(item, NodeItem) and hasattr(item.node, "nav_node"):
                nav = item.node.nav_node
                if nav and nav != self.main_window._current_nav:
                    self.switch_context_safe(nav)

    def _fit_view(self):
        rect = self.map_scene.itemsBoundingRect()
        if not rect.isEmpty():
            self.map_view.fitInView(rect, Qt.KeepAspectRatio)

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
                gn.color = ACCENT if nav == self.main_window._current_nav else BG_RAISED
                self.map_graph.add_node(gn)
                node_map[nav] = gn
                if not nav.children: return 120
                total_h = 0
                for child in nav.children.values():
                    total_h += _build(child, x + 250, y + total_h)
                return total_h

            _build(self.main_window._nav_root, 0, 0)
            for nav, gn in node_map.items():
                for child in nav.children.values():
                    if child in node_map: self.map_graph.connect(gn.id, "out", node_map[child].id, "in")
            self.map_scene.load_from_graph()

        self.map_scene.blockSignals(False)
        
        for item in self.map_scene.items():
            item.setFlag(QGraphicsItem.ItemIsMovable, False)
            if isinstance(item, ConnectionItem): item.setFlag(QGraphicsItem.ItemIsSelectable, False)
            if isinstance(item, NodeItem) and getattr(item.node, "nav_node", None) == self.main_window._current_nav:
                item.setSelected(True)
        
        self._fit_view()