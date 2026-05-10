from __future__ import annotations

import os

from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QPainterPath
from PySide6.QtCore import Qt, QPoint
from gui.widgets.basic_shapes import ShapeDrawer
BG_DARK             = "#1a1a1a"
BG_DARKER           = "#111111"
BG_MED              = "#252525"
BG_BASE             = "#2a2a2a"
BG_SURFACE          = "#333333"
BG_RAISED           = "#3d3d3d"
BG_HOVER            = "#4a4a4a"
BG_SELECTED         = "#4d4d4d"
BG_MED_TRANSPARENT  = "#252525cc"

BORDER              = "#111111"
BORDER_DARK         = "#111111"
BORDER_MED          = "#2a2a2a"
BORDER_LIGHT        = "#444444"

FG_BRIGHT           = "#ffffff"
FG_MAIN             = "#f0f0f0"
FG_DEFAULT          = "#cccccc"
FG_DIM              = "#888888"
FG_DIMMER           = "#555555"

ACCENT              = "#63c2df"

# -- Semantic & Functional Colors ---------------------------------------------
VAR_BOOL            = "#4CAF50"
VAR_INT             = "#2196F3"
VAR_FLOAT           = "#FF9800"
VAR_STR             = "#9C27B0"

COLOR_VALID         = "#6a9955"
COLOR_INVALID       = "#f44747"
COLOR_ERROR         = "#f44747"
COLOR_PREVIEW       = "#569cd6"
COLOR_COMPILE       = "#ce9178"
COLOR_WARN          = "#ce9178"
COLOR_INFO          = "#888888"

# -- Node Editor --------------------------------------------------------------
NODE_BG             = "#202020"
HEADER_DARKNESS     = 150
WIRE_IDLE           = "#BEBEBE"
WIRE_SEL            = "#f29d29"

GRID_COARSE         = "#555555"
GRID_FINE           = "#404040"

# -- Minimap -------------------------------------------------------------------
MINIMAP_BORDER      = BORDER_LIGHT   # outline of the minimap widget
MINIMAP_VIEW        = ACCENT         # rectangle showing the current viewport

# -- Typography ----------------------------------------------------------------
FONT_UI      = "Segoe UI"
FONT_MONO    = "Consolas"
FONT_SM      = "13px"
FONT_MD      = "14px"

# -- Application-wide stylesheet -----------------------------------------------
MAIN_STYLESHEET = f"""
QMainWindow, QWidget            {{ background-color: {BG_BASE}; color: {FG_MAIN}; font-family: {FONT_UI}; }}
QDockWidget                     {{ font-weight: bold; color: {FG_DIM}; }}
QDockWidget::title              {{ background: {BG_DARK}; padding-left: 5px; padding-top: 4px; border: 1px solid {BORDER_DARK}; }}
QTreeWidget, QListView          {{ background-color: {BG_DARK}; alternate-background-color: {BG_MED}; border: 1px inset {BORDER_DARK}; color: {FG_DEFAULT}; outline: none; }}
QTreeWidget::item               {{ padding: 4px; }}
QTreeWidget::item:selected,
QListView::item:selected        {{ background-color: {BG_SELECTED}; color: {ACCENT}; }}
QHeaderView::section            {{ background-color: {BG_DARK}; color: {FG_DIM}; padding: 4px; border: none; border-right: 1px solid {BORDER_DARK}; border-bottom: 1px solid {BORDER_DARK}; font-size: {FONT_SM}; font-weight: bold; }}
QPushButton, QToolButton        {{ background-color: {BG_SURFACE}; color: {FG_BRIGHT}; border: 1px solid {BORDER_DARK}; border-radius: 2px; padding: 4px 10px; }}
QPushButton:hover,
QToolButton:hover               {{ background-color: {BG_HOVER}; }}
QPushButton:pressed,
QToolButton:pressed             {{ background-color: {BG_RAISED}; }}
QTextEdit                       {{ background-color: {BG_DARKER}; border: 1px inset {BORDER_DARK}; color: {FG_BRIGHT}; font-family: {FONT_MONO}; font-size: {FONT_SM}; }}
QTabWidget::pane                {{ border: 1px solid {BORDER_DARK}; background: {BG_BASE}; }}
QTabBar::tab                    {{ background: {BG_DARK}; color: {FG_DIM}; padding: 6px 12px; border: 1px solid {BORDER_DARK}; border-bottom: none; margin-right: 2px; }}
QTabBar::tab:selected           {{ background: {BG_BASE}; color: {ACCENT}; font-weight: bold; }}
QMenu                           {{ background: {BG_DARK}; border: 1px solid {BORDER_DARK}; }}
QMenu::item:selected            {{ background: {BG_SELECTED}; }}
QToolBar                        {{ background: {BG_DARK}; border-bottom: 1px solid {BORDER_DARK}; }}
QStatusBar                      {{ background: {BG_DARK}; color: {FG_DIM}; font-size: {FONT_SM}; border-top: 1px solid {BORDER_DARK}; }}
QScrollBar:vertical             {{ background: {BG_MED}; width: 8px; border: none; }}
QScrollBar::handle:vertical     {{ background: {BG_SURFACE}; border-radius: 4px; min-height: 20px; }}
QScrollBar:horizontal           {{ background: {BG_MED}; height: 8px; border: none; }}
QScrollBar::handle:horizontal   {{ background: {BG_SURFACE}; border-radius: 4px; min-width: 20px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QSplitter::handle               {{ background: {BORDER_DARK}; }}
"""

# -- Component Stylesheets -----------------------------------------------------
EDIT_STYLE = f"""
QLineEdit {{
    background-color: {BG_DARK};
    color: {FG_BRIGHT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 3px;
    padding: 2px 4px;
    font-size: 11px;
}}
QLineEdit:focus {{ border: 1px solid {ACCENT}; }}
"""

NODE_COMBO_STYLE = f"""
QComboBox {{
    background: {BG_DARK}; color: {FG_BRIGHT};
    border: 1px solid transparent; outline: none; margin: 0px;
    border-radius: 6px; padding: 0px 6px;
    font-family: {FONT_UI}; font-size: {FONT_SM};
}}
QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QComboBox::drop-down {{
    border: none;
    background: transparent;
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 14px;
}}
QComboBox QAbstractItemView {{
    background: {BG_SURFACE};
    border: 1px solid {BORDER_DARK};
    color: {FG_MAIN};
    outline: none;
    padding: 1px;
}}
QComboBox QAbstractItemView::item {{
    padding: 4px 8px;
    min-height: 20px;
}}
QComboBox QAbstractItemView::item:selected {{
    background-color: {BG_SELECTED};
    color: {ACCENT};
}}
QComboBox QAbstractItemView::item:disabled {{
    color: {FG_DIM};
    font-weight: bold;
    font-size: 9px;
    background: transparent;
    padding: 2px 8px 1px;
    min-height: 0px;
}}
QComboBox QAbstractItemView::separator {{
    height: 1px;
    background: {BORDER_LIGHT};
    margin: 0px 4px;
}}
"""

BTN_STYLE = f"""
QPushButton {{
    background: {BG_SURFACE}; color: {FG_MAIN};
    border: 1px solid {BORDER_DARK}; border-radius: 2px;
    padding: 1px 1px; font-family: {FONT_UI}; font-size: {FONT_MD};
}}
QPushButton:hover {{ background: {BG_HOVER}; }}
"""

TOOLBAR = f"""
QToolBar {{ background: {BG_BASE}; border-bottom: 1px solid {BORDER_DARK}; spacing: 1px; }}
QToolButton {{ background: transparent; color: {FG_MAIN}; border: none; padding: 2px; }}
QToolButton:hover {{ background: {BG_RAISED}; }}
"""

MENU = f"""
QMenu, QDialog {{ background: {BG_MED}; border: 1px solid {BORDER_DARK}; color: {FG_MAIN}; }}
QMenu::item:selected {{ background: {BG_SELECTED}; }}
QLineEdit {{ background: {BG_DARK}; color: {FG_BRIGHT}; border: 1px solid {BORDER_MED}; }}
"""

# -- Enhanced Node Search Dialog Styles -----------------------------------------
ENHANCED_MENU_STYLE = f"""
QDialog {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                stop:0 {BG_SURFACE}, stop:1 {BG_MED}); 
    border: 1px solid {BORDER_LIGHT}; 
    border-radius: 8px;
    color: {FG_MAIN};
}}
"""

SEARCH_STYLE = f"""
QLineEdit {{
    background: {BG_DARK};
    color: {FG_BRIGHT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 4px;
    padding: 8px 12px;
    font-size: 12px;
    font-family: {FONT_UI};
}}
QLineEdit:focus {{
    border: 2px solid {ACCENT};
    background: {BG_DARKER};
}}
"""

LIST_STYLE = f"""
QListWidget {{
    background: {BG_DARK};
    border: 1px solid {BORDER_MED};
    border-radius: 4px;
    outline: none;
    font-size: 11px;
    font-family: {FONT_UI};
}}
QListWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid transparent;
    color: {FG_MAIN};
}}
QListWidget::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                stop:0 {BG_SELECTED}, stop:1 {BG_HOVER}); 
    color: {FG_BRIGHT};
    border-left: 3px solid {ACCENT};
}}
QListWidget::item:hover {{
    background: {BG_HOVER};
}}
QScrollBar:vertical {{
    background: {BG_MED};
    width: 6px;
    border: none;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {BG_SURFACE};
    border-radius: 3px;
    min-height: 15px;
}}
QScrollBar::handle:vertical:hover {{
    background: {BG_HOVER};
}}
"""

SEARCH_BAR_STYLE = f"""
QLineEdit {{
    background: {BG_DARK};
    color: {FG_BRIGHT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 6px;
    padding: 10px 12px;
    font-size: 13px;
    font-family: {FONT_UI};
}}
QLineEdit:focus {{
    border: 2px solid {ACCENT};
    background: {BG_DARKER};
}}
"""

CATEGORY_LIST_STYLE = f"""
QListWidget {{
    background: {BG_DARK};
    border: 1px solid {BORDER_MED};
    border-radius: 6px;
    outline: none;
    font-size: 12px;
    font-family: {FONT_UI};
}}
QListWidget::item {{
    padding: 8px 12px;
    border-bottom: 1px solid transparent;
    color: {FG_MAIN};
    border-radius: 4px;
    margin: 1px 4px;
}}
QListWidget::item:selected {{
    background: {BG_SELECTED};
    color: {FG_BRIGHT};
    font-weight: bold;
}}
QListWidget::item:hover {{
    background: {BG_HOVER};
}}
"""

NODE_LIST_STYLE = f"""
QListWidget {{
    background: {BG_DARK};
    border: 1px solid {BORDER_MED};
    border-radius: 6px;
    outline: none;
    font-size: 11px;
    font-family: {FONT_UI};
}}
QListWidget::item {{
    border-bottom: 1px solid transparent;
    color: {FG_MAIN};
    border-radius: 4px;
    margin: 2px 4px;
}}
QListWidget::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                stop:0 {BG_SELECTED}, stop:1 {BG_HOVER}); 
    color: {FG_BRIGHT};
    border-left: 3px solid {ACCENT};
}}
QListWidget::item:hover {{
    background: {BG_HOVER};
}}
QScrollBar:vertical {{
    background: {BG_MED};
    width: 6px;
    border: none;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {BG_SURFACE};
    border-radius: 3px;
    min-height: 15px;
}}
QScrollBar::handle:vertical:hover {{
    background: {BG_HOVER};
}}
"""

CATEGORY_HEADER_STYLE = f"""
QLabel {{
    color: {ACCENT};
    font-weight: bold;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 4px 8px;
    background: transparent;
}}
"""

TAB_STYLE = f"""
QTabWidget::pane {{ border: 1px solid {BORDER_DARK}; background: {BG_BASE}; }}
QTabBar::tab {{ background: {BG_SURFACE}; color: {FG_DIM}; padding: 6px 12px; }}
QTabBar::tab:selected {{ background: {BG_BASE}; color: {FG_BRIGHT}; border-bottom: 2px solid {ACCENT}; }}
"""

HISTORY_STYLE = f"""
QUndoView {{ 
    background: {BG_DARK}; 
    color: {FG_MAIN}; 
    border: 1px solid {BORDER_DARK}; 
    border-radius: 4px; 
    outline: none; 
    font-size: {FONT_SM};
    padding: 2px;
}}
QUndoView::item {{ 
    padding: 8px 12px; 
    border-bottom: 1px solid {BORDER_MED}; 
    min-height: 24px;
}}
QUndoView::item:selected {{ 
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                stop:0 {BG_SELECTED}, stop:1 {BG_RAISED}); 
    color: {FG_BRIGHT}; 
    border-left: 3px solid {ACCENT};
}}
QUndoView::item:hover {{ 
    background: {BG_HOVER}; 
}}
QUndoView::item:disabled {{ 
    color: {FG_DIMMER}; 
    font-style: italic;
}}
"""

TREE_STYLE = f"""
QTreeWidget {{
    background-color: {BG_DARK};
    border: 1px solid {BORDER_DARK};
    border-radius: 4px;
    outline: none;
}}
QTreeWidget::item {{
    height: 24px;
    padding: 0px 2px;
}}
QTreeWidget::item:hover    {{ background-color: {BG_HOVER}; }}
QTreeWidget::item:selected {{ background-color: {BG_SELECTED}; color: {ACCENT}; }}
QTreeWidget::branch        {{ background-color: transparent; }}
QTreeWidget::branch:has-children {{ image: none; }}

QHeaderView::section {{
    background-color: {BG_SURFACE};
    color: {FG_DIM};
    border: none;
    border-bottom: 1px solid {BORDER_DARK};
    padding: 2px 6px;
    font-size: {FONT_SM};
    font-weight: bold;
}}
"""

# -- Node Widget Styles ---------------------------------------------------------
NODE_WIDGET_STYLE = f"""
QLineEdit {{
    background-color: {BG_DARK};
    color: {FG_BRIGHT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 3px;
    padding: 2px 4px;
    font-size: 11px;
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}
"""

NODE_BOOL_STYLE = f"""
QPushButton {{
    background-color: {BG_DARK};
    color: {FG_BRIGHT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 3px;
    font-size: 11px;
    font-weight: bold;
    padding: 0 8px;
}}
QPushButton:hover {{
    background-color: {BG_HOVER};
    border-color: {ACCENT};
}}
"""

NODE_COMBO_STYLE = f"""
QComboBox {{
    background-color: {BG_DARK};
    color: {FG_BRIGHT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 3px;
    padding: 2px 4px;
    font-size: 11px;
}}
QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 0px;
}}
QComboBox::down-arrow {{
    image: none;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_SURFACE};
    border: 1px solid {BORDER_DARK};
    color: {FG_MAIN};
    selection-background-color: {BG_SELECTED};
}}
"""

NODE_FILE_LABEL_STYLE = f"""
    QLabel {{
        background-color: #1e1e1e;
        border: 1px solid #3a3a3a;
        border-radius: 4px;
        padding: 4px 8px;
        color: {FG_MAIN};
        font-size: 10px;
    }}
"""

# -- Execution Panel Styles ---------------------------------------------------
EXEC_ITEM_CHECKBOX_STYLE = f"""
QCheckBox {{
    background: transparent;
    border: none;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER_LIGHT};
    border-radius: 2px;
    background-color: {BG_SURFACE};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border: 1px solid {ACCENT};
}}
QCheckBox::indicator:hover {{
    border: 1px solid {ACCENT};
}}
"""

EXEC_ITEM_TEXT_LABEL_STYLE = f"""
color: {FG_MAIN};
font-size: 12px;
font-weight: 500;
padding: 2px;
"""

EXEC_ITEM_ORDER_LABEL_STYLE = f"""
color: {FG_DIM};
font-size: 10px;
font-weight: bold;
background: {BG_SURFACE};
border: 1px solid {BORDER_LIGHT};
border-radius: 8px;
padding: 2px 6px;
min-width: 16px;
max-width: 24px;
"""

EXEC_LIST_WIDGET_STYLE = f"""
QListWidget {{
    background-color: {BG_DARK};
    border: 1px solid {BORDER_DARK};
    border-radius: 6px;
    padding: 4px;
    outline: none;
    font-family: {FONT_UI};
}}
QListWidget::item {{
    padding: 2px;
    margin: 1px 2px;
    border: 1px solid transparent;
    border-radius: 4px;
    background-color: {BG_SURFACE};
    min-height: 28px;
}}
QListWidget::item:hover {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {BG_HOVER}, stop:1 {BG_RAISED});
    border: 1px solid {BORDER_LIGHT};
}}
QListWidget::item:selected {{
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {BG_SELECTED}, stop:1 {BG_HOVER});
    border: 1px solid {ACCENT};
    color: {FG_BRIGHT};
}}
QListWidget::item:focus {{
    outline: none;
}}
QScrollBar:vertical {{
    background: {BG_MED};
    width: 8px;
    border: none;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BG_SURFACE};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {BG_HOVER};
}}
"""

SESSION_RENAME_EDIT_STYLE = f"""
QLineEdit {{
    background: {BG_DARK};
    border: 1px solid {BORDER_DARK};
    border-radius: 3px;
    color: {FG_BRIGHT};
    padding: 4px;
    font-size: 11px;
}}
QLineEdit:focus {{
    border: 1px solid {ACCENT};
}}
"""

SESSION_RENAME_EDIT_ERROR_STYLE = f"""
QLineEdit {{
    background: {BG_SURFACE};
    border: 1px solid {COLOR_ERROR};
    border-radius: 3px;
    color: {FG_MAIN};
    padding: 4px;
    font-size: 11px;
}}
"""

# -- Icon Creation Functions ---------------------------------------------------

def get_folder_icon(size: int = 16) -> QIcon:
    """Create a folder icon with appropriate colors."""
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # Use a folder-like color
    painter.setBrush(QColor("#63c2df"))  # ACCENT color
    painter.setPen(Qt.NoPen)
    
    ShapeDrawer.draw_folder(painter, 0, 0, size)
    painter.end()
    return QIcon(px)

def get_file_icon(size: int = 16, letter: str = "A", is_image: bool = False) -> QIcon:
    """Create a file icon with a letter for readable files."""
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing)
    
    if is_image:
        # Light blue for image files
        painter.setBrush(QColor("#87CEEB"))  # Sky blue
        painter.setPen(QColor("#4682B4"))  # Steel blue for outline
    else:
        # White for other readable files
        painter.setBrush(QColor("#FFFFFF"))  # White
        painter.setPen(QColor("#CCCCCC"))  # Light grey for outline
    
    ShapeDrawer.draw_file_with_letter(painter, 0, 0, size, letter)
    painter.end()
    return QIcon(px)

def get_blank_file_icon(size: int = 16) -> QIcon:
    """Create a blank file icon for unreadable/binary files."""
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # Use lighter grey for binary/unreadable files
    painter.setBrush(QColor("#808080"))  # Lighter grey
    painter.setPen(QColor("#606060"))  # Medium grey for outline
    
    ShapeDrawer.draw_file(painter, 0, 0, size)
    painter.end()
    return QIcon(px)

def is_image_file(file_path: str) -> bool:
    """Check if file is an image based on extension."""
    image_extensions = {'.jpg', '.jpeg', '.png', '.tga', '.dds', '.bmp', '.tiff', '.tif', '.gif', '.webp', '.exr', '.hdr'}
    return os.path.splitext(file_path)[1].lower() in image_extensions

def get_bookmark_icon(size: int = 16) -> QIcon:
    """Create a simple bookmark icon."""
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # Use accent color for the bookmark
    painter.setBrush(QColor(ACCENT))
    painter.setPen(Qt.NoPen)  # No outline
    
    # Draw bookmark shape using QPainterPath
    margin = size // 8  # Keep original margin
    tag_height = size // 3
    width_reduction = size // 6  # How much to reduce width on each side
    
    # Create custom path for bookmark shape
    path = QPainterPath()
    path.moveTo(margin + width_reduction, margin)  # Top-left (moved right)
    path.lineTo(size - margin - width_reduction, margin)  # Top-right (moved left)
    path.lineTo(size - margin - width_reduction, size - margin - tag_height)  # Right before tag
    path.lineTo(size // 2, size - margin)  # Bottom point (center)
    path.lineTo(margin + width_reduction, size - margin - tag_height)  # Left before tag
    path.closeSubpath()
    
    painter.drawPath(path)
    
    painter.end()
    return QIcon(px)


def get_execution_icon(size: int = 16) -> QIcon:
    """Create an execution icon representing node execution."""
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    painter = QPainter(px)
    painter.setRenderHint(QPainter.Antialiasing)
    
    # Use accent color for execution icon
    painter.setBrush(QColor(ACCENT))
    painter.setPen(QColor(ACCENT))
    
    ShapeDrawer.draw_execution(painter, 0, 0, size)
    painter.end()
    return QIcon(px)


def is_file_readable(file_path: str) -> bool:
    """Check if a file is readable (text-based) or binary."""
    try:
        with open(file_path, 'rb') as f:
            # Read first 1024 bytes to check for non-ASCII content
            # Check if there are any null bytes or too many non-ASCII characters
            # Count non-ASCII printable characters
            # If more than 30% non-ASCII, consider it binary

            chunk = f.read(1024)
            if b'\x00' in chunk:
                return False

            non_ascii = sum(1 for byte in chunk if byte > 127)      
            return non_ascii / len(chunk) < 0.3
            
    except (IOError, OSError):
        return False
