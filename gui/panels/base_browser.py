"""
Base browser widget class to eliminate code duplication between Asset and Variables browsers.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QMenu, QTreeWidgetItem, QTreeWidget, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QRect
from PySide6.QtGui import QAction, QColor, QFont

from gui.theme import BTN_STYLE, MENU, FG_DIM, FG_BRIGHT, get_folder_icon
from gui.widgets.basic_shapes import ShapeDrawer
from gui.dialogs import RenameDialog


class BaseBrowserTree(QTreeWidget):
    """Base tree for assets and variables with shared hierarchy and drag-drop logic."""
    deleteRequested = Signal()
    hierarchyChanged = Signal()

    _T = Qt.UserRole  # "item" | "folder"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setIndentation(16)
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.setAnimated(False)
        self.setHeaderHidden(True)
        self.itemExpanded.connect(lambda _: self.hierarchyChanged.emit())
        self.itemCollapsed.connect(lambda _: self.hierarchyChanged.emit())

    def drawBranches(self, painter, rect, index):
        """Draw custom fold/unfold indicators."""
        super().drawBranches(painter, rect, index)

        # Skip drawing for root items (depth 0)
        depth = 0
        tmp = index
        while tmp.parent().isValid():
            tmp = tmp.parent()
            depth += 1
        
        if depth > 0:
            painter.save()
            painter.setRenderHint(painter.RenderHint.Antialiasing, False)
            
            # Subtle line color matching the UI theme
            line_pen = QColor(FG_DIM)
            line_pen.setAlpha(80)
            painter.setPen(line_pen)

            indent = self.indentation()

            ancestor = index.parent()
            for i in range(depth - 1, -1, -1):
                if ancestor.sibling(ancestor.row() + 1, 0).isValid():
                    lx = rect.left() + (i * indent) + (indent // 2)
                    painter.drawLine(lx, rect.top(), lx, rect.bottom())
                ancestor = ancestor.parent()

            cx = rect.left() + (depth * indent) + (indent // 2)
            cy = rect.top() + (rect.height() // 2)
            
            if index.sibling(index.row() + 1, 0).isValid():
                painter.drawLine(cx, rect.top(), cx, rect.bottom())
            else:
                painter.drawLine(cx, rect.top(), cx, cy)

            painter.drawLine(cx, cy, cx + (indent // 2), cy)
            painter.restore()

        if not self.model().hasChildren(index):
            return
        indent = self.indentation()
        arrow_rect = QRect(rect.right() - indent, rect.top(), indent, rect.height())
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(FG_DIM))
        size = 8
        x = arrow_rect.x() + (arrow_rect.width() - size) // 2
        y = arrow_rect.y() + (arrow_rect.height() - size) // 2
        shape_func = ShapeDrawer.draw_triangle_down if self.isExpanded(index) else ShapeDrawer.draw_triangle_left
        shape_func(painter, x, y, size)
        painter.restore()

    def dropEvent(self, event):
        """Drop with expansion preservation."""
        expanded = []
        stack = [self.invisibleRootItem().child(i) for i in range(self.invisibleRootItem().childCount())]
        while stack:
            it = stack.pop()
            if it.isExpanded(): expanded.append(it)
            for i in range(it.childCount()): stack.append(it.child(i))

        super().dropEvent(event)
        self._enforce_hierarchy()
        for item in expanded: item.setExpanded(True)
        self.hierarchyChanged.emit()

    def _enforce_hierarchy(self):
        """Ensure items aren't nested inside leaf items."""
        root = self.invisibleRootItem()

        def _clean(parent):
            i = 0
            while i < parent.childCount():
                item = parent.child(i)
                if item.data(0, self._T) != "folder":
                    while item.childCount():
                        parent.insertChild(i + 1, item.takeChild(0))
                else:
                    _clean(item)
                i += 1
        _clean(root)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            self.deleteRequested.emit()
            return
        super().keyPressEvent(event)

    def add_folder(self, name: str, parent: QTreeWidgetItem | None = None) -> QTreeWidgetItem:
        item = QTreeWidgetItem(self if parent is None else parent)
        item.setData(0, self._T, "folder")
        item.setText(0, name)
        item.setIcon(0, get_folder_icon())
        font = QFont()
        font.setBold(True)
        item.setFont(0, font)
        item.setForeground(0, QColor(FG_BRIGHT))
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled)
        item.setExpanded(True)
        # Set tooltip for folder showing its name
        item.setToolTip(0, f"Folder: {name}")
        return item


class BaseBrowserWidget(QWidget):
    """Base class for browser widgets with single '=' button action menu."""

    def __init__(self, main_window: "MainWindow", parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self._is_rebuilding = False  # blocks refresh() from reacting to graph_changed
        self._is_syncing    = False  # blocks re-entrant _sync_to_graph calls
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup UI with single '=' button - to be overridden by subclasses."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        
        # Single action button with '=' symbol
        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        self.action_btn = QPushButton("=")
        self.action_btn.setToolTip("Actions (right-click for menu)")
        self.action_btn.setFixedWidth(32)
        self.action_btn.setStyleSheet(BTN_STYLE)
        self.action_btn.clicked.connect(self._show_action_menu)
        toolbar.addWidget(self.action_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)
        
        # Tree widget - to be set by subclass
        self._setup_tree(layout)
        self._setup_connections()
    
    def _setup_tree(self, layout):
        """Setup tree widget - to be implemented by subclass."""
        raise NotImplementedError("Subclass must implement _setup_tree")
    
    def _setup_connections(self):
        """Setup signal connections - to be implemented by subclass."""
        raise NotImplementedError("Subclass must implement _setup_connections")
    
    def _show_action_menu(self):
        """Show action menu from '=' button click - to be implemented by subclass."""
        raise NotImplementedError("Subclass must implement _show_action_menu")
    
    def get_menu_actions(self):
        """Get list of menu actions - to be implemented by subclass."""
        raise NotImplementedError("Subclass must implement get_menu_actions")
    
    def _setup_tree_context_menu(self, tree_widget):
        """Setup context menu for tree widget items."""
        def show_context_menu(pos):
            item = tree_widget.itemAt(pos)
            if item is None:
                menu = QMenu(tree_widget)
                menu.setStyleSheet(MENU)
                self._fill_menu(menu, None)
                if menu.actions(): menu.exec(tree_widget.mapToGlobal(pos))
                return
            
            is_folder = item.data(0, tree_widget._T) == "folder"
            menu = QMenu(tree_widget)
            menu.setStyleSheet(MENU)
            if is_folder:
                self._fill_folder_menu(menu, item)
                menu.addSeparator()
                menu.addAction("Delete", self._on_delete)
            else:
                menu.addAction("Delete", self._on_delete)
                menu.addAction("Put in Folder", lambda: self._on_context_put_in_folder(tree_widget))
            menu.exec(tree_widget.mapToGlobal(pos))
        
        tree_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        tree_widget.customContextMenuRequested.connect(show_context_menu)
    
    def _on_delete(self):
        items = self.tree_widget.selectedItems()
        if not items:
            return

        removed = self._collect_removed(items)

        self._is_rebuilding = True
        try:
            with self.main_window.scene._undo_manager.transaction("Delete"):
                self._remove_items(items)
                self._sync_to_graph()
                self._notify_removed(removed)
        finally:
            self._is_rebuilding = False

    def _remove_items(self, items):
        root = self.tree_widget.invisibleRootItem()
        leaves  = [it for it in items if it.data(0, self.tree_widget._T) != "folder"]
        folders = [it for it in items if it.data(0, self.tree_widget._T) == "folder"]
        for it in leaves:
            (it.parent() or root).removeChild(it)
        for folder in folders:
            p = folder.parent() or root
            while folder.childCount():
                p.addChild(folder.takeChild(0))
            p.removeChild(folder)

    def _notify_deleted_data(self, deletion_data):
        """Hook for subclasses to process collected deletion data."""
        pass

    def _notify_deleted(self, items):
        """Optional hook for subclasses to notify about deleted items."""
        pass

    def get_hierarchy(self) -> list[dict]:
        """Serialize tree to dict list."""
        def _serialize(item):
            if item.data(0, self.tree_widget._T) == "folder":
                return {
                    "type": "folder", "name": item.text(0),
                    "expanded": item.isExpanded(),
                    "children": [_serialize(item.child(i)) for i in range(item.childCount())]
                }
            return self._serialize_leaf(item)
        root = self.tree_widget.invisibleRootItem()
        return [_serialize(root.child(i)) for i in range(root.childCount())]

    def _serialize_leaf(self, item: QTreeWidgetItem) -> dict:
        raise NotImplementedError()

    def refresh(self):
        if self._is_rebuilding or not self.main_window.graph:
            return
        self._do_refresh()

    def _do_refresh(self):
        """Subclass implements this — called only when safe to rebuild."""
        raise NotImplementedError()

    def _sync_to_graph(self):
        if not self.main_window.graph or self._is_syncing:
            return
        self._is_syncing = True
        try:
            self._do_sync()
        finally:
            self._is_syncing = False

    def _on_hierarchy_changed(self):
        if self._is_rebuilding or self._is_syncing:
            return
        with self.main_window.scene._undo_manager.transaction("Reorder"):
            self._sync_to_graph()
    
    def _on_context_put_in_folder(self, tree_widget):
        """Handle put in folder from context menu."""
        selected = tree_widget.selectedItems()
        if not selected:
            return
        
        # Prompt for folder name
        dlg = RenameDialog("New Folder", "New Folder", "Folder name:", self)
        if dlg.exec() != 1:  # QDialog.Accepted == 1
            return
        folder_name = dlg.get_name().strip()
        if not folder_name:
            return
        
        self._put_selected_in_folder(tree_widget, selected, folder_name)
    
    def _put_selected_in_folder(self, tree_widget, selected_items, folder_name):
        """Put selected items in a new folder - to be implemented by subclass."""
        raise NotImplementedError("Subclass must implement _put_selected_in_folder")
    
    def _fill_menu(self, menu: QMenu, item: QTreeWidgetItem | None = None):
        """Fill menu with actions - to be implemented by subclass."""
        raise NotImplementedError("Subclass must implement _fill_menu")
    
    def _fill_folder_menu(self, menu: QMenu, folder_item: QTreeWidgetItem):
        """Fill menu with folder-specific actions - to be implemented by subclass."""
        raise NotImplementedError("Subclass must implement _fill_folder_menu")

    def _collect_removed(self, items) -> list:
        """Subclass returns whatever data _notify_removed needs."""
        return []
    
    def _notify_removed(self, removed: list):
        """Subclass notifies the scene after graph is consistent."""
        pass