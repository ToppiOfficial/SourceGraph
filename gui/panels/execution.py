from __future__ import annotations
import copy
from contextlib import nullcontext
from typing import Any
import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QListWidget, QListWidgetItem, QLabel, QComboBox,
    QMenu, QAbstractItemView, QCheckBox, QListWidgetItem, QLineEdit,
    QDialog, QFormLayout, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QAction, QKeyEvent, QFont, QIcon, QPixmap, QPainter, QColor, QMouseEvent

from gui.panels.base_panel import BasePanel
from gui.dialogs import RenameDialog
from core.execution import (
    ExecutionContext, StandardExecutionEngine, ExecutionResult
)
from gui.logger import log
from PySide6.QtGui import QColor
from gui.theme import *
from gui.theme import (
    EXEC_ITEM_CHECKBOX_STYLE,
    EXEC_ITEM_TEXT_LABEL_STYLE,
    EXEC_ITEM_ORDER_LABEL_STYLE,
    EXEC_LIST_WIDGET_STYLE,
    SESSION_RENAME_EDIT_STYLE,
    SESSION_RENAME_EDIT_ERROR_STYLE
)


class ExecutionItemWidget(QWidget):
    """Custom widget for execution list items with checkbox."""
    
    name_changed = Signal(str)  # Signal emitted when name changes
    
    def __init__(self, node, node_id, index, parent=None):
        super().__init__(parent)
        self.node = node
        self.node_id = node_id
        self.index = index
        self.custom_name = ""
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(6)
        
        # Checkbox for enabling/disabling execution of this item
        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.setFixedSize(16, 16)
        self.checkbox.setStyleSheet(EXEC_ITEM_CHECKBOX_STYLE)
        layout.addWidget(self.checkbox)
        
        # Text label (non-editable)
        self.text_label = QLabel()
        display_text = self._format_display_text()
        self.text_label.setText(display_text)
        self.text_label.setStyleSheet(EXEC_ITEM_TEXT_LABEL_STYLE)
        layout.addWidget(self.text_label, 1)
        
        # Add execution order indicator
        self.order_label = QLabel()
        self.order_label.setText(f"{index + 1}")
        self.order_label.setStyleSheet(EXEC_ITEM_ORDER_LABEL_STYLE)
        self.order_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.order_label)
        
        self.setLayout(layout)
    
    def update_display_text(self):
        """Update the text label with current display text."""
        display_text = self._format_display_text()
        self.text_label.setText(display_text)
    
    def update_execution_order(self, index: int):
        """Update the execution order indicator."""
        self.index = index
        self.order_label.setText(f"{index + 1}")
    
    def _format_display_text(self) -> str:
        """Format the display text with execution order and node info."""
        node_default = self.node.title  # class-level default (e.g. "Print")
        node_class = self.node.__class__.__name__.replace("Node", "")
        node_custom = getattr(self.node, 'custom_name', None)
        node_custom = node_custom.strip() if node_custom else ""

        # Build the fixed node label: "Custom Name [Default]" or just "Default"
        if node_custom:
            node_label = f"{node_custom} [{node_default}]"
        else:
            node_label = node_default

        # Session custom name prefix
        if self.custom_name:
            return f"{self.custom_name} ({node_label})"

        # No session custom name
        if node_custom:
            return node_label  # "Custom Name [Default]"

        # Fallback: default title + class
        display_text = node_default
        if len(display_text) < 40:
            display_text += f" ({node_class})"
        return display_text

    def set_error_highlight(self, active: bool):
        color = COLOR_ERROR if active else FG_MAIN
        self.text_label.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 500; padding: 2px;")
    
    def is_checked(self) -> bool:
        return self.checkbox.isChecked()
    
    def set_checked(self, checked: bool):
        self.checkbox.setChecked(checked)


class ExecutionListWidget(QListWidget):
    delete_requested = Signal()
    check_nodes_requested = Signal(list)  # Signal for check nodes functionality
    execute_item_requested = Signal(str)  # Signal for executing single item
    rename_item_requested = Signal(str)  # Signal for renaming single item
    item_order_changed = Signal()  # Signal emitted when items are reordered
    replace_target_requested = Signal(str)  # node_id to replace

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setIconSize(QSize(16, 16))
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._current_menu = None  # Track current menu to prevent duplicates
        self.setStyleSheet(EXEC_LIST_WIDGET_STYLE)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Delete:
            self.delete_requested.emit()
        elif event.key() == Qt.Key_F2:
            # Trigger rename for the current item
            current_item = self.currentItem()
            if current_item:
                widget = self.itemWidget(current_item)
                if widget:
                    dialog = RenameDialog("Rename Execution Item", widget.custom_name, "Custom name (leave empty to clear):", self)
                    if dialog.exec() == QDialog.Accepted:
                        new_name = dialog.get_name()
                        if new_name != widget.custom_name:
                            widget.custom_name = new_name
                            widget.update_display_text()
                            widget.name_changed.emit(new_name)
            event.accept()
            return
        elif event.key() == Qt.Key_Escape:
            # Close any open context menus
            self.closePersistentEditor()
            self.clearSelection()
            # Find and close any open QMenu widgets
            from PySide6.QtWidgets import QApplication
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, QMenu) and widget.isVisible():
                    widget.close()
            event.accept()
            return
        super().keyPressEvent(event)
    
    def dropEvent(self, event):
        """Handle drop event for reordering items."""
        super().dropEvent(event)
        self.item_order_changed.emit()
    
    def _show_context_menu(self, position):
        """Show context menu with execution options."""
        # Close any existing menu first
        if self._current_menu and self._current_menu.isVisible():
            self._current_menu.close()
            return
            
        menu = QMenu(self)
        menu.setStyleSheet(MENU)
        self._current_menu = menu
        
        # Store the position for use in the execute action
        self._context_menu_position = position
        
        # Add "Rename execution" option
        rename_action = QAction("Rename execution", self)
        rename_action.triggered.connect(self._rename_item)
        menu.addAction(rename_action)

        replace_action = QAction("Replace target node", self)
        replace_action.triggered.connect(self._start_replace_target)
        menu.addAction(replace_action)

        menu.addSeparator()

        # Add "Execute this item" option
        execute_action = QAction("Execute this item", self)
        execute_action.triggered.connect(self._execute_item)
        menu.addAction(execute_action)

        menu.addSeparator()

        check_action = QAction("Check Nodes", self)
        check_action.triggered.connect(self._check_nodes)
        menu.addAction(check_action)

        menu.addSeparator()

        remove_action = QAction("Remove from Session", self)
        remove_action.triggered.connect(self.delete_requested.emit)
        menu.addAction(remove_action)
        
        # Clear reference when menu is hidden
        menu.aboutToHide.connect(lambda: setattr(self, '_current_menu', None))
        menu.exec(self.mapToGlobal(position))
    
    def _execute_item(self):
        """Execute the right-clicked item."""
        # Get the item at the stored context menu position
        item = self.itemAt(self._context_menu_position)
        
        if not item:
            # Fallback: get the first selected item
            selected_items = self.selectedItems()
            if selected_items:
                item = selected_items[0]
        
        if item:
            node_id = item.data(Qt.UserRole)
            if node_id:
                self.execute_item_requested.emit(node_id)
    
    def _rename_item(self):
        """Rename the right-clicked item using dialog."""
        # Get the item at the stored context menu position
        item = self.itemAt(self._context_menu_position)
        
        if not item:
            # Fallback: get the first selected item
            selected_items = self.selectedItems()
            if selected_items:
                item = selected_items[0]
        
        if item:
            widget = self.itemWidget(item)
            if widget:
                dialog = RenameDialog("Rename Execution Item", widget.custom_name, "Custom name (leave empty to clear):", self)
                if dialog.exec() == QDialog.Accepted:
                    new_name = dialog.get_name()
                    if new_name != widget.custom_name:
                        widget.custom_name = new_name
                        widget.update_display_text()
                        widget.name_changed.emit(new_name)
    
    def _check_nodes(self):
        """Emit signal to check/highlight selected nodes."""
        selected_items = self.selectedItems()
        if selected_items:
            node_ids = [item.data(Qt.UserRole) for item in selected_items]
            self.check_nodes_requested.emit(node_ids)

    def _start_replace_target(self):
        """Emit signal to start eyedropper mode for the right-clicked item."""
        item = self.itemAt(self._context_menu_position)
        if not item:
            selected = self.selectedItems()
            if selected:
                item = selected[0]
        if item:
            node_id = item.data(Qt.UserRole)
            if node_id:
                self.replace_target_requested.emit(node_id)

    def add_execution_item(self, node, node_id, index):
        """Add an execution item with checkbox and execution icon."""
        # Create custom widget
        widget = ExecutionItemWidget(node, node_id, index)
        
        # Create list item and set widget
        item = QListWidgetItem(self)
        item.setSizeHint(QSize(-1, 32))  # Set consistent height
        item.setData(Qt.UserRole, node_id)
        
        # Set the widget as the item widget
        self.setItemWidget(item, widget)
        
        return item, widget
    
    def get_checked_items(self) -> list[str]:
        """Get node IDs of checked items."""
        checked_ids = []
        for i in range(self.count()):
            item = self.item(i)
            widget = self.itemWidget(item)
            if widget and widget.is_checked():
                checked_ids.append(item.data(Qt.UserRole))
        return checked_ids


class ExecutionSession:
    """A session that executes specific nodes in the graph."""
    
    def __init__(self, name: str = "Session"):
        self.name = name
        self.node_ids: list[str] = []
        self.node_names: dict[str, str] = {}
        self.disabled_nodes: set[str] = set()  # unchecked nodes
        self.results: dict[str, Any] = {}

    def is_enabled(self, node_id: str) -> bool:
        return node_id not in self.disabled_nodes

    def set_enabled(self, node_id: str, enabled: bool) -> None:
        if enabled:
            self.disabled_nodes.discard(node_id)
        else:
            self.disabled_nodes.add(node_id)

    def add_node(self, node_id: str, custom_name: str = "") -> None:
        if node_id not in self.node_ids:
            self.node_ids.append(node_id)
            if custom_name:
                self.node_names[node_id] = custom_name

    def remove_node(self, node_id: str) -> None:
        if node_id in self.node_ids:
            self.node_ids.remove(node_id)
            self.node_names.pop(node_id, None)
            self.disabled_nodes.discard(node_id)

    def clear(self) -> None:
        self.node_ids.clear()
        self.node_names.clear()
        self.disabled_nodes.clear()
        self.results.clear()
        
    def set_node_name(self, node_id: str, name: str) -> None:
        """Set custom name for a node."""
        if node_id in self.node_ids:
            self.node_names[node_id] = name
            
    def get_node_name(self, node_id: str) -> str:
        """Get custom name for a node."""
        return self.node_names.get(node_id, "")


class _SessionItemsProvider:
    """Validates and fixes ports bound to graph execution sessions."""

    def resolve(self, graph, port) -> None:
        exec_data = getattr(graph, "execution_sessions", [])
        if not exec_data:
            return
        sessions_list = exec_data.get("sessions", []) if isinstance(exec_data, dict) else exec_data
        pv = str(port.value) if port.value else ""
        if not pv or "|" not in pv:
            return
        parts = pv.split("|", 1)
        if len(parts) < 2:
            return
        s_name, node_id = parts
        for s_data in sessions_list:
            if s_data.get("name") == s_name and node_id in s_data.get("node_ids", []):
                return
        matches = [s_data.get("name") for s_data in sessions_list
                   if node_id in s_data.get("node_ids", [])]
        port.value = f"{matches[0]}|{node_id}" if len(matches) == 1 else ""


class ExecutionPanel(QWidget):
    """Panel for managing execution sessions."""

    execution_started = Signal(str)  # session_name
    execution_finished = Signal(str, dict)  # session_name, results
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.graph = None
        self._scene = None
        self.sessions: dict[str, ExecutionSession] = {}
        self.current_session: ExecutionSession | None = None
        self._is_updating = False
        self._eyedropper_active = False
        self._eyedropper_target_id: str | None = None
        self._last_failed_node_id: str | None = None
        self._failed_session_items: set[str] = set()
        self._session_rename_original_name: str | None = None

        self._setup_ui()
        from core.enum_providers import register_enum_provider
        register_enum_provider("session_items", _SessionItemsProvider())

    def keyPressEvent(self, event):
        """Handle key press events, particularly Escape to close context menus."""
        if event.key() == Qt.Key_Escape:
            # Close any open context menus
            from PySide6.QtWidgets import QApplication
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, QMenu) and widget.isVisible():
                    widget.close()
            event.accept()
            return
        super().keyPressEvent(event)
    
    def contextMenuEvent(self, event):
        """Override context menu event to prevent duplicate menus."""
        # Check if there's already a menu open
        from PySide6.QtWidgets import QApplication
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QMenu) and widget.isVisible():
                event.ignore()
                return
        super().contextMenuEvent(event)
        
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # Session selector row
        session_layout = QHBoxLayout()
        session_layout.addWidget(QLabel("Session:"))
        
        self.session_combo = QComboBox()
        self.session_combo.currentTextChanged.connect(self._on_session_changed)
        self.session_combo.setStyleSheet(NODE_COMBO_STYLE)
        session_layout.addWidget(self.session_combo, 1)
        
        self.btn_new_session = QPushButton("+")
        self.btn_new_session.setToolTip("New Session")
        self.btn_new_session.setStyleSheet(BTN_STYLE)
        self.btn_new_session.setFixedSize(24, 24)
        self.btn_new_session.clicked.connect(lambda: self._new_session())
        session_layout.addWidget(self.btn_new_session)
        
        self.btn_del_session = QPushButton("-")
        self.btn_del_session.setToolTip("Delete Session")
        self.btn_del_session.setStyleSheet(BTN_STYLE)
        self.btn_del_session.setFixedSize(24, 24)
        self.btn_del_session.clicked.connect(self._delete_session)
        session_layout.addWidget(self.btn_del_session)
        
        layout.addLayout(session_layout)
        
        # Rename field row
        rename_layout = QHBoxLayout()
        self.session_rename_edit = QLineEdit()
        self.session_rename_edit.setStyleSheet(INPUT_STYLE)
        self.session_rename_edit.textEdited.connect(self._on_session_name_changed)
        self.session_rename_edit.editingFinished.connect(self._on_rename_editing_finished)
        rename_layout.addWidget(self.session_rename_edit, 1)
        
        layout.addLayout(rename_layout)
        
        # Node list for current session
        self.node_list = ExecutionListWidget()
        self.node_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.node_list.delete_requested.connect(self._remove_selected_nodes)
        self.node_list.check_nodes_requested.connect(self._check_nodes)
        self.node_list.execute_item_requested.connect(self._execute_single_item)
        self.node_list.rename_item_requested.connect(self._rename_execution_item)
        self.node_list.replace_target_requested.connect(self._start_eyedropper)
        self.node_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.node_list.setDragEnabled(True)
        self.node_list.setAcceptDrops(True)
        self.node_list.setDropIndicatorShown(True)
        self.node_list.item_order_changed.connect(self._on_item_order_changed)
        layout.addWidget(QLabel("Execution Order:"))
        layout.addWidget(self.node_list)
        
        # Execute button
        self.btn_execute = QPushButton("Execute")
        self.btn_execute.setStyleSheet(BTN_STYLE)
        self.btn_execute.clicked.connect(self._execute_current)
        layout.addWidget(self.btn_execute)
        
        # Create default session
        self._new_session("default")
        
    def set_graph(self, graph, scene=None):
        """Set the graph to execute."""
        if self._eyedropper_active:
            self._cancel_eyedropper()
        self.graph = graph
        self._scene = scene

    def refresh(self) -> None:
        """Refresh the UI from the current graph state (used by Undo/Redo)."""
        if self._is_updating or not self.graph:
            return
        # Only refresh the node list UI, don't overwrite the entire state
        self._refresh_node_list()
        
    def _sync_to_graph(self):
        """Notify the editor that the execution state has changed for undo tracking."""
        if self._scene:
            # Also update the graph's execution sessions for persistence
            self.graph.execution_sessions = self.get_project_state()

            for item in self._scene._node_items.values():
                item.refresh()

            self._scene.graph_changed.emit()

    def get_project_state(self) -> dict:
        """Return execution sessions to be saved in the project JSON."""
        state = {
            "current_session": self.session_combo.currentText(),
            "sessions": []
        }
        for name, session in self.sessions.items():
            state["sessions"].append({
                "name": name,
                "node_ids": list(session.node_ids),
                "node_names": dict(session.node_names),
                "disabled_nodes": list(session.disabled_nodes),
            })
        return state

    def set_project_state(self, state: dict):
        """Restore execution sessions from project JSON."""
        if not state:
            return

        self._is_updating = True
        self.session_combo.blockSignals(True)
        
        try:
            self.sessions.clear()
            self.session_combo.clear()

            # Handle both old (dict with 'sessions' key) and new (list of sessions) formats
            sessions_list = []
            current = None
            if isinstance(state, dict):
                sessions_list = state.get("sessions", [])
                current = state.get("current_session")
            elif isinstance(state, list):
                sessions_list = state

            for s_data in sessions_list:
                if not isinstance(s_data, dict):
                    continue
                name = str(s_data.get("name", "Session"))
                session = ExecutionSession(name)
                session.node_ids = list(s_data.get("node_ids", []))
                session.node_names = dict(s_data.get("node_names", {}))
                session.disabled_nodes = set(s_data.get("disabled_nodes", []))
                self.sessions[name] = session
                self.session_combo.addItem(name)
                
            if current and str(current) in self.sessions:
                self.session_combo.setCurrentText(str(current))
                self.current_session = self.sessions[str(current)]
            elif self.session_combo.count() == 0:
                self._new_session("default")
            else:
                self.current_session = self.sessions[self.session_combo.itemText(0)]
        finally:
            self.session_combo.blockSignals(False)
            self._is_updating = False
            
        # Ensure the list UI matches the now-restored current session
        self._refresh_node_list()

        # Sync the graph's execution sessions so SessionNodes can resolve names correctly
        if self.graph:
            self.graph.execution_sessions = self.get_project_state()

        if self.current_session:
            self.session_rename_edit.blockSignals(True)
            self.session_rename_edit.setText(self.current_session.name)
            self.session_rename_edit.blockSignals(False)
            self._reset_rename_style()

    def _new_session(self, name: str | None = None):
        if name is None:
            base = "session"
            i = 1
            name = f"{base} {i}"
            while name in self.sessions:
                i += 1
                name = f"{base} {i}"
                
        name = str(name)
        mgr = self._scene._undo_manager if (self._scene and hasattr(self._scene, "_undo_manager")) else None
        with mgr.transaction(f"New Session: {name}") if mgr else nullcontext():
            session = ExecutionSession(name)
            self.sessions[name] = session
            
            # Block signals to prevent currentTextChanged from firing with invalid values
            self.session_combo.blockSignals(True)
            self.session_combo.addItem(name)
            self.session_combo.setCurrentText(name)
            self.session_combo.blockSignals(False)
            
            self.current_session = session
            self.session_rename_edit.blockSignals(True)
            self.session_rename_edit.setText(name)
            self.session_rename_edit.blockSignals(False)
            self._sync_to_graph()
            print(f"[Session] Created new session: {name}")
        
    def _delete_session(self):
        name = self.session_combo.currentText()
        mgr = self._scene._undo_manager if (self._scene and hasattr(self._scene, "_undo_manager")) else None
        with mgr.transaction(f"Delete Session: {name}") if mgr else nullcontext():
            if name in self.sessions:
                del self.sessions[name]
                self.session_combo.removeItem(self.session_combo.currentIndex())
                self._sync_to_graph()
                
            if self.session_combo.count() == 0:
                self._new_session("default")
            
    def _on_session_changed(self, name: str):
        if not name or not isinstance(name, str) or name not in self.sessions:
            return
        self.current_session = self.sessions[name]
        self._session_rename_original_name = name
        self._refresh_node_list()
        self.session_rename_edit.blockSignals(True)
        self.session_rename_edit.setText(name)
        self.session_rename_edit.blockSignals(False)
        self._reset_rename_style()
    
    def _on_session_name_changed(self, text: str):
        new_name = text.strip()
        current_name = self.session_combo.currentText()

        if not new_name:
            self.session_rename_edit.setStyleSheet(SESSION_RENAME_EDIT_ERROR_STYLE)
            return

        if new_name in self.sessions and new_name != current_name:
            self.session_rename_edit.setStyleSheet(SESSION_RENAME_EDIT_ERROR_STYLE)
            return

        if new_name == current_name:
            self._reset_rename_style()
            return

        self._reset_rename_style()
        self._apply_session_rename_impl_no_transaction(current_name, new_name)

    def _apply_session_rename_impl_no_transaction(self, current_name: str, new_name: str):
        """Apply the rename without creating an undo transaction."""
        session = self.sessions.pop(current_name, None)
        if session:
            session.name = new_name
            self.sessions[new_name] = session
            self.session_combo.blockSignals(True)
            idx = self.session_combo.findText(current_name)
            if idx >= 0:
                self.session_combo.setItemText(idx, new_name)
                self.session_combo.setCurrentIndex(idx)
            self.session_combo.blockSignals(False)
            self._sync_to_graph()

    def _on_rename_editing_finished(self):
        current_name = self.session_combo.currentText()
        edit_text = self.session_rename_edit.text().strip()

        if not edit_text or (edit_text in self.sessions and edit_text != current_name):
            self.session_rename_edit.blockSignals(True)
            self.session_rename_edit.setText(current_name)
            self.session_rename_edit.blockSignals(False)
            self._reset_rename_style()
            return

        if self._session_rename_original_name and self._session_rename_original_name != current_name:
            mgr = self._scene._undo_manager if (self._scene and hasattr(self._scene, "_undo_manager")) else None
            with mgr.transaction(f"Rename Session: {self._session_rename_original_name} → {current_name}") if mgr else nullcontext():
                pass
            self._session_rename_original_name = current_name

    def _reset_rename_style(self):
        self.session_rename_edit.setStyleSheet(SESSION_RENAME_EDIT_STYLE)
            
    def _refresh_node_list(self):
        self.node_list.clear()
        if not self.current_session or not self.graph:
            return

        display_idx = 0
        for node_id in self.current_session.node_ids:
            node = self.graph.nodes.get(node_id)
            if node:
                custom_name = self.current_session.get_node_name(node_id)
                item, widget = self.node_list.add_execution_item(node, node_id, display_idx)
                if custom_name:
                    widget.custom_name = custom_name
                    widget.update_display_text()
                widget.update_execution_order(display_idx)
                display_idx += 1
                # Restore checked state
                widget.checkbox.blockSignals(True)
                widget.set_checked(self.current_session.is_enabled(node_id))
                widget.checkbox.blockSignals(False)
                # Persist checkbox changes to session
                widget.checkbox.toggled.connect(
                    lambda checked, nid=node_id: self._on_item_check_changed(nid, checked)
                )
                widget.name_changed.connect(
                    lambda text, nid=node_id: self._on_item_name_changed(nid, text)
                )
                
    def _on_item_name_changed(self, node_id: str, name: str):
        if self.current_session:
            self.current_session.set_node_name(node_id, name)
            self._sync_to_graph()

    def _on_item_check_changed(self, node_id: str, checked: bool):
        if self.current_session and not self._is_updating:
            self.current_session.set_enabled(node_id, checked)
            if self.graph:
                self.graph.execution_sessions = self.get_project_state()
    
    def _rename_execution_item(self, node_id: str):
        """Handle rename request from execution list."""
        if not self.current_session:
            return
            
        # Find the widget for this node_id and update its name
        for i in range(self.node_list.count()):
            item = self.node_list.item(i)
            if item and item.data(Qt.UserRole) == node_id:
                widget = self.node_list.itemWidget(item)
                if widget:
                    current_name = self.current_session.get_node_name(node_id)
                    dialog = RenameDialog("Rename Execution Item", current_name, "Custom name (leave empty to clear):", self)
                    if dialog.exec() == QDialog.Accepted:
                        new_name = dialog.get_name()
                        if new_name != current_name:
                            self.current_session.set_node_name(node_id, new_name)
                            widget.custom_name = new_name
                            widget.update_display_text()
                            self._sync_to_graph()
                break
    
    def _on_item_order_changed(self):
        """Handle item reordering in the execution list."""
        if not self.current_session:
            return
            
        # Get the new order from the list widget
        new_order = []
        for i in range(self.node_list.count()):
            item = self.node_list.item(i)
            if item:
                node_id = item.data(Qt.UserRole)
                if node_id:
                    new_order.append(node_id)
                    # Update the execution order indicator for each widget
                    widget = self.node_list.itemWidget(item)
                    if widget:
                        widget.update_execution_order(i)
        
        # Update the session's node order
        mgr = self._scene._undo_manager if (self._scene and hasattr(self._scene, "_undo_manager")) else None
        with mgr.transaction("Reorder Execution Items") if mgr else nullcontext():
            self.current_session.node_ids = new_order
            self._sync_to_graph()

    def _check_nodes(self, node_ids: list[str]):
        """Select nodes and their dependencies in the scene."""
        if not self.graph or not self._scene:
            return
            
        # Collect all nodes including dependencies
        all_node_ids = set(node_ids)
        for node_id in node_ids:
            self._add_deps_recursive(node_id, all_node_ids)
        
        # Deselect all first
        self._scene.clearSelection()
        
        # Select items in the scene
        selected_count = 0
        for node_id in all_node_ids:
            node_item = self._scene._node_items.get(node_id)
            if node_item:
                node_item.setSelected(True)
                selected_count += 1
                
        print(f"[Check Nodes] Selected {selected_count} nodes (including dependencies)")

    def _add_selected_node(self):
        if not self.current_session or not self.graph:
            return
            
        mgr = self._scene._undo_manager if (self._scene and hasattr(self._scene, "_undo_manager")) else None
        with mgr.transaction("Add to Execution") if mgr else nullcontext():
            if self._scene:
                from gui.items.node import NodeItem
                selected = [item for item in self._scene.selectedItems() 
                           if isinstance(item, NodeItem)]
                for item in selected:
                    self.current_session.add_node(item.node.id)
            else:
                for node_id in self.graph.nodes:
                    self.current_session.add_node(node_id)
            self._refresh_node_list()
            self._sync_to_graph()
        
    def _remove_selected_nodes(self):
        if not self.current_session:
            return
            
        mgr = self._scene._undo_manager if (self._scene and hasattr(self._scene, "_undo_manager")) else None
        with mgr.transaction("Remove from Execution") if mgr else nullcontext():
            for item in self.node_list.selectedItems():
                node_id = item.data(Qt.UserRole)
                self.current_session.remove_node(node_id)
            self._refresh_node_list()
            self._sync_to_graph()
        
    def _clear_session(self):
        if self.current_session:
            mgr = self._scene._undo_manager if (self._scene and hasattr(self._scene, "_undo_manager")) else None
            with mgr.transaction("Clear Execution Session") if mgr else nullcontext():
                self.current_session.clear()
                self._refresh_node_list()
                self._sync_to_graph()
            
    def eventFilter(self, obj, event):
        if not self._eyedropper_active:
            return False
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            self._cancel_eyedropper()
            return True
        if event.type() == QEvent.MouseButtonPress:
            if self._scene and self._scene.views():
                from gui.items.node import NodeItem
                view = self._scene.views()[0]
                # items() takes viewport coordinates — event.pos() is in viewport coords
                hit = next(
                    (i for i in view.items(event.pos()) if isinstance(i, NodeItem)),
                    None
                )
                if hit is not None:
                    self._finish_eyedropper(hit.node.id)
                else:
                    self._cancel_eyedropper()
            return True
        return False

    def _start_eyedropper(self, target_node_id: str):
        self._eyedropper_active = True
        self._eyedropper_target_id = target_node_id
        if self._scene and self._scene.views():
            vp = self._scene.views()[0].viewport()
            vp.setCursor(Qt.CrossCursor)
            vp.installEventFilter(self)
        log.info("[Replace] Click a node to replace — Escape to cancel")

    def _cancel_eyedropper(self):
        self._eyedropper_active = False
        self._eyedropper_target_id = None
        if self._scene and self._scene.views():
            vp = self._scene.views()[0].viewport()
            vp.unsetCursor()
            vp.removeEventFilter(self)
        log.info("[Replace] Cancelled")

    def _finish_eyedropper(self, new_node_id: str):
        old_node_id = self._eyedropper_target_id
        self._eyedropper_active = False
        self._eyedropper_target_id = None
        if self._scene and self._scene.views():
            vp = self._scene.views()[0].viewport()
            vp.unsetCursor()
            vp.removeEventFilter(self)

        if not self.current_session or old_node_id not in self.current_session.node_ids:
            return
        idx = self.current_session.node_ids.index(old_node_id)
        self.current_session.node_ids[idx] = new_node_id
        custom_name = self.current_session.node_names.pop(old_node_id, "")
        if custom_name:
            self.current_session.node_names[new_node_id] = custom_name

        new_node = self.graph.nodes.get(new_node_id) if self.graph else None
        log.info(f"[Replace] Target replaced with: {new_node.title if new_node else new_node_id}")
        self._refresh_node_list()
        self._sync_to_graph()

    def _execute_current(self):
        if not self.current_session or not self.graph:
            return
            
        # Get only checked items for execution
        checked_node_ids = self.node_list.get_checked_items()
        if not checked_node_ids:
            print("[Execution] No items checked for execution")
            return
            
        # Create a temporary session with only checked nodes
        temp_session = ExecutionSession(f"{self.current_session.name} (checked)")
        temp_session.node_ids = checked_node_ids
        self._execute_session(temp_session)
        
                
    def _execute_single_item(self, node_id: str):
        """Execute a single item by node ID."""
        if not self.graph:
            return
            
        # Create a temporary session with just this node
        temp_session = ExecutionSession(f"Single Item: {node_id}")
        temp_session.node_ids = [node_id]
        self._execute_session(temp_session)
            
    def _execute_session(self, session: ExecutionSession):
        print(f"--- Executing: {session.name} ---")
        self.execution_started.emit(session.name)

        if not session.node_ids:
            print("No nodes in session")
            return

        start_total = time.perf_counter()
        original_vars = copy.deepcopy(self.graph.variables)
        any_failed = False

        try:
            # Clear previous error highlights
            for i in range(self.node_list.count()):
                list_item = self.node_list.item(i)
                if list_item:
                    w = self.node_list.itemWidget(list_item)
                    if w:
                        w.set_error_highlight(False)

            engine = StandardExecutionEngine()
            # Successful results shared across items (cache deps that already ran OK)
            global_ok: dict[str, ExecutionResult] = {}
            session.results = {}

            def on_error(nid, msg):
                node = self.graph.nodes.get(nid)
                log.error(f"[{node.title if node else nid}] {msg}")
                if self._scene:
                    scene_item = self._scene._node_items.get(nid)
                    if scene_item:
                        scene_item.update()

            context = ExecutionContext(on_node_error=on_error)

            for session_item_id in session.node_ids:
                item_node = self.graph.nodes.get(session_item_id)
                if item_node is None:
                    continue

                # Collect and sort this item's full dependency subtree
                item_deps = self._collect_with_deps([session_item_id])
                sorted_deps = self._sort_by_deps(item_deps)

                # Reset execution times for nodes not yet cached from a previous item
                for dep_id in sorted_deps:
                    if dep_id not in global_ok:
                        dep_node = self.graph.nodes.get(dep_id)
                        if dep_node:
                            dep_node.last_execution_time = None

                # Execute subtree, stopping at first failure
                item_results = dict(global_ok)
                failed_dep: str | None = None

                for dep_id in sorted_deps:
                    if dep_id in item_results:
                        continue  # already succeeded for a previous item
                    res = engine.execute_node(dep_id, self.graph, context, item_results)
                    item_results[dep_id] = res
                    if not res.success:
                        failed_dep = dep_id
                        break  # stop this item's subtree

                if failed_dep is not None:
                    any_failed = True
                    self._failed_session_items.add(session_item_id)
                    self._highlight_failed_item(session_item_id)
                    dep_node = self.graph.nodes.get(failed_dep)
                    dep_title = dep_node.title if dep_node else failed_dep
                    log.error(f"[{item_node.title}] Execution failed (caused by: {dep_title})")
                else:
                    # Promote this item's results to the global cache
                    for k, v in item_results.items():
                        global_ok.setdefault(k, v)
                    # Log this item's outputs
                    item_result = item_results.get(session_item_id)
                    if item_result:
                        session.results[session_item_id] = item_result.outputs
                        for out_name, out_val in item_result.outputs.items():
                            print(f"[{item_node.title}] {out_name}: {out_val}")

            end_total = time.perf_counter()
            total_time = end_total - start_total
            unit = getattr(self.graph, 'time_unit', 'ms')
            disp_time = total_time * 1000 if unit == "ms" else total_time
            msg = (f"Execution complete with errors in {disp_time:.4f}{unit}"
                   if any_failed else
                   f"Execution complete in {disp_time:.4f}{unit}")
            print(msg)
            if self._scene and self._scene.views():
                self._scene.views()[0].show_notification(msg, is_error=any_failed)

            self.execution_finished.emit(session.name, session.results)
            print(f"--- {session.name} complete ---")

        except Exception as e:
            log.error(f"Execution Error: {e}")
            if self._scene and self._scene.views():
                self._scene.views()[0].show_notification(f"Execution Error: {e}", is_error=True)
        finally:
            self.graph.variables.clear()
            self.graph.variables.update(original_vars)
            self.refresh()
            for failed_id in self._failed_session_items:
                self._highlight_failed_item(failed_id)
            self._failed_session_items.clear()
            if self._scene:
                self._scene.update()
            try:
                from PySide6.QtWidgets import QApplication
                for w in QApplication.topLevelWidgets():
                    if hasattr(w, 'panel_manager'):
                        gmp = w.panel_manager.get_panel("GraphMapDock")
                        if gmp and hasattr(gmp, 'update_execution_errors'):
                            gmp.update_execution_errors()
                        break
            except Exception:
                pass
                
    def _highlight_failed_item(self, node_id: str):
        for i in range(self.node_list.count()):
            item = self.node_list.item(i)
            if item and item.data(Qt.UserRole) == node_id:
                widget = self.node_list.itemWidget(item)
                if widget:
                    widget.set_error_highlight(True)
                break

    def _collect_with_deps(self, node_ids: list[str]) -> set[str]:
        """Collect all nodes including dependencies, skipping stale IDs."""
        result = {nid for nid in node_ids if nid in self.graph.nodes}
        for node_id in list(result):
            self._add_deps_recursive(node_id, result)
        return result

    def _add_deps_recursive(self, node_id: str, collected: set[str]):
        """Recursively add dependency nodes."""
        for conn in self.graph.connections:
            if conn.dst_node == node_id:
                if conn.src_node not in collected and conn.src_node in self.graph.nodes:
                    collected.add(conn.src_node)
                    self._add_deps_recursive(conn.src_node, collected)

    # Resource-based dependencies (e.g., Variable writers for a reader)
        node = self.graph.nodes.get(node_id)
        if node:
            for res in node.get_reads():
                for other_id, other_node in self.graph.nodes.items():
                    if other_id != node_id and res in other_node.get_writes():
                        if other_id not in collected:
                            collected.add(other_id)
                            self._add_deps_recursive(other_id, collected)
                    
    def _sort_by_deps(self, node_ids: set[str]) -> list[str]:
        """Sort nodes so dependencies come first."""
        # Simple topological sort
        in_degree = {nid: 0 for nid in node_ids}
        deps = {nid: [] for nid in node_ids}
        
        for conn in self.graph.connections:
            if conn.dst_node in node_ids and conn.src_node in node_ids:
                deps[conn.src_node].append(conn.dst_node)
                in_degree[conn.dst_node] += 1

        resource_writers: dict[str, list[str]] = {}
        for nid in node_ids:
            node = self.graph.nodes.get(nid)
            if node:
                for res in node.get_writes():
                    resource_writers.setdefault(res, []).append(nid)

        for nid in node_ids:
            node = self.graph.nodes.get(nid)
            if node:
                for res in node.get_reads():
                    for w_nid in resource_writers.get(res, []):
                        if w_nid != nid and nid not in deps[w_nid]:
                            deps[w_nid].append(nid)
                            in_degree[nid] += 1
                
        # Kahn's algorithm
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        result = []
        
        while queue:
            nid = queue.pop(0)
            result.append(nid)
            for dep in deps[nid]:
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)
                    
        # Add any remaining (shouldn't happen in DAG)
        for nid in node_ids:
            if nid not in result:
                result.append(nid)
                
        return result

class ExecutionModularPanel(BasePanel):
    ID = "ExecutionDock"
    TITLE = "Execution"
    DEFAULT_AREA = Qt.RightDockWidgetArea

    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self._widget = ExecutionPanel(main_window)
        self.setWidget(self._widget)

    def setup(self) -> None:
        self._widget.set_graph(self.main_window.graph, self.main_window.scene)
        # Connect to graph changes so Undo/Redo of other actions (like node deletion) 
        # are reflected in the execution list.
        sc = self.main_window.scene
        if sc:
            sc.graph_changed.connect(self._widget.refresh)

    def update_context(self, graph, scene) -> None:
        self._widget.set_graph(graph, scene)
        if self._active_scene:
            try: self._active_scene.graph_changed.disconnect(self._widget.refresh)
            except (TypeError, RuntimeError): pass
            
        self._active_scene = scene
        scene.graph_changed.connect(self._widget.refresh)
        self._widget.refresh()