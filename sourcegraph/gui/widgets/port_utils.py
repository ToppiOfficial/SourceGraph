"""Shared utilities for port-type inspection, text validation, and port widgets.

Centralizes logic that was previously duplicated between gui/items/node.py
(node-canvas inline editing) and gui/panels/node_inspector.py (inspector panel).
"""
from __future__ import annotations

from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QColor, QPainter

from sourcegraph.sys.registry import (
    is_editable as _is_node_editable,
    is_inspector_editable as _is_inspector_editable,
    get_port_type_spec as _get_type_spec,
)


def port_is_node_editable(port_type) -> bool:
    """Return True if this port type supports inline value editing on the node canvas."""
    return _is_node_editable(port_type)


def port_is_inspector_editable(port_type) -> bool:
    """Return True if this port type supports value editing in the inspector panel."""
    return _is_inspector_editable(port_type)


def validate_port_text(port_type: str, text: str) -> str | None:
    """Validate raw text input for a port.

    Returns an error message string if the value is invalid, or None if acceptable.
    """
    if not text:
        return None
    spec = _get_type_spec(port_type)
    return spec.validate_text(text) if spec and spec.validate_text else None


class PortDot(QWidget):
    """12×12 colored circle that visually matches the port dot drawn on graph nodes.

    Used in the inspector panel to label each port row with its type color.
    """

    def __init__(self, color: str, parent=None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(12, 12)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self._color)
        p.setPen(self._color.darker(150))
        p.drawEllipse(1, 1, 10, 10)
