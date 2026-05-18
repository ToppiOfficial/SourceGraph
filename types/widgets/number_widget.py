from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton
from PySide6.QtCore import Qt
from gui.theme import NUMBER_INPUT_STYLE, NODE_NUMBER_BTN_STYLE, EDIT_STYLE

def make_number_canvas_widget(port, parent=None) -> QWidget:
    container = QWidget(parent)
    container.setFixedHeight(22)
    container.setObjectName("NumberInputContainer")
    container.setStyleSheet(NUMBER_INPUT_STYLE)

    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    btn_minus = QPushButton("-", container)
    btn_minus.setFixedSize(20, 20)
    btn_minus.setStyleSheet(NODE_NUMBER_BTN_STYLE)
    btn_minus.setFocusPolicy(Qt.NoFocus)

    edit = QLineEdit(container)
    edit.setFixedHeight(20)
    edit.setStyleSheet(
        "QLineEdit { background: transparent; border: none; font-size: 11px; padding: 0px; }"
    )
    edit.setAlignment(Qt.AlignCenter)

    v = port.value
    val_str = f"{v:g}" if isinstance(v, float) else str(v) if v is not None else ""
    edit.setText(val_str)
    edit.setProperty("original_val", port.value)

    btn_plus = QPushButton("+", container)
    btn_plus.setFixedSize(20, 20)
    btn_plus.setStyleSheet(NODE_NUMBER_BTN_STYLE)
    btn_plus.setFocusPolicy(Qt.NoFocus)

    layout.addWidget(btn_minus)
    layout.addWidget(edit)
    layout.addWidget(btn_plus)

    container.setProperty("widget_type", "number")
    container.number_edit = edit
    container.btn_minus = btn_minus
    container.btn_plus = btn_plus
    container.refresh_value = lambda v, _e=edit: _e.setText(
        f"{v:g}" if isinstance(v, float) else str(v) if v is not None else ""
    )
    return container


def make_number_inspector_widget(port, on_commit=None) -> QLineEdit:
    v = port.value
    val_str = f"{v:g}" if isinstance(v, float) else str(v) if v is not None else ""
    edit = QLineEdit(val_str)
    edit.setStyleSheet(EDIT_STYLE)
    edit.setProperty("original_val", port.value)

    def _on_finished():
        new_text = edit.text()
        old_val = edit.property("original_val")
        try:
            if port.port_type == "float":
                if abs(float(old_val or 0) - float(new_text or 0)) < 1e-7:
                    return
                new_val = float(new_text)
            else:
                if int(old_val or 0) == int(new_text or 0):
                    return
                new_val = int(new_text)
        except (ValueError, TypeError):
            return
        edit.setProperty("original_val", new_text)
        if on_commit is not None:
            on_commit(new_val)
        else:
            port.value = new_val

    edit.editingFinished.connect(_on_finished)
    return edit
