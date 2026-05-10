from __future__ import annotations

from PySide6.QtCore import Qt, QSize, QRect
from PySide6.QtGui import QIcon, QFont, QPainter, QPixmap, QColor
from PySide6.QtWidgets import QUndoView, QStyledItemDelegate, QStyle, QAbstractItemView

from .basic_shapes import ShapeDrawer, get_shape_for_action, get_color_for_action


class CustomUndoView(QUndoView):
    """
    Enhanced QUndoView with custom styling, icons, and improved visual hierarchy.
    """
    
    def __init__(self, stack=None, parent=None):
        super().__init__(stack, parent)
        self._setup_ui()
        
    def _setup_ui(self):
        """Configure the view with enhanced settings."""
        # Enable better visual settings
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        
        # Set custom item delegate for enhanced rendering
        self.setItemDelegate(CustomUndoItemDelegate(self))
        
        # Configure visual properties
        self.setIconSize(QSize(16, 16))
        self.setSpacing(2)
        
    def setStack(self, stack):
        """Override to apply styling when stack changes."""
        super().setStack(stack)
        self._apply_enhanced_styling()
        
    def _apply_enhanced_styling(self):
        """Apply enhanced visual styling to the view."""
        # This will be enhanced with custom styling from theme
        pass


class CustomUndoItemDelegate(QStyledItemDelegate):
    """
    Custom item delegate for rendering enhanced history items with icons and formatting.
    """
    
    def __init__(self, parent_view):
        super().__init__(parent_view)
        self.parent_view = parent_view
        self._icon_cache = {}
        
    def paint(self, painter, option, index):
        """Override paint to provide custom rendering."""
        # Get the action text
        action_text = index.data(Qt.DisplayRole) or ""
        
        # Draw background
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor(74, 74, 74))  # BG_HOVER
        else:
            painter.fillRect(option.rect, QColor(37, 37, 37))  # BG_MED
            
        # Draw icon (centered vertically)
        icon = self.get_action_icon(action_text)
        icon_y = option.rect.top() + (option.rect.height() - 16) // 2
        icon_rect = QRect(option.rect.left() + 8, icon_y, 16, 16)
        icon.paint(painter, icon_rect)
        
        # Draw text (centered vertically)
        text_rect = QRect(option.rect.left() + 32, option.rect.top(), 
                          option.rect.width() - 36, option.rect.height())
        
        formatted_text = self.format_action_text(action_text)
        
        # Set text color based on state
        if option.state & QStyle.State_Selected:
            text_color = QColor(255, 255, 255)  # FG_BRIGHT
        elif not index.flags() & Qt.ItemIsEnabled:
            text_color = QColor(85, 85, 85)    # FG_DIMMER
        else:
            text_color = QColor(240, 240, 240)  # FG_MAIN
            
        painter.setPen(text_color)
        painter.setFont(QFont("Segoe UI", 10))  # Slightly smaller font for compact view
        painter.drawText(text_rect, Qt.AlignVCenter, formatted_text)
        
    def sizeHint(self, option, index):
        """Provide custom size hint for items."""
        return QSize(200, 20)  # Reduced height for more compact view
        
    def get_action_icon(self, action_text):
        """Get appropriate icon based on action type."""
        action_lower = action_text.lower()
        
        # Cache icons for performance
        if action_text in self._icon_cache:
            return self._icon_cache[action_text]
            
        icon = self._create_action_icon(action_lower)
        self._icon_cache[action_text] = icon
        return icon
        
    def _create_action_icon(self, action_text):
        """Create icon based on action type using standardized shapes."""
        # Create simple colored icons based on action type
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(0, 0, 0, 0))  # Transparent background
        
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get standardized color and shape
        color = get_color_for_action(action_text)
        shape_name = get_shape_for_action(action_text)
        
        # Draw the shape using standardized methods
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        
        # Map shape names to drawing methods
        shape_methods = {
            'plus': ShapeDrawer.draw_plus,
            'minus': ShapeDrawer.draw_minus,
            'arrow_right': ShapeDrawer.draw_arrow_right,
            'triangle_right': ShapeDrawer.draw_triangle_right,
            'triangle_down': ShapeDrawer.draw_triangle_down,
            'line_horizontal': ShapeDrawer.draw_line_horizontal,
            'circle': ShapeDrawer.draw_circle,
            'square': ShapeDrawer.draw_square,
        }
        
        draw_method = shape_methods.get(shape_name, ShapeDrawer.draw_square)
        draw_method(painter, 0, 0, 16)
            
        painter.end()
        return QIcon(pixmap)
        
    def format_action_text(self, action_text):
        """Format action text for better readability."""
        # Capitalize first letter, add proper spacing
        if not action_text:
            return action_text
            
        # Split on common separators and capitalize
        parts = action_text.replace('_', ' ').replace(':', ': ').split()
        formatted = ' '.join(part.capitalize() if part.islower() else part for part in parts)
        
        # Add some common formatting improvements
        formatted = formatted.replace('Node ', 'Node: ')
        formatted = formatted.replace('Fold ', 'Fold ')
        formatted = formatted.replace('Unfold ', 'Unfold ')
        
        return formatted.strip()
