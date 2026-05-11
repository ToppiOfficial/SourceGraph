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
            
        # Draw text (centered vertically)
        text_rect = QRect(option.rect.left() + 4, option.rect.top(), 
                          option.rect.width() - 8, option.rect.height())
        
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
