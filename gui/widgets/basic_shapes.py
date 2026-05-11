"""
Standardized basic shapes and symbols for consistent UI iconography.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QPainter, QColor, QPainterPath


class ShapeDrawer:
    """
    Utility class for drawing standardized shapes and symbols.
    """
    
    @staticmethod
    def draw_triangle_right(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a right-pointing triangle (folded state)."""
        margin = size // 8
        points = [
            QPoint(x + margin, y + size // 2),
            QPoint(x + size - margin, y + margin),
            QPoint(x + size - margin, y + size - margin),
        ]
        painter.drawPolygon(points)
    
    @staticmethod
    def draw_triangle_down(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a down-pointing triangle (unfolded state)."""
        margin = size // 8
        points = [
            QPoint(x + margin, y + margin),
            QPoint(x + size - margin, y + margin),
            QPoint(x + size // 2, y + size - margin),
        ]
        painter.drawPolygon(points)
    
    @staticmethod
    def draw_triangle_left(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a left-pointing triangle."""
        margin = size // 8
        points = [
            QPoint(x + size - margin, y + size // 2),
            QPoint(x + margin, y + margin),
            QPoint(x + margin, y + size - margin),
        ]
        painter.drawPolygon(points)

class IconColors:
    """Standardized color palette for icons."""
    
    # Action type colors
    CONNECT = QColor(86, 156, 214)  # Light Blue
    DEFAULT = QColor(136, 136, 136) # Gray


def get_shape_for_action(action_text: str) -> str:
    """Get the appropriate shape name for a given action text."""
    action_lower = action_text.lower()
    
    if any(keyword in action_lower for keyword in ['unfold', 'expand']):
        return 'triangle_down'
    elif any(keyword in action_lower for keyword in ['connect', 'wire', 'link']):
        return 'line_horizontal'
    else:
        return 'square'


def get_color_for_action(action_text: str) -> QColor:
    """Get the appropriate color for a given action text."""
    action_lower = action_text.lower()
    
    if any(keyword in action_lower for keyword in ['fold', 'unfold', 'expand', 'collapse']):
        return IconColors.FOLD
    elif any(keyword in action_lower for keyword in ['connect', 'wire', 'link']):
        return IconColors.CONNECT
    else:
        return IconColors.DEFAULT
