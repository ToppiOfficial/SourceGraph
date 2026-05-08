from __future__ import annotations

import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTreeWidgetItem,
    QHeaderView, QMenu, QDialog, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeyEvent, QIcon, QPixmap, QPainter, QColor, QFont

from gui.widgets.basic_shapes import ShapeDrawer
from core.node import PortType, port_uses_graph_variables
from gui.panels.base_panel import BasePanel
from gui.panels.base_browser import BaseBrowserWidget, BaseBrowserTree
from gui.dialogs import RenameDialog
from gui.theme import *


# -- value helpers ------------------------------------------------------------

def _parse_value(v: str):
    if isinstance(v, str):
        if v.lower() in ("true", "false"):
            return v.lower() == "true"
        try:
            if v.isdigit() or (v.startswith("-") and v[1:].isdigit()):
                return int(v)
        except ValueError:
            pass
        try:
            return float(v)
        except ValueError:
            pass
    return v


def _format_value(v) -> str:
    return "<empty>" if (v is None or v == "") else str(v)


def _type_icon(value) -> QIcon:
    px = QPixmap(16, 16)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    if value is None or value == "" or value == "<empty>":
        color = QColor(COLOR_INVALID)
    else:
        v = _parse_value(value) if isinstance(value, str) else value
        if isinstance(v, bool):    color = QColor(VAR_BOOL)
        elif isinstance(v, int):   color = QColor(VAR_INT)
        elif isinstance(v, float): color = QColor(VAR_FLOAT)
        else:                      color = QColor(VAR_STR)
    p.setBrush(color)
    p.setPen(Qt.NoPen)
    p.drawEllipse(2, 2, 12, 12)
    p.end()
    return QIcon(px)


# -- tree widget ---------------------------------------------------------------

class VariablesTreeWidget(BaseBrowserTree):
    value_edit_requested = Signal(str, str)  # var_name, current_value
    var_rename_requested = Signal(str, str)  # old_name, new_name

    _N = Qt.UserRole + 1   # name role

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(2)
        self.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.header().setSectionResizeMode(1, QHeaderView.Stretch)
        self.setStyleSheet(TREE_STYLE)

    def mimeData(self, items):
        data = super().mimeData(items)
        names = []

        def _collect(it):
            if it.data(0, self._T) == "var":
                names.append(it.data(0, self._N))
            elif it.data(0, self._T) == "folder":
                for i in range(it.childCount()):
                    _collect(it.child(i))

        for item in items:
            _collect(item)

        if names:
            data.setText(json.dumps({"type": "variables", "names": list(dict.fromkeys(names))}))
        return data

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

    # -- item factories -------------------------------------------------------

    def add_folder(self, name: str, parent=None):
        item = super().add_folder(name, parent)
        item.setData(0, self._N, name)
        self._refresh_folder_spans()
        return item

    def add_variable(self, name: str, value, parent: QTreeWidgetItem | None = None) -> QTreeWidgetItem:
        item = QTreeWidgetItem(self if parent is None else parent)
        item.setData(0, self._T, "var")
        item.setData(0, self._N, name)
        item.setText(0, name)
        item.setText(1, _format_value(value))
        
        font = QFont()
        font.setBold(True)
        item.setFont(0, font)
        
        item.setIcon(0, _type_icon(value))
        # Variables accept no children
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled)
        return item

    def update_variable(self, name: str, value):
        for item in self._all_vars():
            if item.data(0, self._N) == name:
                item.setText(1, _format_value(value))
                item.setIcon(0, _type_icon(value))
                break

    # -- iteration ------------------------------------------------------------

    def _all_vars(self):
        """Depth-first iteration over all variable items (ignores folders)."""
        root  = self.invisibleRootItem()
        stack = [root.child(i) for i in range(root.childCount())]
        while stack:
            item = stack.pop()
            if item.data(0, self._T) == "var":
                yield item
            for i in range(item.childCount()):
                stack.append(item.child(i))

    def get_variable_names(self) -> list[str]:
        return [it.data(0, self._N) for it in self._all_vars()]

    # -- keyboard -------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._do_edit_value()
        elif event.key() == Qt.Key_F2:
            self._do_rename()
        else:
            super().keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.position().toPoint())
        if item and item.data(0, self._T) == "var":
            self.value_edit_requested.emit(item.data(0, self._N), item.text(1))
            return  # don't expand/collapse on var double-click
        super().mouseDoubleClickEvent(event)

    def _do_rename(self):
        item = self.currentItem()
        if not item:
            return
        typ = item.data(0, self._T)
        cur = item.data(0, self._N)
        lbl = "Rename Folder" if typ == "folder" else "Rename Variable"
        dlg = RenameDialog(lbl, cur, "Enter new name:", self)
        if dlg.exec() != QDialog.Accepted:
            return
        new = dlg.get_name().strip()
        if not new or new == cur:
            return
        if typ == "folder":
            item.setData(0, self._N, new)
            item.setText(0, new)
        else:
            self.var_rename_requested.emit(cur, new)

    def _do_edit_value(self):
        item = self.currentItem()
        if item and item.data(0, self._T) == "var":
            self.value_edit_requested.emit(item.data(0, self._N), item.text(1))


# -- browser widget ------------------------------------------------------------

class VariablesBrowserWidget(BaseBrowserWidget):
    def __init__(self, main_window: "MainWindow", parent=None):  # pyright: ignore
        super().__init__(main_window, parent)
        self._in_command = False

    def _setup_tree(self, layout):
        """Setup variables tree widget."""
        self.tree_widget = VariablesTreeWidget()
        layout.addWidget(self.tree_widget)
        # Setup context menu from base class
        self._setup_tree_context_menu(self.tree_widget)

    def _setup_connections(self):
        self.tree_widget.deleteRequested.connect(self._on_delete)
        self.tree_widget.value_edit_requested.connect(self._on_edit_value)
        self.tree_widget.var_rename_requested.connect(self._on_variable_name_changed)
        self.tree_widget.hierarchyChanged.connect(self._on_hierarchy_changed)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)
        self.action_btn = QPushButton("=")
        self.action_btn.setFixedWidth(32)
        self.action_btn.setStyleSheet(BTN_STYLE)
        self.action_btn.clicked.connect(self._show_action_menu)
        toolbar.addWidget(self.action_btn)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._setup_tree(layout)
        self._setup_connections()

    def _fill_menu(self, menu: QMenu, item: QTreeWidgetItem | None = None):
        """Populate menu with variable actions based on selection."""
        if item is None:
            menu.addAction("Add Variable...", self._on_add)
            menu.addAction("Add Folder...", self._on_add_folder)
            return

        typ = item.data(0, self.tree_widget._T)
        if item == self.root_item or typ == "folder":
            menu.addAction("Rename Folder", self.tree_widget._do_rename)
            menu.addSeparator()
            menu.addAction("Delete Folder", self._on_delete)
        elif typ == "var":
            menu.addAction("Rename Variable", self.tree_widget._do_rename)
            menu.addAction("Edit Value", self.tree_widget._do_edit_value)
            menu.addSeparator()
            menu.addAction("Delete Variable", self._on_delete)
    
    def _fill_folder_menu(self, menu: QMenu, folder_item: QTreeWidgetItem):
        """Populate menu with folder-specific actions."""
        menu.addAction("Add Variable...", lambda: self._on_add_to_folder(folder_item))
        menu.addAction("Add Folder...", lambda: self._on_add_subfolder(folder_item))
        menu.addAction("Rename Folder", self.tree_widget._do_rename)

    def _show_action_menu(self):
        """Show action menu from '=' button click."""
        # Clear selection so _fill_menu adds global actions
        self.tree_widget.clearSelection()
        
        menu = QMenu(self)
        menu.setStyleSheet(MENU)
        self._fill_menu(menu, None)

        button_rect = self.action_btn.geometry()
        menu_pos = self.action_btn.mapToGlobal(button_rect.bottomLeft())
        menu.exec(menu_pos)

    # -- public API -----------------------------------------------------------

    def get_flat_variables(self) -> dict:
        """Derived flat dictionary for node logic."""
        res = {}
        for item in self.tree_widget._all_vars():
            name = item.data(0, self.tree_widget._N)
            val_str = item.text(1)
            if val_str == "<empty>": val_str = ""
            res[name] = _parse_value(val_str)
        return res

    def _serialize_leaf(self, item: QTreeWidgetItem) -> dict:
        return {"type": "var", "name": item.data(0, self.tree_widget._N), "value": item.text(1)}

    def get_variables(self) -> dict:
        return self.get_flat_variables()

    def refresh(self):
        """Rebuild from graph state (undo/redo)."""
        if self._in_command or not self.main_window.graph:
            return
        
        # Prioritize layout; fallback to flat variables ONLY if layout is missing
        layout = self.main_window.graph.variable_layout
        if layout is not None:
            self.set_variables(layout)
        else:
            self.set_variables(self.main_window.graph.variables)

    def set_variables(self, data: list | dict):
        self._in_command = True
        try:
            self.tree_widget.clear()
                
            def _apply(items, parent=None):
                for d in items:
                    if d.get("type") == "folder":
                        folder = self.tree_widget.add_folder(d["name"], parent)
                        folder.setExpanded(d.get("expanded", True))
                        _apply(d.get("children", []), folder)
                    else:
                        self.tree_widget.add_variable(d["name"], d.get("value", ""), parent)
            
            if isinstance(data, dict):
                for name, val in data.items():
                    display_val = str(val).lower() if isinstance(val, bool) else str(val)
                    self.tree_widget.add_variable(name, display_val, None)
            else:
                _apply(data, None)
            self.tree_widget._refresh_folder_spans()
        finally:
            self._in_command = False

    # -- handlers -------------------------------------------------------------

    def _on_add(self):
        if self._in_command:
            return
        with self.main_window.scene._undo_manager.transaction("Add Variable"):
            name = _unique_name(self.tree_widget, "new_var")

            # Default to top level
            parent = None
            sel = self.tree_widget.selectedItems()
            if sel:
                s = sel[0]
                if s.data(0, self.tree_widget._T) == "folder":
                    parent = s
                elif s.parent() and s.parent().data(0, self.tree_widget._T) == "folder":
                    parent = s.parent()

            self._in_command = True
            self.tree_widget.add_variable(name, "", parent)
            self._in_command = False
            self._sync_to_graph()

    def _on_add_variable_with_name(self, name: str):
        """Add a variable with a specific name from context menu."""
        if self._in_command:
            return
        with self.main_window.scene._undo_manager.transaction("Add Variable"):
            # Ensure name is unique
            final_name = _unique_name(self.tree_widget, name)

            # Default to top level
            parent = None
            sel = self.tree_widget.selectedItems()
            if sel:
                s = sel[0]
                if s.data(0, self.tree_widget._T) == "folder":
                    parent = s
                elif s.parent() and s.parent().data(0, self.tree_widget._T) == "folder":
                    parent = s.parent()

            self._in_command = True
            self.tree_widget.add_variable(final_name, "", parent)
            self._in_command = False

            self._sync_to_graph()

    def _on_add_folder_with_name(self, name: str):
        """Add a folder with a specific name from context menu."""
        if self._in_command:
            return
        with self.main_window.scene._undo_manager.transaction("Add Folder"):
            # Ensure name is unique within siblings
            final_name = _unique_name(self.tree_widget, name)
            
            # Default to top level
            parent = None
            sel = self.tree_widget.selectedItems()
            if sel:
                s = sel[0]
                if s.data(0, self.tree_widget._T) == "folder":
                    parent = s
                elif s.parent() and s.parent().data(0, self.tree_widget._T) == "folder":
                    parent = s.parent()
            
            self._in_command = True
            self.tree_widget.add_folder(final_name, parent)
            self._in_command = False
            
            self._sync_to_graph()

    def _on_add_to_folder(self, folder_item):
        """Add a variable directly to a specific folder."""
        if self._in_command:
            return
        with self.main_window.scene._undo_manager.transaction("Add Variable to Folder"):
            name = _unique_name(self.tree_widget, "new_var")
            
            self._in_command = True
            self.tree_widget.add_variable(name, "", folder_item)
            self._in_command = False
            self._sync_to_graph()
    
    def _on_add_subfolder(self, parent_folder):
        """Add a subfolder to a specific folder."""
        dlg = RenameDialog("New Folder", "New Folder", "Folder name:", self)
        if dlg.exec() != QDialog.Accepted:
            return
        name = dlg.get_name().strip()
        if name:
            with self.main_window.scene._undo_manager.transaction("Add Subfolder"):
                # Ensure name is unique within siblings
                final_name = _unique_name(self.tree_widget, name)
                
                self._in_command = True
                self.tree_widget.add_folder(final_name, parent_folder)
                self._in_command = False
                
                self._sync_to_graph()
    
    def _on_add_folder(self):
        """Add a folder at the top level."""
        dlg = RenameDialog("New Folder", "New Folder", "Folder name:", self)
        if dlg.exec() != QDialog.Accepted:
            return
        name = dlg.get_name().strip()
        if name:
            with self.main_window.scene._undo_manager.transaction("Add Folder"):
                self.tree_widget.add_folder(name, None)
                self._sync_to_graph()

    def _on_hierarchy_changed(self):
        if self._in_command or not self.main_window or not self.main_window.scene: return
        with self.main_window.scene._undo_manager.transaction("Reorder Variables"):
            self._sync_to_graph()

    def _on_variable_name_changed(self, old_name: str, new_name: str):
        if self._in_command or not new_name.strip():
            return
        with self.main_window.scene._undo_manager.transaction("Rename Variable"):
            final_name = _unique_name(self.tree_widget, new_name, exclude=old_name)
            for it in self.tree_widget._all_vars():
                if it.data(0, self.tree_widget._N) == old_name:
                    it.setData(0, self.tree_widget._N, final_name)
                    it.setText(0, final_name)
                    break
            # graph.variables is updated during sync
            self._propagate_variable_rename(old_name, final_name)
            self._sync_to_graph()

    def _on_edit_value(self, var_name: str, current_value: str):
        if self._in_command:
            return
        dlg = RenameDialog("Edit Variable Value", current_value, "Enter new value:", self)
        if dlg.exec() != QDialog.Accepted:
            return
        new_value = dlg.get_name()
        if new_value == current_value:
            return
        with self.main_window.scene._undo_manager.transaction("Edit Variable Value"):
            self.tree_widget.update_variable(var_name, new_value)
            self._sync_to_graph()

    # -- internals ------------------------------------------------------------

    def _sync_to_graph(self):
        if not self.main_window.graph or self._in_command:
            return
            
        self._in_command = True
        try:
            self.main_window.graph.variables = self.get_flat_variables()
            self.main_window.graph.variable_layout = self.get_hierarchy()
            
            for item in self.main_window.scene._node_items.values():
                item.refresh()
            self.main_window.scene.update()
            self.main_window.scene.graph_changed.emit()
        finally:
            self._in_command = False

    def _propagate_variable_rename(self, from_name: str, to_name: str) -> None:
        scene = self.main_window.scene
        for node in self.main_window.graph.nodes.values():
            touched = False
            for port in node.inputs.values():
                if port.port_type != PortType.ENUM or port.enum_options is not None:
                    continue
                if not port_uses_graph_variables(port):
                    continue
                if str(port.value) == str(from_name):
                    port.value = to_name
                    touched = True
            if touched and scene:
                scene._after_node_mutation(node.id)

    def _put_selected_in_folder(self, tree_widget, selected_items, folder_name):
        """Put selected items in a new folder."""
        with self.main_window.scene._undo_manager.transaction("Put Items in Folder"):
            folder = tree_widget.add_folder(folder_name)
            root = tree_widget.invisibleRootItem()
            for item in selected_items:
                if item.data(0, tree_widget._T) in ["var", "folder"]:
                    parent = item.parent() or root
                    parent.removeChild(item)
                    folder.addChild(item)
            self._sync_to_graph()


# -- helpers ------------------------------------------------------------------

def _parse_value(val_str: str) -> Any:
    """Parse string value into appropriate Python type."""
    if val_str == "<empty>":
        return ""
    try:
        if val_str.lower() in ("true", "false"):
            return val_str.lower() == "true"
        elif "." in val_str:
            return float(val_str)
        elif val_str.isdigit() or (val_str.startswith("-") and val_str[1:].isdigit()):
            return int(val_str)
        else:
            return val_str
    except Exception:
        return val_str


def _unique_name(tree: VariablesTreeWidget, base: str, exclude: str = "") -> str:
    existing = set(tree.get_variable_names())
    existing.discard(exclude)
    if base not in existing:
        return base
    counter = 1
    while f"{base}_{counter}" in existing:
        counter += 1
    return f"{base}_{counter}"


# -- panel ---------------------------------------------------------------------

class VariablesModularPanel(BasePanel):
    ID            = "VariablesDock"
    TITLE         = "Variables"
    DEFAULT_AREA  = Qt.LeftDockWidgetArea
    COLOR         = "#63c2df"  # Accent color for Variables panel

    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self._widget = VariablesBrowserWidget(main_window)
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