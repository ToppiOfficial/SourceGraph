from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QComboBox,
    QScrollArea,
    QFileDialog,
)
from PySide6.QtCore import Qt

from core.node import port_uses_graph_variables, PortType
from PySide6.QtGui import QColor
from gui.theme import *
from gui.items.node import NodeItem
from gui.panels.base_panel import BasePanel

if TYPE_CHECKING:
    from gui.main_window import MainWindow

def _populate_asset_combo(combo: QComboBox, port, graph) -> None:
    assets = getattr(graph, "assets", []) or []
    ext_filter = port.enum_filter
    for asset_path in assets:
        if ext_filter and os.path.splitext(asset_path)[1].lower() not in ext_filter:
            continue
        combo.addItem(os.path.basename(asset_path), asset_path)


def _populate_variable_combo(combo: QComboBox, graph) -> None:
    for var_name in (getattr(graph, "variables", {}) or {}).keys():
        combo.addItem(var_name, var_name)


_EDITABLE = {PortType.STRING, PortType.INT, PortType.FLOAT, PortType.BOOL, PortType.ENUM, PortType.FILE}


def _validate_port_text(port_type: PortType, text: str) -> str | None:
    if not text:
        return None
    try:
        if port_type == PortType.INT:
            int(text)
        elif port_type == PortType.FLOAT:
            float(text)
        elif port_type == PortType.BOOL:
            if text.lower() not in ("true", "1", "yes", "false", "0", "no"):
                raise ValueError
    except ValueError:
        return f"'{text}' is not a valid {port_type.value}"
    return None


class SelectedNodePanel(QWidget):
    """Edits the single selected node's title (if allowed) and disconnected inputs."""

    def __init__(self, main_window: MainWindow, parent=None) -> None:
        super().__init__(parent)
        self.main_window = main_window
        self._item: NodeItem | None = None
        self._title_edit: QLineEdit | None = None
        self._suppress_refresh = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        self._subtitle = QLabel("")
        self._subtitle.setStyleSheet(f"color:{FG_DIM}; font-size:14px;")
        self._subtitle.setWordWrap(True)
        outer.addWidget(self._subtitle)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)

        self._body = QWidget()
        self._rows = QVBoxLayout(self._body)
        self._rows.setSpacing(6)
        self._rows.addStretch()
        self._scroll.setWidget(self._body)
        outer.addWidget(self._scroll, 1)

    def refresh(self) -> None:
        if self._suppress_refresh:
            return
        scene = self.main_window.scene
        try:
            # Safety check: avoid crash if the C++ scene object was already deleted
            selected = [i for i in scene.selectedItems() if isinstance(i, NodeItem)]
        except RuntimeError:
            return
            
        if len(selected) != 1:
            self._build_empty(len(selected))
            return
        self._build_for_node(selected[0])

    def _build_empty(self, n_selected: int) -> None:
        self._item = None
        self._clear_rows()
        if n_selected == 0:
            self._subtitle.setText("Select a single node to edit its properties here.")
        else:
            self._subtitle.setText("Select only one node to use the inspector.")

    def _clear_rows(self) -> None:
        while self._rows.count() > 1:
            item = self._rows.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _build_for_node(self, item: NodeItem) -> None:
        self._item = item
        node = item.node
        self._clear_rows()

        self._subtitle.setText(f"{node.__class__.__name__}  ·  {node.id[:8]}…")

        title_row = QWidget()
        tl = QHBoxLayout(title_row)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.addWidget(QLabel("Title"))
        if getattr(node, "locked_title", False):
            tl.addWidget(QLabel(node.display_name), 1)
        else:
            self._title_edit = QLineEdit(node.display_name)
            self._title_edit.setStyleSheet(EDIT_STYLE)
            self._title_edit.editingFinished.connect(self._on_title_finished)
            tl.addWidget(self._title_edit, 1)
        self._rows.insertWidget(0, title_row)

        scene = self.main_window.scene
        graph = scene.graph
        insert_at = 1
        for pname, port in node.inputs.items():
            if not port.display_in_inspector:
                continue
            if not port.editable and port.port_type not in _EDITABLE:
                continue
            conn = scene.graph.get_input_connection(node.id, pname)
            row = QWidget()
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)
            lbl = QLabel(port.label or pname)
            lbl.setMinimumWidth(72)
            lbl.setStyleSheet(f"color:{FG_MAIN};")
            rl.addWidget(lbl)

            custom_w = None
            if not conn and hasattr(node, 'create_widget_for_port'):
                custom_w = node.create_widget_for_port(port)
            if custom_w is not None:
                rl.addWidget(custom_w, 1)
                self._rows.insertWidget(insert_at, row)
                insert_at += 1
                continue

            if conn:
                src = graph.nodes.get(conn.src_node)
                hint = f"← {src.title if src else conn.src_node}:{conn.src_port}"
                le = QLabel(hint)
                le.setStyleSheet(f"color:{FG_DIMMER};")
                le.setWordWrap(True)
                rl.addWidget(le, 1)
            elif not port.editable:
                le = QLabel("(Connection Required)")
                le.setStyleSheet(f"color:{FG_DIMMER}; font-style: italic;")
                rl.addWidget(le, 1)
            elif port.port_type in (PortType.ENUM, PortType.BOOL):
                combo = QComboBox()
                combo.setStyleSheet(NODE_COMBO_STYLE)

                if port.port_type == PortType.BOOL:
                    combo.addItem("True", True)
                    combo.addItem("False", False)
                    
                    raw = port.value
                    is_true = str(raw).lower() in ("true", "1", "yes")
                    combo.setCurrentIndex(0 if is_true else 1)
                elif port.enum_options is not None:
                    for opt in port.enum_options:
                        combo.addItem(opt, opt)
                    
                    raw = port.value
                    val_str = (
                        str(raw).lower()
                        if isinstance(raw, bool)
                        else (str(raw) if raw is not None else "")
                    )
                    idx = combo.findData(val_str)
                    if idx < 0:
                        idx = combo.findText(val_str)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                else:
                    if port_uses_graph_variables(port):
                        _populate_variable_combo(combo, graph)
                    else:
                        _populate_asset_combo(combo, port, graph)

                    pv = "" if port.value is None else str(port.value)
                    idx = combo.findData(pv)
                    if idx < 0 and pv:
                        norm_val = os.path.normpath(pv).replace("\\", "/")
                        for i in range(combo.count()):
                            d = combo.itemData(i)
                            if d is not None and os.path.normpath(str(d)).replace("\\", "/") == norm_val:
                                idx = i
                                break
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                combo.activated.connect(
                    lambda _i, p=pname, c=combo: self._on_combo_activated(p, c)
                )
                rl.addWidget(combo, 1)
            elif port.port_type == PortType.FILE:
                edit = QLineEdit(str(port.value or ""))
                edit.setStyleSheet(EDIT_STYLE)
                edit.setProperty("port_name", pname)
                edit.setProperty("original_val", port.value)
                edit.editingFinished.connect(lambda e=edit: self._on_lineedit_finished(e))
                btn = QPushButton("…")
                btn.setFixedWidth(28)
                btn.clicked.connect(lambda _=False, e=edit, pn=pname: self._browse_file(pn, e))
                rl.addWidget(edit, 1)
                rl.addWidget(btn)
            elif port.port_type in (PortType.STRING, PortType.INT, PortType.FLOAT):
                v = port.value
                val_str = f"{v:g}" if isinstance(v, float) else str(v) if v is not None else ""
                edit = QLineEdit(val_str)
                edit.setStyleSheet(EDIT_STYLE)
                edit.setProperty("port_name", pname)
                edit.setProperty("original_val", port.value)
                edit.editingFinished.connect(lambda e=edit: self._on_lineedit_finished(e))
                rl.addWidget(edit, 1)
            else:
                le = QLabel("(Connection Required)")
                le.setStyleSheet(f"color:{FG_DIMMER}; font-style: italic;")
                rl.addWidget(le, 1)

            self._rows.insertWidget(insert_at, row)
            insert_at += 1

    def _on_title_finished(self) -> None:
        if not self._item or not self._title_edit:
            return
        new_t = self._title_edit.text().strip()
        
        # Check if anything actually changed
        current_display = self._item.node.display_name
        if new_t == current_display:
            return
            
        # If empty, clear custom name to revert to default
        if not new_t:
            self._item.node.custom_name = None
        # Otherwise, set the custom name
        else:
            self._item.node.custom_name = new_t

        self._suppress_refresh = True
        try:
            # Update the node item display
            self._item.update()
            
            # Mark graph as changed
            if self.main_window.scene:
                self.main_window.scene.graph_changed.emit()
        finally:
            self._suppress_refresh = False

    def _on_lineedit_finished(self, edit: QLineEdit) -> None:
        pname = edit.property("port_name")
        if not pname or not self._item:
            return
        port = self._item.node.inputs.get(pname)
        if not port:
            return
        new_val = edit.text()
        old_val = edit.property("original_val")
        try:
            if port.port_type == PortType.FLOAT:
                is_same = abs(float(port.value or 0) - float(new_val or 0)) < 1e-7
            elif port.port_type == PortType.INT:
                is_same = int(port.value or 0) == int(new_val or 0)
            else:
                is_same = str(port.value) == new_val
        except (ValueError, TypeError):
            is_same = str(port.value) == new_val
        if is_same:
            return
        err = _validate_port_text(port.port_type, new_val)
        self._item.node.error_msg = err
        if err:
            from gui.logger import log
            log.error(f"[{self._item.node.title}] {err}")
            return

        self._suppress_refresh = True
        try:
            from gui.node_editor import PropertyCommand
            self.main_window.scene.undo_stack.push(PropertyCommand(self._item, pname, old_val, new_val))
        finally:
            self._suppress_refresh = False
        edit.setProperty("original_val", new_val)

    def _on_combo_activated(self, pname: str, combo: QComboBox) -> None:
        if not self._item:
            return
        port = self._item.node.inputs.get(pname)
        if not port:
            return
        new_val = combo.itemData(combo.currentIndex())
        if port.value == new_val:
            return

        self._suppress_refresh = True
        try:
            from gui.node_editor import PropertyCommand
            self.main_window.scene.undo_stack.push(
                PropertyCommand(self._item, pname, port.value, new_val)
            )
        finally:
            self._suppress_refresh = False

    def _browse_file(self, pname: str, edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "All Files (*)")
        if path and self._item:
            port = self._item.node.inputs.get(pname)
            edit.setProperty("original_val", port.value if port else None)
            edit.setText(path)
            self._on_lineedit_finished(edit)

class NodeInspectorModularPanel(BasePanel):
    ID = "NodeInspectorDock"
    TITLE = "Node Inspector"
    DEFAULT_AREA = Qt.RightDockWidgetArea

    def __init__(self, main_window: MainWindow) -> None:
        super().__init__(main_window)
        self._widget = SelectedNodePanel(main_window)
        self.setWidget(self._widget)

    def setup(self) -> None:
        """Connect the inspector to the scene's selection and change signals."""
        scene = self.main_window.scene
        if scene:
            # Update whenever selection changes
            scene.selectionChanged.connect(self._widget.refresh)
            # Update when the graph structure or values change
            scene.graph_changed.connect(self._widget.refresh)
        self._widget.refresh()

    def update_context(self, graph, scene) -> None:
        if self._active_scene:
            try:
                self._active_scene.selectionChanged.disconnect(self._widget.refresh)
                self._active_scene.graph_changed.disconnect(self._widget.refresh)
            except (TypeError, RuntimeError): pass
            
        self._active_scene = scene
        scene.selectionChanged.connect(self._widget.refresh)
        scene.graph_changed.connect(self._widget.refresh)
        self._widget.refresh()