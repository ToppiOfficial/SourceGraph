from __future__ import annotations
from PySide6.QtWidgets import QLineEdit
from gui.theme import NODE_WIDGET_STYLE, EDIT_STYLE


def make_string_canvas_widget(port, parent=None) -> QLineEdit:
    edit = QLineEdit(parent)
    edit.setFixedHeight(22)
    edit.setStyleSheet(NODE_WIDGET_STYLE)
    v = port.value
    val_str = f"{v:g}" if isinstance(v, float) else str(v) if v is not None else ""
    edit.setText(val_str)
    edit.setProperty("original_val", port.value)
    return edit


def make_string_inspector_widget(port, on_commit=None) -> QLineEdit:
    v = port.value
    val_str = f"{v:g}" if isinstance(v, float) else str(v) if v is not None else ""
    edit = QLineEdit(val_str)
    edit.setStyleSheet(EDIT_STYLE)
    edit.setProperty("original_val", port.value)

    def _on_finished():
        new_text = edit.text()
        old_val = edit.property("original_val")
        if str(old_val if old_val is not None else "") == new_text:
            return
        edit.setProperty("original_val", new_text)
        if on_commit is not None:
            on_commit(new_text)
        else:
            port.value = new_text

    edit.editingFinished.connect(_on_finished)
    return edit
