from __future__ import annotations
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog

from core.node import BaseNode, In, OptIn, Out
from core.drop_registry import register_drop_handler
from core.enum_providers import EnumProvider as _EnumProvider, register_enum_provider
from core.file_picker_registry import register_file_picker
from core.registry import NODE_CLASS_MAPPINGS
from gui.widgets.node_widgets import make_file_picker, make_path_editor
from gui.logger import log
from gui.menu.file_search_dialog import SubgraphSearchDialog
from AssetTree.dialogs import FileSearchDialog


class FileLoader(BaseNode):
    """Picks a project asset."""
    title = "FileLoader"
    CATEGORY = "Loaders"
    color = "#ce9178"
    locked_title = True
    default_width = 225

    asset = In("FILE", default="", allow_connection=False, editable=True, full_row=True)
    file  = Out("FILE")

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
        label_text = os.path.basename(port.value) if port.value else "Select file…"
        container, self._file_label = make_file_picker(label_text, self._show_file_dialog)
        self._asset_port = port
        return container

    def _show_file_dialog(self):
        try:
            from gui.main_window import MainWindow
            main_window = next(
                (w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow)), None
            )
            dialog = FileSearchDialog(parent=main_window, file_filter=None, title="Select File")
            if dialog.exec() == FileSearchDialog.Accepted and dialog.selected_file:
                self._set_asset(dialog.selected_file)
        except Exception:
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
        path = self.validate_file_input(asset, must_exist=True, absolute_path=True)
        return (path,)


class ToRelativePathNode(BaseNode):
    """Converts an absolute FILE path to a path relative to the graph file."""
    title = "To Relative Path"
    CATEGORY = "Loaders"
    color = "#ce9178"

    file     = In("FILE", editable=False)
    relative = Out("FILE")

    def execute(self, file: str, **kwargs):
        path = self.validate_file_input(file, must_exist=False, absolute_path=False)
        return (path,)


class ReadFileNode(BaseNode):
    """Reads and returns the raw content of a file."""
    title = "Read File"
    CATEGORY = "General"
    color = "#ce9178"

    file    = In("FILE", default="", allow_connection=True, editable=False)
    content = Out("ANY")

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


class OutputFileNode(BaseNode):
    title = "Export To File"
    CATEGORY = "General"
    color = "#7a2d2d"
    locked_title = True

    out_path = In("STRING", default="", full_row=True, allow_connection=False)
    content  = OptIn("ANY", editable=False)
    file     = Out("FILE")

    def on_property_changed(self):
        port = self.inputs.get("out_path")
        out_path = port.value if port else ""
        self.title = "Save " + os.path.basename(out_path) if out_path else "Save To File"

    def create_widget_for_port(self, port):
        if port.name != "out_path":
            return None
        container, self._path_edit = make_path_editor(
            str(port.value) if port.value else "",
            lambda: self._on_path_changed(),
            lambda: self._show_save_dialog(),
        )
        return container

    def _show_save_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(None, "Save File As", "", "All Files (*)")
        if path:
            if hasattr(self, '_path_edit'):
                try:
                    self._path_edit.setText(path)
                except RuntimeError:
                    pass
            self.inputs["out_path"].value = path
            self.on_property_changed()

    def _on_path_changed(self) -> None:
        if hasattr(self, '_path_edit'):
            try:
                self.inputs["out_path"].value = self._path_edit.text()
            except RuntimeError:
                pass
        self.on_property_changed()

    def execute(self, content, out_path: str, **kwargs):
        try:
            Path(out_path).write_text(str(content), encoding="utf-8")
            log.info(f"Written -> {out_path}")
        except Exception as exc:
            log.error(f"Error: {exc}")

        return (out_path,)


def _handle_asset_drop(scene, pos, value, modifiers) -> bool:
    ext = os.path.splitext(value)[1].lower()
    if ext in (".srcsubgraph", ".srcgraph"):
        cls = NODE_CLASS_MAPPINGS.get("SubgraphNode")
        assign_key = "graph_path"
    else:
        cls = NODE_CLASS_MAPPINGS.get("FileLoader")
        assign_key = "asset"
    if not cls:
        return False
    node = cls()
    node.graph = scene.graph
    node.title = os.path.basename(value)
    if assign_key in node.inputs:
        node.inputs[assign_key].value = value
    else:
        for key in ("asset", "path", "file"):
            if key in node.inputs:
                node.inputs[key].value = value
                break
    if hasattr(node, "on_property_changed"):
        node.on_property_changed()
    scene.add_node(node, pos)
    item = scene._node_items.get(node.id)
    if item:
        item.setSelected(True)
    return True


register_drop_handler("asset", _handle_asset_drop)


class _AssetsEnumProvider(_EnumProvider):
    def resolve(self, graph, port) -> None:
        assets = getattr(graph, "assets", None) or []
        if not assets:
            return
        ext_filter = port.enum_filter
        valid: list[str] = []
        for a in assets:
            if ext_filter and os.path.splitext(a)[1].lower() not in ext_filter:
                continue
            valid.append(os.path.normpath(str(a)).replace("\\", "/"))
        pv_raw = "" if port.value is None else str(port.value)
        if not pv_raw:
            return
        pv = os.path.normpath(pv_raw).replace("\\", "/")
        if pv in valid:
            port.value = pv
            return
        base = os.path.basename(pv)
        matches = [a for a in valid if os.path.basename(a) == base]
        if len(matches) == 1:
            port.value = matches[0]
        elif len(valid) == 1:
            port.value = valid[0]
        else:
            port.value = ""


register_enum_provider("assets", _AssetsEnumProvider())


def _asset_picker(parent, file_filter, title):
    dialog = FileSearchDialog(parent=parent, file_filter=file_filter, title=title)
    if dialog.exec() == FileSearchDialog.Accepted and dialog.selected_file:
        return dialog.selected_file
    return None


def _subgraph_picker(parent, file_filter, title):
    dialog = SubgraphSearchDialog(parent=parent)
    if dialog.exec() == SubgraphSearchDialog.Accepted and dialog.selected_file:
        return dialog.selected_file
    return None


register_file_picker("asset", _asset_picker)
register_file_picker("subgraph", _subgraph_picker)
