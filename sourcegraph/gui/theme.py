from __future__ import annotations
import os
from PySide6.QtGui import QIcon
from sourcegraph.gui.widgets.icon_provider import load_icon

BG_DARK             = "#1F1F1F"
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

NODE_INPUT_BG       = "#131313"

ACCENT              = "#63c2df"

# -- Semantic & Functional Colors ---------------------------------------------
VAR_BOOL            = "#4CAF50"
VAR_INT             = "#2196F3"
VAR_FLOAT           = "#FF9800"
VAR_STR             = "#9C27B0"

COLOR_VALID         = "#6a9955"
COLOR_INVALID       = "#f44747"
#COLOR_ERROR         = "#f44747"
COLOR_ERROR         = COLOR_INVALID
COLOR_PREVIEW       = "#569cd6"
COLOR_COMPILE       = "#ce9178"
COLOR_WARN          = "#ce9178"
COLOR_INFO          = "#888888"

# -- Reusable Style Fragments --------------------------------------------------
COMMON_BORDER_STYLE = f"border: 1px solid {BORDER_DARK}; border-radius: 4px;"
LIST_WIDGET_BASE = f"""
    background: {BG_DARK};
    {COMMON_BORDER_STYLE}
    outline: none;
"""
INPUT_STYLE = f"""
    background: {BG_DARK};
    color: {FG_BRIGHT};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 3px;
    padding: 2px 4px;
    font-size: 11px;
"""

# -- Node Editor --------------------------------------------------------------
NODE_BG             = "#202020"
HEADER_DARKNESS     = 150
WIRE_IDLE           = "#9E9E9E"
WIRE_SEL            = "#ffffff"

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
QTreeWidget, QListView          {{ {LIST_WIDGET_BASE} alternate-background-color: {BG_MED}; color: {FG_DEFAULT}; }}
QTreeWidget::item               {{ padding: 4px; }}
QTreeWidget::item:selected,
QListView::item:selected        {{ background-color: {BG_SELECTED}; color: {ACCENT}; }}
QHeaderView::section            {{ background-color: {BG_DARK}; color: {FG_DIM}; padding: 4px; border: none; border-right: 1px solid {BORDER_DARK}; border-bottom: 1px solid {BORDER_DARK}; font-size: {FONT_SM}; font-weight: bold; }}
QPushButton, QToolButton        {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {BG_SURFACE}, stop:1 {BG_HOVER}); border-radius: 2px; padding: 4px 8px; }}
QPushButton:hover,
QToolButton:hover               {{ background-color: {BG_HOVER}; }}
QPushButton:pressed,
QToolButton:pressed             {{ background-color: {BG_RAISED}; }}
QTextEdit                       {{ background-color: {BG_DARKER}; border: 1px inset {BORDER_DARK}; color: {FG_BRIGHT}; font-family: {FONT_MONO}; font-size: {FONT_SM}; }}
QTabWidget::pane                {{ border: 1px solid {BORDER_DARK}; background: {BG_BASE}; }}
QTabBar::tab                    {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {BG_SURFACE}, stop:1 {BG_HOVER}); color: {FG_DIM}; padding: 6px 12px; border: 1px solid {BORDER_DARK}; border-bottom: none; margin-right: 2px; }}
QTabBar::tab:selected           {{ background: {BG_BASE}; color: {FG_BRIGHT}; }}
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

NODE_TEXT_DISPLAY_STYLE = f"""
    QTextEdit {{
        background-color: {NODE_INPUT_BG};
        color: #f0f0f0;
        border: none;
        padding: 4px;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 10px;
    }}
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
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                stop:0 {BG_SURFACE}, stop:1 {BG_HOVER});
    color: {FG_MAIN};
    border: none; border-radius: 2px;
    padding: 1px 1px; font-family: {FONT_UI}; font-size: {FONT_MD};
}}
QPushButton:hover {{ background: {BG_HOVER}; }}
"""

NUMBER_INPUT_STYLE = f"""
    #NumberInputContainer {{
        background-color: {NODE_INPUT_BG};
        border: none;
        border-radius: 3px;
    }}
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

SEARCH_BAR_STYLE = f"""
QLineEdit {{
    background: {BG_DARKER};
    color: {FG_BRIGHT};
    border: none;
    padding: 10px 12px;
    font-size: 13px;
    font-family: {FONT_UI};
}}
"""

CATEGORY_LIST_STYLE = f"""
QListWidget {{
    {LIST_WIDGET_BASE}
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

NODE_LIST_STYLE = f"""
QListWidget {{
    {LIST_WIDGET_BASE}
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

DIALOG_STYLE = f"""
QDialog {{
    background: {BG_MED};
    color: {FG_MAIN};
    border: 1px solid {BORDER_DARK};
}}
QLabel {{ color: {FG_DIM}; font-size: 12px; }}
"""

# -- Node Widget Styles ---------------------------------------------------------
NODE_WIDGET_STYLE = f"""
QLineEdit {{
    background-color: {NODE_INPUT_BG};
    color: {FG_BRIGHT};
    border: none;
    border-radius: 3px;
    padding: 2px 4px;
    font-size: 11px;
}}
"""

NODE_BOOL_STYLE = f"""
QPushButton {{
    background-color: {NODE_INPUT_BG};
    color: {FG_BRIGHT};
    border: none;
    border-radius: 3px;
    font-size: 11px;
    font-weight: bold;
    padding: 0 8px;
}}
QPushButton:hover {{
    background-color: {BG_HOVER};
}}
"""

NODE_NUMBER_BTN_STYLE = f"""
QPushButton {{
    background-color: transparent;
    color: {FG_DIM};
    border: none;
    font-size: 14px;
    font-weight: bold;
    padding: 0px;
    min-width: 16px;
}}
QPushButton:pressed {{
    color: {FG_BRIGHT};
}}
"""

NODE_ENUM_BTN_STYLE = f"""
QPushButton {{
    background-color: {NODE_INPUT_BG};
    color: {FG_BRIGHT};
    border: none;
    border-radius: 3px;
    padding: 2px 8px;
    font-size: 11px;
    text-align: left;
}}
QPushButton:hover {{
    background-color: {BG_HOVER};
}}
"""

NODE_FILE_LABEL_STYLE = f"""
    QLabel {{
        background-color: {NODE_INPUT_BG};
        border: none;
        border-radius: 4px;
        padding: 4px 8px;
        color: {FG_MAIN};
        font-size: 10px;
    }}
"""

# -- Dialog Styles -------------------------------------------------------------
DIALOG_RENAME_STYLE = f"""
    QDialog {{
        background: {BG_DARK};
        color: {FG_MAIN};
    }}
    QLabel {{
        color: {FG_MAIN};
        font-size: 12px;
    }}
    QLineEdit {{
        {INPUT_STYLE}
        background: {BG_SURFACE};
        padding: 6px;
    }}
    QLineEdit:focus {{
        border: 1px solid {ACCENT};
    }}
    QDialogButtonBox QPushButton {{
        background: {BG_SURFACE};
        border: 1px solid {BORDER_LIGHT};
        border-radius: 3px;
        color: {FG_MAIN};
        padding: 6px 12px;
        font-size: 12px;
    }}
    QDialogButtonBox QPushButton:hover {{
        background: {BG_HOVER};
        border: 1px solid {ACCENT};
    }}
"""

# -- View Control Styles -------------------------------------------------------
VIEW_CONTROLS_STYLE = f"""
    QWidget {{
        background-color: rgba(30, 30, 30, 230);
        border: none;
    }}
    QPushButton {{
        background: transparent;
        color: {FG_MAIN};
        border: 1px solid transparent;
        font-weight: bold;
        padding: 4px 8px;
        border-radius: 4px;
    }}
    QPushButton:hover {{ 
        background: {BG_HOVER}; 
        border: 1px solid {BORDER_LIGHT};
    }}
    QPushButton:checked {{ 
        background: {BG_HOVER}; 
        color: {BG_DARK};
    }}
    QPushButton:checked:hover {{ 
        background: {ACCENT};
        opacity: 0.8;
    }}
"""

# -- Notification Styles -------------------------------------------------------
NOTIFICATION_STYLE = f"""
    QLabel {{
        background-color: {BG_DARKER};
        color: {FG_MAIN};
        border: 2px solid {{bg_color}};
        border-radius: 8px;
        padding: 9px 20px;
        font-family: {FONT_MONO};
        font-size: 12px;
        font-weight: bold;
    }}
"""

# -- Splash Screen Styles ------------------------------------------------------
SPLASH_BG_STYLE = f"""
    #SplashContainer {{
        background-color: {BG_DARKER};
        border: 1px solid {BORDER_LIGHT};
        border-radius: 12px;
    }}
"""

SPLASH_PROGRESS_STYLE = f"""
    QProgressBar {{
        background-color: {BG_DARK};
        border: 1px solid {BORDER_MED};
        border-radius: 6px;
        text-align: center;
        color: transparent;
        height: 10px;
    }}
    QProgressBar::chunk {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
            stop:0 {ACCENT}, stop:1 #4fa8c2);
        border-radius: 5px;
    }}
"""

# -- Preview Panel Styles ------------------------------------------------------
PREVIEW_SCROLL_STYLE = f"""
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 6px; border: none; }}
    QScrollBar::handle:vertical {{ background: {BG_SURFACE}; border-radius: 3px; min-height: 20px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
"""

PREVIEW_RENDER_CONTAINER_STYLE = f"""
    QFrame {{
        background-color: {BG_DARKER};
        border-radius: 8px;
    }}
"""

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

# -- Node Inspector Panel Styles -----------------------------------------------
INSPECTOR_TITLE_EDIT_STYLE = f"""
QLineEdit {{
    background: transparent;
    border: none;
    border-bottom: 1px solid transparent;
    color: {FG_BRIGHT};
    font-size: 12px;
    font-weight: bold;
    font-family: "Roboto", "Segoe UI";
    padding: 0px 0px 1px 0px;
}}
QLineEdit:focus {{
    border-bottom: 1px solid {ACCENT};
}}
"""

INSPECTOR_SECTION_LABEL_STYLE = (
    f"color: {FG_DIMMER}; font-size: 10px; font-weight: bold; "
    f"padding: 6px 10px 2px 10px; letter-spacing: 1px; background: transparent;"
)
INSPECTOR_PORT_LABEL_STYLE = f"color: {FG_DEFAULT}; font-size: 12px; background: transparent;"
INSPECTOR_CONN_HINT_STYLE  = f"color: {FG_DIMMER}; font-size: 11px; font-style: italic; background: transparent;"

# -- File Type Colors ----------------------------------------------------------
# Extension -> icon tint color. Edit here to affect all panels.
FILE_TYPE_COLORS: dict[str, str] = {
    # QC / model source
    ".qc":   "#f4a261",
    ".smd":  "#5ba4cf",
    ".dmx":  "#74b3ce",
    ".mdl":  "#7ec8e3",
    ".dx90": "#7ec8e3",
    # Textures
    ".vtf":  "#c77dff",
    ".tga":  "#c77dff",
    ".png":  "#c77dff",
    ".jpg":  "#c77dff",
    ".jpeg": "#c77dff",
    ".bmp":  "#c77dff",
    # Materials
    ".vmt":  "#b5838d",
    ".mat":  "#b5838d",
    # Audio
    ".wav":  "#52b788",
    ".mp3":  "#52b788",
    ".ogg":  "#52b788",
    # Data / config
    ".json": "#ffd166",
    ".cfg":  "#ffd166",
    ".txt":  "#adb5bd",
    ".srcgraph":  "#1ada4a",
    ".srcsubgraph":  "#69ec8a",
    # Fallback
    "":      "#adb5bd",
}


def load_file_icon(path: str) -> QIcon:
    """Return a tinted file QIcon for *path* based on its extension."""
    ext = os.path.splitext(path)[1].lower()
    color = FILE_TYPE_COLORS.get(ext, FILE_TYPE_COLORS[""])
    return load_icon("file",color=color)