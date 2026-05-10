from __future__ import annotations

import os
import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QMenu,
)
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QColor, QFont

from gui.widgets.basic_shapes import ShapeDrawer
from gui.dialogs import RenameDialog
from gui.theme import *
from gui.panels.base_panel import BasePanel
from gui.panels.base_browser import BaseBrowserWidget, BaseBrowserTree


class AssetTreeWidget(BaseBrowserTree):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(3)
        self.setColumnHidden(1, True)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.header().setSectionResizeMode(2, QHeaderView.Stretch)
        self.setStyleSheet(TREE_STYLE)

    def dropEvent(self, event):
        super().dropEvent(event)
        self._refresh_folder_spans()

    def _refresh_folder_spans(self):
        """Re-apply first-column spanning for all folders recursively."""
        root = self.invisibleRootItem()
        stack = [(root, self.rootIndex())]
        while stack:
            parent_item, parent_idx = stack.pop()
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                if child.data(0, self._T) == "folder":
                    self.setFirstColumnSpanned(i, parent_idx, True)
                    stack.append((child, self.indexFromItem(child)))

    def add_folder(self, name: str, parent: QTreeWidgetItem | None = None) -> QTreeWidgetItem:
        item = super().add_folder(name, parent)
        self._refresh_folder_spans()
        return item

    def mimeData(self, items):
        data = super().mimeData(items)
        paths = []

        def _collect(it):
            if it.data(0, self._T) == "asset":
                paths.append(it.text(2))
            elif it.data(0, self._T) == "folder":
                for i in range(it.childCount()):
                    _collect(it.child(i))

        for item in items:
            _collect(item)

        if paths:
            data.setText(json.dumps({"type": "assets", "paths": list(dict.fromkeys(paths))}))
        return data

    def add_asset(self, path: str, parent: QTreeWidgetItem | None = None) -> QTreeWidgetItem:
        ext  = os.path.splitext(path)[1][1:].upper() or "FILE"
        name = os.path.basename(path)
        item = QTreeWidgetItem(self if parent is None else parent)
        item.setData(0, self._T, "asset")
        item.setText(0, name)
        item.setText(1, ext)
        item.setText(2, path)

        font = QFont()
        font.setBold(True)
        item.setFont(0, font)

        item.setToolTip(0, f"Name: {name}\nPath: {path}\nType: {ext}")
        item.setToolTip(1, f"Type: {ext}\nPath: {path}")
        item.setToolTip(2, path)

        item.setIcon(0, load_file_icon(path))

        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
        return item

    def _all_assets(self):
        """Depth-first iteration over all asset items (ignores folders)."""
        root  = self.invisibleRootItem()
        stack = [root.child(i) for i in range(root.childCount())]
        while stack:
            item = stack.pop()
            if item.data(0, self._T) == "asset":
                yield item
            for i in range(item.childCount()):
                stack.append(item.child(i))

    def all_paths(self) -> list[str]:
        return [it.text(2) for it in self._all_assets()]


class AssetBrowserWidget(BaseBrowserWidget):
    def __init__(self, main_window: "MainWindow", parent=None):  # pyright: ignore
        super().__init__(main_window, parent)

    # -- base contract --------------------------------------------------------

    def _setup_tree(self, layout):
        self.tree_widget = AssetTreeWidget()
        layout.addWidget(self.tree_widget)
        self._setup_tree_context_menu(self.tree_widget)

    def _setup_connections(self):
        self.tree_widget.deleteRequested.connect(self._on_delete)
        self.tree_widget.hierarchyChanged.connect(self._on_hierarchy_changed)

    def _do_refresh(self):
        layout = self.main_window.graph.asset_layout
        if layout is not None:
            self.set_assets(layout)
        else:
            self.set_assets(self.main_window.graph.assets)

    def _do_sync(self):
        self.main_window.graph.assets = self.tree_widget.all_paths()
        self.main_window.graph.asset_layout = self.get_hierarchy()
        self.main_window.graph._notify()
        self.refresh_status()
        self.main_window.scene.graph_changed.emit()

    def _collect_removed(self, items) -> list:
        paths = []
        def _walk(it):
            if it.data(0, self.tree_widget._T) == "asset":
                paths.append(it.text(2))
            else:
                for i in range(it.childCount()):
                    _walk(it.child(i))
        for it in items:
            _walk(it)
        return paths

    def _notify_removed(self, removed: list):
        for path in removed:
            self.main_window.scene.on_asset_removed(path)

    def _serialize_leaf(self, item: QTreeWidgetItem) -> dict:
        return {"type": "asset", "path": item.text(2)}

    # -- menu -----------------------------------------------------------------

    def _fill_menu(self, menu: QMenu, item: QTreeWidgetItem | None = None):
        if item is None:
            menu.addAction("Import Files...", self._on_import)
            menu.addAction("Add Folder...", self._on_add_folder)
            menu.addAction("Find Missing...", self._on_find_missing)

    def _fill_folder_menu(self, menu: QMenu, folder_item: QTreeWidgetItem):
        menu.addAction("Import Files...", lambda: self._on_import_to_folder(folder_item))
        menu.addSeparator()
        menu.addAction("Add Folder...", lambda: self._on_add_subfolder(folder_item))

    def _show_action_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(MENU)
        self._fill_menu(menu)
        button_rect = self.action_btn.geometry()
        menu_pos = self.action_btn.mapToGlobal(button_rect.bottomLeft())
        menu.exec(menu_pos)

    # -- public API -----------------------------------------------------------

    def set_assets(self, data: list) -> None:
        self._is_rebuilding = True
        try:
            self.tree_widget.clear()

            def _apply(items, parent=None):
                for d in items:
                    if isinstance(d, str):  # legacy flat list
                        self.tree_widget.add_asset(d, parent)
                    elif d.get("type") == "folder":
                        folder = self.tree_widget.add_folder(d["name"], parent)
                        folder.setExpanded(d.get("expanded", True))
                        _apply(d.get("children", []), folder)
                    else:
                        path = d.get("path", "") if isinstance(d, dict) else str(d)
                        if path:
                            self.tree_widget.add_asset(path, parent)
            _apply(data, None)
            self.tree_widget._refresh_folder_spans()
            self.refresh_status()
        finally:
            self._is_rebuilding = False

    def refresh_status(self) -> None:
        """Highlight missing files in red."""
        for item in self.tree_widget._all_assets():
            path = item.text(2)
            if not os.path.exists(path):
                item.setForeground(0, QColor(COLOR_INVALID))
                item.setForeground(2, QColor(COLOR_INVALID))
                item.setToolTip(0, f"File missing: {path}")
            else:
                item.setData(0, Qt.ForegroundRole, None)
                item.setData(2, Qt.ForegroundRole, None)
                item.setToolTip(0, path)

    # -- handlers -------------------------------------------------------------

    def _on_import(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Import Assets", "",
            "All Files (*)"
        )
        if not files:
            return
        existing = set(self.tree_widget.all_paths())
        parent = self._selected_parent()
        with self.main_window.scene._undo_manager.transaction("Import Assets"):
            for f in files:
                if f not in existing:
                    self.tree_widget.add_asset(f, parent)
            self._sync_to_graph()

    def _on_add_folder(self):
        dlg = RenameDialog("New Folder", "New Folder", "Folder name:", self)
        if dlg.exec() != 1:
            return
        name = dlg.get_name().strip()
        if name:
            with self.main_window.scene._undo_manager.transaction("Add Folder"):
                self.tree_widget.add_folder(name, None)
                self._sync_to_graph()

    def _on_import_to_folder(self, folder_item):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Import Assets to Folder", "",
            "All Files (*)"
        )
        if not files:
            return
        existing = set(self.tree_widget.all_paths())
        with self.main_window.scene._undo_manager.transaction("Import Assets to Folder"):
            for f in files:
                if f not in existing:
                    self.tree_widget.add_asset(f, folder_item)
            self._sync_to_graph()

    def _on_add_subfolder(self, parent_folder):
        dlg = RenameDialog("New Folder", "New Folder", "Folder name:", self)
        if dlg.exec() != 1:
            return
        name = dlg.get_name().strip()
        if name:
            with self.main_window.scene._undo_manager.transaction("Add Subfolder"):
                self.tree_widget.add_folder(name, parent_folder)
                self._sync_to_graph()

    def _on_find_missing(self):
        from gui.menu.asset_finder import AssetFinderDialog
        missing = [p for p in self.tree_widget.all_paths() if not os.path.exists(p)]
        if not missing:
            return
        dlg = AssetFinderDialog(missing, self)
        if dlg.exec() != 1:
            return
        results = dlg.get_results()
        if not results:
            return
        with self.main_window.scene._undo_manager.transaction("Resolve Missing Assets"):
            for item in self.tree_widget._all_assets():
                old_path = item.text(2)
                if old_path not in results:
                    continue
                new_path = results[old_path]
                name = os.path.basename(new_path)
                ext = os.path.splitext(new_path)[1][1:].upper() or "FILE"
                item.setText(0, name)
                item.setText(1, ext)
                item.setText(2, new_path)
                item.setToolTip(0, f"Name: {name}\nPath: {new_path}\nType: {ext}")
                item.setToolTip(1, f"Type: {ext}\nPath: {new_path}")
                item.setToolTip(2, new_path)
                item.setIcon(0, load_file_icon(new_path))
            # Remap port values on any node that references a resolved path
            scene = self.main_window.scene
            for node in self.main_window.graph.nodes.values():
                for port in node.inputs.values():
                    if port.value in results:
                        port.value = results[port.value]
                        scene._after_node_mutation(node.id)
                        break
            self._sync_to_graph()
            scene._emit_graph_changed()
        self.refresh_status()

    def _put_selected_in_folder(self, tree_widget, selected_items, folder_name):
        with self.main_window.scene._undo_manager.transaction("Put Items in Folder"):
            folder = tree_widget.add_folder(folder_name)
            root = tree_widget.invisibleRootItem()
            for item in selected_items:
                if item.data(0, tree_widget._T) in ["asset", "folder"]:
                    parent = item.parent() or root
                    parent.removeChild(item)
                    folder.addChild(item)
            self._sync_to_graph()

    # -- internals ------------------------------------------------------------

    def _selected_parent(self) -> QTreeWidgetItem | None:
        """Return the folder to add into based on current selection."""
        sel = self.tree_widget.selectedItems()
        if not sel:
            return None
        s = sel[0]
        if s.data(0, self.tree_widget._T) == "folder":
            return s
        if s.parent() and s.parent().data(0, self.tree_widget._T) == "folder":
            return s.parent()
        return None


class AssetModularPanel(BasePanel):
    ID           = "AssetDock"
    TITLE        = "Asset Browser"
    DEFAULT_AREA = Qt.LeftDockWidgetArea
    COLOR        = "#63c2df"

    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self._widget = AssetBrowserWidget(main_window)
        self.setWidget(self._widget)

    def setup(self) -> None:
        sc = self.main_window.scene
        if sc:
            sc.graph_changed.connect(self._widget.refresh)
            self._widget.refresh()

    def update_context(self, graph, scene) -> None:
        self._widget.main_window.graph = graph
        if self._active_scene:
            try: self._active_scene.graph_changed.disconnect(self._widget.refresh)
            except (TypeError, RuntimeError): pass

        self._active_scene = scene
        scene.graph_changed.connect(self._widget.refresh)
        self._widget.refresh()