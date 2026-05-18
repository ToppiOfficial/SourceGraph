from __future__ import annotations
from PySide6.QtWidgets import QPushButton
from gui.theme import NODE_ENUM_BTN_STYLE


def _elide(s: str, n: int = 25) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


def make_enum_canvas_widget(port, parent=None) -> QPushButton:
    btn = QPushButton(parent)
    btn.setFixedHeight(22)
    btn.setStyleSheet(NODE_ENUM_BTN_STYLE)
    v = port.value
    btn.setText(_elide(str(v) if v is not None else "Select...", 25))
    btn.setProperty("widget_type", "enum")
    btn.refresh_value = lambda v, _b=btn: _b.setText(
        _elide(str(v) if v is not None else "Select...", 25)
    )
    return btn
