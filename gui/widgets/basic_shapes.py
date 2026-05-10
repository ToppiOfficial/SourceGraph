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
    def draw_plus(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a plus symbol."""
        thickness = max(1, size // 4)
        offset = (size - thickness) // 2
        
        # Vertical line
        painter.drawRect(x + offset, y + 2, thickness, size - 4)
        # Horizontal line
        painter.drawRect(x + 2, y + offset, size - 4, thickness)
    
    @staticmethod
    def draw_minus(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a minus symbol."""
        thickness = max(1, size // 4)
        offset = (size - thickness) // 2
        
        painter.drawRect(x + 2, y + offset, size - 4, thickness)
    
    @staticmethod
    def draw_arrow_right(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a right-pointing arrow."""
        margin = size // 8
        points = [
            QPoint(x + margin, y + margin),
            QPoint(x + size - margin, y + size // 2),
            QPoint(x + margin, y + size - margin),
            QPoint(x + margin, y + size // 2 + margin // 2),
            QPoint(x + margin * 2, y + size // 2),
            QPoint(x + margin, y + size // 2 - margin // 2),
        ]
        painter.drawPolygon(points)
    
    @staticmethod
    def draw_arrow_left(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a left-pointing arrow."""
        margin = size // 8
        points = [
            QPoint(x + size - margin, y + margin),
            QPoint(x + margin, y + size // 2),
            QPoint(x + size - margin, y + size - margin),
            QPoint(x + size - margin, y + size // 2 + margin // 2),
            QPoint(x + size - margin * 2, y + size // 2),
            QPoint(x + size - margin, y + size // 2 - margin // 2),
        ]
        painter.drawPolygon(points)
    
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
    def draw_triangle_up(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw an up-pointing triangle."""
        margin = size // 8
        points = [
            QPoint(x + size // 2, y + margin),
            QPoint(x + size - margin, y + size - margin),
            QPoint(x + margin, y + size - margin),
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
    
    @staticmethod
    def draw_circle(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a circle."""
        margin = size // 8
        painter.drawEllipse(x + margin, y + margin, size - 2 * margin, size - 2 * margin)
    
    @staticmethod
    def draw_square(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a square."""
        margin = size // 8
        painter.drawRect(x + margin, y + margin, size - 2 * margin, size - 2 * margin)
    
    @staticmethod
    def draw_line_horizontal(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a horizontal line."""
        thickness = max(1, size // 8)
        offset = (size - thickness) // 2
        painter.drawRect(x + 2, y + offset, size - 4, thickness)
    
    @staticmethod
    def draw_line_vertical(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a vertical line."""
        thickness = max(1, size // 8)
        offset = (size - thickness) // 2
        painter.drawRect(x + offset, y + 2, thickness, size - 4)
    
    @staticmethod
    def draw_diamond(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a diamond."""
        center_x = x + size // 2
        center_y = y + size // 2
        half_size = size // 2 - 1
        points = [
            QPoint(center_x, y + 1),
            QPoint(x + size - 1, center_y),
            QPoint(center_x, y + size - 1),
            QPoint(x + 1, center_y),
        ]
        painter.drawPolygon(points)
    
    @staticmethod
    def draw_cross(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw an X cross."""
        thickness = max(1, size // 6)
        offset = (size - thickness) // 2
        
        # Diagonal from top-left to bottom-right
        painter.drawRect(x + 2, y + 2, size - 4, thickness)
        # Diagonal from top-right to bottom-left
        painter.drawRect(x + 2, y + 2, thickness, size - 4)
    
    @staticmethod
    def draw_chevron_right(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a right-pointing chevron (double triangle)."""
        margin = size // 4
        ShapeDrawer.draw_triangle_right(painter, x, y, size - margin)
        ShapeDrawer.draw_triangle_right(painter, x + margin // 2, y, size - margin)
    
    @staticmethod
    def draw_chevron_down(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a down-pointing chevron (double triangle)."""
        margin = size // 4
        ShapeDrawer.draw_triangle_down(painter, x, y, size - margin)
        ShapeDrawer.draw_triangle_down(painter, x, y + margin // 2, size - margin)

    @staticmethod
    def draw_palette(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a square with diagonal cut (half colored, half grey)."""
        margin = size // 8
        
        # Save current brush/pen settings
        original_brush = painter.brush()
        original_pen = painter.pen()
        
        # Draw square outline
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(x + margin, y + margin, size - 2 * margin, size - 2 * margin)
        
        # Draw colored half (top-right triangle)
        colored_path = QPainterPath()
        colored_path.moveTo(x + margin, y + margin)  # Top-left
        colored_path.lineTo(x + size - margin, y + margin)  # Top-right
        colored_path.lineTo(x + size - margin, y + size - margin)  # Bottom-right
        colored_path.closeSubpath()
        
        painter.setBrush(original_pen.color())  # Use the pen color as fill
        painter.setPen(Qt.NoPen)
        painter.drawPath(colored_path)
        
        # Draw grey half (bottom-left triangle)
        grey_path = QPainterPath()
        grey_path.moveTo(x + margin, y + margin)  # Top-left
        grey_path.lineTo(x + margin, y + size - margin)  # Bottom-left
        grey_path.lineTo(x + size - margin, y + size - margin)  # Bottom-right
        grey_path.closeSubpath()
        
        painter.setBrush(IconColors.DISABLED)  # Grey color
        painter.drawPath(grey_path)
        
        # Restore original settings
        painter.setBrush(original_brush)
        painter.setPen(original_pen)

    @staticmethod
    def draw_link(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a chain link icon."""
        margin = size // 8
        thickness = max(1, size // 6)
        
        # Calculate link dimensions
        link_width = size // 2 - margin
        link_height = size // 3
        center_x = x + size // 2
        center_y = y + size // 2
        
        # Draw two interlocking links
        # Left link (vertical oval)
        left_x = center_x - link_width // 2
        painter.drawEllipse(left_x, center_y - link_height // 2, link_width, link_height)
        
        # Right link (horizontal oval)
        right_y = center_y - link_height // 2
        painter.drawEllipse(center_x - link_height // 2, right_y, link_height, link_width)

    @staticmethod
    def draw_map(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a map/minimap icon."""
        margin = size // 8
        # Draw outer rectangle
        painter.drawRect(x + margin, y + margin, size - 2 * margin, size - 2 * margin)
        
        # Draw some blocks to represent nodes/areas
        block_size = size // 6
        # Top-left block
        painter.drawRect(x + margin * 2, y + margin * 2, block_size, block_size)
        # Top-right block  
        painter.drawRect(x + size - margin * 2 - block_size, y + margin * 2, block_size, block_size)
        # Bottom-left block
        painter.drawRect(x + margin * 2, y + size - margin * 2 - block_size, block_size, block_size)
        # Center block
        painter.drawRect(x + size // 2 - block_size // 2, y + size // 2 - block_size // 2, block_size, block_size)

    @staticmethod
    def draw_connection(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw a connection/node link icon."""
        margin = size // 8
        center_x = x + size // 2
        center_y = y + size // 2
        node_size = size // 4
        line_thickness = max(1, size // 8)
        
        # Draw left node
        painter.drawEllipse(x + margin, center_y - node_size // 2, node_size, node_size)
        
        # Draw right node
        painter.drawEllipse(x + size - margin - node_size, center_y - node_size // 2, node_size, node_size)
        
        # Draw connecting line
        painter.drawRect(x + margin + node_size, center_y - line_thickness // 2, 
                       size - 2 * margin - node_size * 2, line_thickness)

    @staticmethod
    def draw_execution(painter: QPainter, x: int, y: int, size: int = 16):
        """Draw an execution icon representing node execution - a play button with node elements."""
        margin = size // 8
        center_x = x + size // 2
        center_y = y + size // 2
        
        # Draw a play triangle (execution symbol)
        triangle_size = size // 3
        triangle_margin = margin + 1
        triangle_points = [
            QPoint(x + triangle_margin, y + triangle_margin),
            QPoint(x + triangle_margin + triangle_size, y + size // 2),
            QPoint(x + triangle_margin, y + size - triangle_margin)
        ]
        painter.drawPolygon(triangle_points)
        
        # Draw small node circles around the play symbol to represent nodes
        node_radius = max(1, size // 10)
        # Top node
        painter.drawEllipse(center_x - node_radius, y + margin, node_radius * 2, node_radius * 2)
        # Bottom node
        painter.drawEllipse(center_x - node_radius, y + size - margin - node_radius * 2, node_radius * 2, node_radius * 2)
        # Right node
        painter.drawEllipse(x + size - margin - node_radius * 2, center_y - node_radius, node_radius * 2, node_radius * 2)




class IconColors:
    """Standardized color palette for icons."""
    
    # Action type colors
    ADD = QColor(106, 153, 85)      # Green
    DELETE = QColor(244, 71, 71)    # Red
    MOVE = QColor(242, 157, 41)     # Orange
    FOLD = QColor(99, 194, 223)     # Blue
    CONNECT = QColor(86, 156, 214)  # Light Blue
    CHANGE = QColor(206, 145, 120)  # Brown
    DEFAULT = QColor(136, 136, 136) # Gray
    
    # State colors
    ACTIVE = QColor(255, 255, 255)  # White
    DISABLED = QColor(85, 85, 85)   # Dark Gray
    HOVER = QColor(74, 74, 74)      # Medium Gray


def get_shape_for_action(action_text: str) -> str:
    """Get the appropriate shape name for a given action text."""
    action_lower = action_text.lower()
    
    if any(keyword in action_lower for keyword in ['add', 'create', 'new']):
        return 'plus'
    elif any(keyword in action_lower for keyword in ['delete', 'remove', 'clear']):
        return 'minus'
    elif any(keyword in action_lower for keyword in ['move', 'drag', 'position']):
        return 'arrow_right'
    elif any(keyword in action_lower for keyword in ['fold', 'collapse']):
        return 'triangle_right'
    elif any(keyword in action_lower for keyword in ['unfold', 'expand']):
        return 'triangle_down'
    elif any(keyword in action_lower for keyword in ['connect', 'wire', 'link']):
        return 'line_horizontal'
    elif any(keyword in action_lower for keyword in ['change', 'modify', 'update', 'edit']):
        return 'circle'
    else:
        return 'square'


def get_color_for_action(action_text: str) -> QColor:
    """Get the appropriate color for a given action text."""
    action_lower = action_text.lower()
    
    if any(keyword in action_lower for keyword in ['add', 'create', 'new']):
        return IconColors.ADD
    elif any(keyword in action_lower for keyword in ['delete', 'remove', 'clear']):
        return IconColors.DELETE
    elif any(keyword in action_lower for keyword in ['move', 'drag', 'position']):
        return IconColors.MOVE
    elif any(keyword in action_lower for keyword in ['fold', 'unfold', 'expand', 'collapse']):
        return IconColors.FOLD
    elif any(keyword in action_lower for keyword in ['connect', 'wire', 'link']):
        return IconColors.CONNECT
    elif any(keyword in action_lower for keyword in ['change', 'modify', 'update', 'edit']):
        return IconColors.CHANGE
    else:
        return IconColors.DEFAULT
