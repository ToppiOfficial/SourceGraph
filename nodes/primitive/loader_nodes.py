from __future__ import annotations
import os
from core.node import BaseNode
from pathlib import Path


class FileLoader(BaseNode):
    """Picks a project asset."""
    title = "FileLoader"
    CATEGORY = "Primitives"
    color = "#ce9178"
    locked_title = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset": ("FILE", {
                    "default": "",
                    "allow_connection": False,
                    "editable": True,
                    "full_row": True,
                }),
            }
        }

    RETURN_TYPES = ("FILE",)
    RETURN_NAMES = ("file",)

    def on_property_changed(self):
        input_port = self.inputs.get("asset")
        raw_path = input_port.value if input_port else ""

        self.error_msg = None
        if raw_path:
            resolved_path = self.resolve_path(raw_path)
            if not os.path.exists(resolved_path):
                self.error_msg = f"File missing: {os.path.basename(raw_path)}"

            display_path = raw_path
            if self.graph and self.graph.file_path:
                try:
                    rel = os.path.relpath(resolved_path, self.graph.file_path.parent).replace("\\", "/")
                    if not rel.startswith(".."):
                        display_path = rel
                except (ValueError, TypeError):
                    pass

            self.title = os.path.basename(display_path)
            self.outputs["file"].label = display_path
        else:
            self.title = "FileLoader"
            self.outputs["file"].label = ""

        if hasattr(self, '_file_label'):
            try:
                self._file_label.setText(os.path.basename(raw_path) if raw_path else "Select file…")
            except RuntimeError:
                pass

    def create_widget_for_port(self, port):
        if port.name != "asset":
            return None

        from PySide6.QtWidgets import QPushButton, QHBoxLayout, QWidget, QLabel
        from gui.theme import BTN_STYLE

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        from gui.theme import NODE_FILE_LABEL_STYLE
        self._file_label = QLabel(os.path.basename(port.value) if port.value else "Select file…")
        self._file_label.setStyleSheet(NODE_FILE_LABEL_STYLE)
        layout.addWidget(self._file_label, 1)

        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(24)
        browse_btn.setStyleSheet(BTN_STYLE)
        browse_btn.clicked.connect(self._show_file_dialog)
        layout.addWidget(browse_btn)

        self._asset_port = port
        return container
    
    def _show_file_dialog(self):
        try:
            from gui.menu.file_search_dialog import FileSearchDialog
            from PySide6.QtWidgets import QApplication
            from gui.main_window import MainWindow
            main_window = next(
                (w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow)), None
            )
            dialog = FileSearchDialog(parent=main_window, file_filter=None, title="Select File")
            if dialog.exec() == FileSearchDialog.Accepted and dialog.selected_file:
                self._set_asset(dialog.selected_file)
        except Exception:
            from PySide6.QtWidgets import QFileDialog
            path, _ = QFileDialog.getOpenFileName(None, "Select File", "", "All Files (*)")
            if path:
                self._set_asset(path)

    def _set_asset(self, path: str) -> None:
        if hasattr(self, '_asset_port'):
            self._asset_port.value = path
        if hasattr(self, '_file_label'):
            try:
                self._file_label.setText(os.path.basename(path))
            except RuntimeError:
                pass
        self.on_property_changed()
        if self.graph:
            self.graph.commit_change("Change File")
            scene = getattr(self.graph, '_scene_ref', lambda: None)()
            if scene:
                item = getattr(scene, '_node_items', {}).get(self.id)
                if item:
                    item.refresh()

    def execute(self, asset: str, **kwargs):
        path = self.validate_file_input(asset, must_exist=True)
        return (path,)


class VariableOutNode(BaseNode):
    """Outputs graph.variables[var_name]."""
    title = "Get Variable"
    CATEGORY = "General"
    color = "#b4629d"
    locked_title = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "var_name": ("ENUM", {
                    "default": "",
                    "allow_connection": False,
                    "graph_enum": "variables",
                    "label": "variable",
                }),
            }
        }

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("value",)

    def get_reads(self) -> set[str]:
        p = self.inputs.get("var_name")
        return {f"var:{p.value}"} if p and p.value else set()

    def on_property_changed(self):
        port = self.inputs.get("var_name")
        # Update title to clearly indicate it's a GET node
        var_name = str(port.value) if port and port.value else "..."
        self.title = f"GET {var_name}"

    def execute(self, var_name: str, **kwargs):
        val = None
        if self.graph and var_name:
            val = self.graph.variables.get(var_name)
        if val is None or (isinstance(val, str) and not val.strip()):
            self.fail(f"Variable '{var_name}' is empty or unset")
        return (val,)


class VariableInNode(BaseNode):
    """Writes new_value into graph.variables[var_name] during execution."""
    title = "Set Variable"
    CATEGORY = "General"
    color = "#b4629d"
    locked_title = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "var_name": ("ENUM", {
                    "default": "",
                    "allow_connection": True,
                    "graph_enum": "variables",
                    "label": "variable",
                }),
            },
            "optional": {
                "new_value": ("*", {"editable": False,}),
            }
        }

    RETURN_TYPES = ()

    def get_writes(self) -> set[str]:
        p = self.inputs.get("var_name")
        return {f"var:{p.value}"} if p and p.value else set()

    def on_property_changed(self):
        port = self.inputs.get("var_name")
        var_name = str(port.value) if port and port.value else "..."
        self.title = f"SET {var_name}"

    def execute(self, var_name: str, **kwargs):
        new_value = kwargs.get("new_value")
        if self.graph and var_name and var_name in self.graph.variables:
            # Only update if a non-empty value was actually provided via connection or widget
            if new_value is not None and (not isinstance(new_value, str) or new_value.strip()):
                self.graph.variables[var_name] = new_value
        return {}


class SessionNode(BaseNode):
    """Outputs the name of a selected execution session."""
    title = "Session"
    CATEGORY = "General"
    color = "#6272a4"
    locked_title = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "session_name": ("STRING", {
                    "default": "",
                    "allow_connection": False,
                    "full_row": True,
                }),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("session",)

    def on_property_changed(self):
        port = self.inputs.get("session_name")
        name = port.value if port and port.value else ""
        self.title = name if name else "Session"
        if hasattr(self, '_session_label'):
            try:
                self._session_label.setText(name if name else "Select session…")
            except RuntimeError:
                pass

    def create_widget_for_port(self, port):
        if port.name != "session_name":
            return None

        from PySide6.QtWidgets import QPushButton, QHBoxLayout, QWidget, QLabel
        from gui.theme import BTN_STYLE, NODE_FILE_LABEL_STYLE

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._session_label = QLabel(port.value if port.value else "Select session…")
        self._session_label.setStyleSheet(NODE_FILE_LABEL_STYLE)
        layout.addWidget(self._session_label, 1)

        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(24)
        browse_btn.setStyleSheet(BTN_STYLE)
        browse_btn.clicked.connect(self._show_session_dialog)
        layout.addWidget(browse_btn)

        self._session_name_port = port
        return container

    def _show_session_dialog(self):
        from gui.menu.file_search_dialog import SessionSearchDialog
        from PySide6.QtWidgets import QApplication
        from gui.main_window import MainWindow
        main_window = next(
            (w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow)), None
        )
        dialog = SessionSearchDialog(parent=main_window)
        if dialog.exec() == SessionSearchDialog.Accepted and dialog.selected_session:
            self._set_session(dialog.selected_session)

    def _set_session(self, name: str) -> None:
        if hasattr(self, '_session_name_port'):
            self._session_name_port.value = name
        if hasattr(self, '_session_label'):
            try:
                self._session_label.setText(name)
            except RuntimeError:
                pass
        self.on_property_changed()
        if self.graph:
            self.graph.commit_change("Change Session")
            scene = getattr(self.graph, '_scene_ref', lambda: None)()
            if scene:
                item = getattr(scene, '_node_items', {}).get(self.id)
                if item:
                    item.refresh_ports()

    def execute(self, session_name: str, **kwargs):
        return (session_name,)


class ReadFile(BaseNode):
    """Reads and returns the raw content of a file."""
    title = "ReadFile"
    CATEGORY = "General"
    color = "#ce9178"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "file": ("FILE", {
                    "default": "",
                    "allow_connection": True,
                    "editable": False,
                }),
            }
        }

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("content",)

    def execute(self, file: str, **kwargs):
        path = self.resolve_path(file)
        if not path:
            self.fail("File path is empty.")
        if not os.path.exists(path):
            self.fail(f"File not found: {path}")
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return (f.read(),)
        except (UnicodeDecodeError, UnicodeError):
            with open(path, 'rb') as f:
                return (f.read(),)
            

class OutputToFileNode(BaseNode):
    title = "Save To File"
    CATEGORY = "General"
    color = "#7a2d2d"
    locked_title = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "out_path": ("STRING", {"default": "", "full_row": True, "allow_connection": False}),
                "content": ("*", {"editable": False}),
            }
        }

    RETURN_TYPES = ()
    RETURN_NAMES = ()

    def on_property_changed(self):
        port = self.inputs.get("out_path")
        out_path = port.value if port else ""

        if out_path:
            self.title = "Save " + os.path.basename(out_path)
        else:
            self.title = "Save To File"

    def create_widget_for_port(self, port):
        if port.name != "out_path":
            return None

        from PySide6.QtWidgets import QPushButton, QHBoxLayout, QWidget, QLineEdit
        from gui.theme import BTN_STYLE, NODE_WIDGET_STYLE

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(2)

        # Text edit for the file path
        path_edit = QLineEdit()
        path_edit.setStyleSheet(NODE_WIDGET_STYLE)
        path_edit.setText(str(port.value) if port.value else "")
        path_edit.editingFinished.connect(lambda: self._on_path_changed(path_edit))
        layout.addWidget(path_edit, 1)

        # Save file dialog button
        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(24)
        browse_btn.setStyleSheet(BTN_STYLE)
        browse_btn.clicked.connect(lambda: self._show_save_dialog(path_edit))
        layout.addWidget(browse_btn)

        self._path_edit = path_edit
        return container

    def _show_save_dialog(self, path_edit: QLineEdit) -> None:
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getSaveFileName(None, "Save File As", "", "All Files (*)")
        if path:
            path_edit.setText(path)
            self.inputs["out_path"].value = path
            self.on_property_changed()

    def _on_path_changed(self, path_edit: QLineEdit) -> None:
        self.inputs["out_path"].value = path_edit.text()
        self.on_property_changed()

    def execute(self, content, out_path: str, **kwargs):
        from gui.logger import log
        try:
            Path(out_path).write_text(str(content), encoding="utf-8")
            log.info(f"Written → {out_path}")
        except Exception as exc:
            log.error(f"Error: {exc}")