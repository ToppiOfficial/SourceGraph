from __future__ import annotations
from PySide6.QtWidgets import QPushButton
from PySide6.QtCore import Qt
from sourcegraph.gui.theme import NODE_BOOL_STYLE


def make_bool_canvas_widget(port, parent=None) -> QPushButton:
    raw = port.value
    is_true = str(raw).lower() in ("true", "1", "yes")
    btn = QPushButton(parent)
    btn.setFixedHeight(20)
    btn.setText("True" if is_true else "False")
    btn.setStyleSheet(NODE_BOOL_STYLE)
    btn.setFocusPolicy(Qt.NoFocus)
    btn.refresh_value = lambda v, _b=btn: _b.setText(
        "True" if str(v).lower() in ("true", "1", "yes") else "False"
    )
    return btn


def make_bool_inspector_widget(port, on_commit=None) -> QPushButton:
    raw = port.value
    is_true = str(raw).lower() in ("true", "1", "yes") if raw is not None else False
    btn = QPushButton("True" if is_true else "False")
    btn.setFixedHeight(20)
    btn.setStyleSheet(NODE_BOOL_STYLE)

    def _clicked():
        current = str(port.value).lower() in ("true", "1", "yes")
        new_val = not current
        if on_commit is not None:
            on_commit(new_val)
        else:
            port.value = new_val
        btn.setText("True" if new_val else "False")

    btn.clicked.connect(_clicked)
    return btn
