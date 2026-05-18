from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import faulthandler
import traceback
from pathlib import Path
from PySide6.QtWidgets import QMainWindow, QFileDialog, QToolBar, QStatusBar, QMessageBox, QMenu, QToolButton, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QApplication
from PySide6.QtGui     import QAction, QKeySequence, QIcon, QPixmap, QPainter, QActionGroup
from PySide6.QtCore    import Qt, QSize, QByteArray, QEvent, QTimer
from dataclasses import dataclass, field

from core.graph    import Graph
from gui.node_editor import NodeEditorScene, NodeEditorView, MinimapWidget
from gui.panels.manager import PanelManager
from core.registry import NODE_CLASS_MAPPINGS
from gui.theme import *
from gui.logger import log, Level
from gui.widgets.basic_shapes import ShapeDrawer, IconColors
from gui.widgets.icon_provider import load_icon
from gui.items.wire import ConnectionItem
from core.plugins import (
    resolve_whl_packages, get_whl_dir,
    find_whl_for_package, select_compatible_whl_url,
    download_whl, is_in_main_venv,
)
from gui.menu.plugin_manager_dialog import PluginManagerDialog
from core.paths import app_root
from core.plugins import PluginLoader
from core.registry import get_default_registry


def create_icon(shape_func, color=IconColors.DEFAULT, size=16) -> QIcon:
    """Create a QIcon using the ShapeDrawer drawing functions."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(color)
    
    painter.setBrush(Qt.NoBrush)
    shape_func(painter, 0, 0, size)
    
    painter.end()
    return QIcon(pixmap)

@dataclass(eq=False)
class NavNode:
    path: str
    graph: Graph
    scene: NodeEditorScene
    parent: NavNode | None = None
    children: dict[str, NavNode] = field(default_factory=dict) # path -> NavNode
    has_cycle: bool = False
    exec_error: bool = False


class MainWindow(QMainWindow):
    def __init__(self, on_progress: callable | None = None) -> None:
        super().__init__()
        self.setWindowTitle("SrcGraph")
        self.resize(1280, 800)
        self.setStyleSheet(MAIN_STYLESHEET)
        self._on_progress = on_progress

        self._setup_crash_reporting()
        self._progress("Initializing core…", 20)

        self.graph = Graph()
        self.graph.project_dir = None
        self.graph.qc_output_dir = None
        self.scene = NodeEditorScene(self.graph)
        self.view  = NodeEditorView(self.scene)
        self._nav_root = NavNode("", self.graph, self.scene)
        self._current_nav = self._nav_root
        self._progress("Starting renderer…", 30)

        # Set up node registry for undo/redo deserialization
        self._setup_undo_registry()
        main_container = QWidget()
        self.main_layout = QVBoxLayout(main_container)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.main_layout.addWidget(self.view)
        self.setCentralWidget(main_container)

        self.view.compile_requested.connect(lambda: self._execute())
        self.view.subgraph_requested.connect(self._on_subgraph_requested)

        self._project_path = ""
        self._recent_files = []
        self._dirty = False
        self._is_switching = False
        self._is_executing = False
        self._disabled_plugins: set[str] = set()

        # Settings
        self._show_full_path_in_title = False  # Default to show just filename

        self._pre_load_disabled_plugins()
        self._build_toolbar()
        self._setup_shortcuts()
        
        # Initialize Panel System
        self.panel_manager = PanelManager(self)
        self._progress("Loading panels…", 40)
        self.panel_manager.discover_and_load()

        # Update window title
        self._update_window_title()
        self._setup_view_overlays()
        self._progress("Setting up panels…", 55)
        self.panel_manager.initialize_all()
        self._apply_initial_layout()

        self._build_statusbar()
        self._update_status_right()
        self.scene.graph_changed.connect(self._on_changed)

        self._progress("Loading plugins…", 65)
        self._setup_plugin_whls()
        self._progress("Initializing plugins…", 75)
        self._load_plugins()
        self.panel_manager.load_and_setup_plugin_panels()

        exec_p = self.panel_manager.get_widget("ExecutionDock")
        if exec_p:
            exec_p.execution_started.connect(lambda _n: self._on_execution_lock(True))
            exec_p.execution_finished.connect(lambda _n, _r: self._on_execution_lock(False))

        default_ws = self._get_default_workspace_path()
        self._progress("Restoring workspace…", 85)
        self._load_layout(default_ws)
        self._progress("Opening project…", 95)
        self._load_config()

        # Command-line arguments override the workspace's last project (e.g., from reload)
        if len(sys.argv) > 1:
            arg_path = sys.argv[1]
            if os.path.isfile(arg_path):
                self._nav_root = None
                self._current_nav = None
                self._load_file(arg_path)

    def _progress(self, message: str, percent: int) -> None:
        """Emit progress update to splash screen."""
        if self._on_progress:
            self._on_progress(message, percent)

    #  toolbar

    def get_external_state(self) -> dict:
        exec_p = self.panel_manager.get_widget("ExecutionDock")
        return {
            "execution": exec_p.get_project_state() if exec_p else [],
            "minimap": {
                "visible": self.minimap_toggle_btn.isChecked(),
                "show_colors": self.minimap_colors_btn.isChecked(),
                "show_links": self.minimap_links_btn.isChecked(),
                "show_errors": self.minimap_errors_btn.isChecked()
            }
        }

    def set_external_state(self, state: dict) -> None:
        exec_p = self.panel_manager.get_widget("ExecutionDock")
        if exec_p:
            # Preserve checkbox state - checked/unchecked is not undoable
            saved_disabled = {s.name: set(s.disabled_nodes) for s in exec_p.sessions.values()}
            exec_p.set_project_state(state.get("execution", []))
            for s in exec_p.sessions.values():
                if s.name in saved_disabled:
                    s.disabled_nodes = saved_disabled[s.name]
            exec_p._refresh_node_list()
        
        # Restore minimap state
        minimap_state = state.get("minimap", {})
        if minimap_state:
            # Set minimap visibility
            visible = minimap_state.get("visible", True)
            self.minimap_toggle_btn.setChecked(visible)
            self.minimap_widget.setVisible(visible)
            
            # Set minimap options
            self.minimap_colors_btn.setChecked(minimap_state.get("show_colors", True))
            self.minimap_links_btn.setChecked(minimap_state.get("show_links", True))
            self.minimap_errors_btn.setChecked(minimap_state.get("show_errors", True))
            
            # Apply options to minimap widget
            self.minimap_widget.show_node_colors = minimap_state.get("show_colors", True)
            self.minimap_widget.show_links = minimap_state.get("show_links", True)
            self.minimap_widget.render_error_state = minimap_state.get("show_errors", True)
            
            # Update minimap display
            self.minimap_widget.update()

    def _build_toolbar(self) -> None:
        tb = QToolBar()
        tb.setObjectName("MainToolBar")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        tb.setContextMenuPolicy(Qt.PreventContextMenu)
        self.addToolBar(Qt.TopToolBarArea, tb)

        file_btn = QToolButton()
        file_btn.setText("File")
        file_btn.setPopupMode(QToolButton.InstantPopup)
        
        file_menu = QMenu(self)
        
        def add_act(menu, label, shortcut, slot):
            a = menu.addAction(label)
            if shortcut: a.setShortcut(QKeySequence(shortcut))
            a.triggered.connect(slot)
            return a

        add_act(file_menu, "New",  "Ctrl+N", self._new)
        add_act(file_menu, "Open", "Ctrl+O", self._open)

        self.recent_menu = QMenu("Open Recent", self)
        file_menu.addMenu(self.recent_menu)

        file_menu.addSeparator()
        add_act(file_menu, "Save", "Ctrl+S", self._save)
        add_act(file_menu, "Save As...", "Ctrl+Shift+S", self._save_as)

        file_menu.addSeparator()
        add_act(file_menu, "Reload", "Ctrl+R", self._reload)
        add_act(file_menu, "Exit", "Alt+F4", self.close)
        
        file_btn.setMenu(file_menu)
        tb.addWidget(file_btn)

        # Panels Menu
        self.panels_btn = QToolButton()
        self.panels_btn.setText("View")
        self.panels_btn.setPopupMode(QToolButton.InstantPopup)
        self.panels_menu = QMenu(self)
        self.panels_btn.setMenu(self.panels_menu)
        
        # Workspace submenu
        workspace_menu = QMenu("Workspace", self)
        workspace_menu.addAction("Save Layout...", self._on_save_layout_clicked)
        workspace_menu.addAction("Load Layout...", self._on_load_layout_clicked)
        workspace_menu.addAction("Reset Workspace", self._reset_layout)
        self.panels_menu.addMenu(workspace_menu)
        
        workspace_menu.addSeparator()
        self._update_workspace_list(workspace_menu)
        
        self.panels_menu.addSeparator()
        tb.addWidget(self.panels_btn)

        # Settings Menu
        self.settings_btn = QToolButton()
        self.settings_btn.setText("Settings")
        # Settings Menu
        settings_menu = QMenu("Settings", self)
        
        title_act = QAction("Show Full Path in Title", self)
        title_act.setCheckable(True)
        title_act.setChecked(self._show_full_path_in_title)
        title_act.triggered.connect(self._toggle_title_display)
        settings_menu.addAction(title_act)
        
        self.debug_act = QAction("Show Debug Messages", self)
        self.debug_act.setCheckable(True)
        self.debug_act.setChecked(log.min_level == Level.DEBUG)
        self.debug_act.triggered.connect(self._on_toggle_debug)
        settings_menu.addAction(self.debug_act)
        
        # Time Unit Settings
        settings_menu.addSeparator()
        
        wire_group = QActionGroup(self)
        wire_group.setExclusive(True)
        
        self.wire_spline_act = QAction("Wire Style: Spline", self)
        self.wire_spline_act.setCheckable(True)
        self.wire_spline_act.setChecked(ConnectionItem.wire_style == "spline")
        self.wire_spline_act.triggered.connect(lambda: self._set_wire_style("spline"))
        
        self.wire_linear_act = QAction("Wire Style: Linear", self)
        self.wire_linear_act.setCheckable(True)
        self.wire_linear_act.setChecked(ConnectionItem.wire_style == "linear")
        self.wire_linear_act.triggered.connect(lambda: self._set_wire_style("linear"))
        
        self.wire_straight_act = QAction("Wire Style: Straight", self)
        self.wire_straight_act.setCheckable(True)
        self.wire_straight_act.setChecked(ConnectionItem.wire_style == "straight")
        self.wire_straight_act.triggered.connect(lambda: self._set_wire_style("straight"))
        
        wire_group.addAction(self.wire_spline_act)
        wire_group.addAction(self.wire_linear_act)
        wire_group.addAction(self.wire_straight_act)
        settings_menu.addAction(self.wire_spline_act)
        settings_menu.addAction(self.wire_linear_act)
        settings_menu.addAction(self.wire_straight_act)
        
        settings_menu.addSeparator()
        time_group = QActionGroup(self)
        time_group.setExclusive(True)

        self.unit_s_act = QAction("Display Seconds (s)", self)
        self.unit_s_act.setCheckable(True)
        self.unit_s_act.setData("s")
        self.unit_s_act.triggered.connect(lambda: self._set_time_unit("s"))
        
        self.unit_ms_act = QAction("Display Milliseconds (ms)", self)
        self.unit_ms_act.setCheckable(True)
        self.unit_ms_act.setData("ms")
        self.unit_ms_act.triggered.connect(lambda: self._set_time_unit("ms"))

        # Set default check state based on current graph unit
        self.unit_ms_act.setChecked(self.graph.time_unit == "ms")
        self.unit_s_act.setChecked(self.graph.time_unit == "s")
        
        time_group.addAction(self.unit_s_act)
        time_group.addAction(self.unit_ms_act)
        settings_menu.addAction(self.unit_s_act)
        settings_menu.addAction(self.unit_ms_act)

        settings_menu.addSeparator()
        settings_menu.addAction("Manage Plugins...", self._open_plugin_manager)

        settings_button = QToolButton()
        settings_button.setText("Settings")
        settings_button.setMenu(settings_menu)
        settings_button.setPopupMode(QToolButton.InstantPopup)
        tb.addWidget(settings_button)

    def _set_wire_style(self, style: str) -> None:
        ConnectionItem.wire_style = style
        
        def refresh_scene(scene):
            for conn, ci in scene._conn_items:
                ci._refresh()
                ci.update()
            
        refresh_scene(self.scene)
        stack = [self._nav_root] if self._nav_root else []
        while stack:
            node = stack.pop()
            if node.scene != self.scene:
                refresh_scene(node.scene)
            stack.extend(node.children.values())
            
        self._save_config()
        log.info(f"Wire style set to: {style}")

    def _on_toggle_debug(self, enabled: bool) -> None:
        log.min_level = Level.DEBUG if enabled else Level.INFO
        log.info(f"Console debug messages {'enabled' if enabled else 'disabled'}")
        
    def _set_time_unit(self, unit: str) -> None:
        self.graph.time_unit = unit
        for item in self.scene._node_items.values():
            item.update()
        self._save_config()
        log.info(f"Execution time unit set to: {unit}")

    def _toggle_title_display(self) -> None:
        """Toggle between showing filename or full path in window title."""
        self._show_full_path_in_title = not self._show_full_path_in_title
        self._update_window_title()
        log.info(f"Title display: {'full path' if self._show_full_path_in_title else 'filename only'}")

    def _setup_shortcuts(self) -> None:
        self._undo_act = QAction("Undo", self)
        self._undo_act.setShortcut(QKeySequence.Undo)
        self._undo_act.setShortcutContext(Qt.WindowShortcut)
        self._undo_act.triggered.connect(self._on_undo)
        self.addAction(self._undo_act)

        self._redo_act = QAction("Redo", self)
        self._redo_act.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self._redo_act.setShortcutContext(Qt.WindowShortcut)
        self._redo_act.triggered.connect(self._on_redo)
        self.addAction(self._redo_act)

    def _on_undo(self) -> None:
        if self._is_executing:
            return
        if self.scene:
            self.scene.undo_stack.undo()

    def _on_redo(self) -> None:
        if self._is_executing:
            return
        if self.scene:
            self.scene.undo_stack.redo()

    def _on_execution_lock(self, locked: bool) -> None:
        self._is_executing = locked
        self._undo_act.setEnabled(not locked)
        self._redo_act.setEnabled(not locked)
        self.panel_manager.notify_execution_lock(locked)

    def _guard_execution(self, action: str = "this action") -> bool:
        if self._is_executing:
            QMessageBox.warning(self, "Execution Running",
                f"Cannot perform '{action}' while the graph is executing.")
            return True
        return False

    def _setup_view_overlays(self) -> None:
        """Setup docking options and non-docking overlays like the Minimap."""
        self.setDockOptions(QMainWindow.AnimatedDocks | QMainWindow.AllowTabbedDocks)

        self.setCorner(Qt.BottomLeftCorner, Qt.LeftDockWidgetArea)
        self.setCorner(Qt.BottomRightCorner, Qt.RightDockWidgetArea)
        
        # Minimap Overlay (In-editor)
        self.minimap_widget = MinimapWidget(self.view)
        self.minimap_widget.setParent(self.view)
        self.minimap_widget.setFixedSize(300, 180)
        self.minimap_widget.closed.connect(lambda: self.minimap_toggle_btn.setChecked(False))

        # Floating View Controls Bar
        self.view_controls = QWidget(self.view)
        self.view_controls.setFixedHeight(30)
        self.view_controls.setStyleSheet(VIEW_CONTROLS_STYLE)
        
        ctrl_layout = QHBoxLayout(self.view_controls)
        ctrl_layout.setContentsMargins(4, 0, 4, 0)
        ctrl_layout.setSpacing(2)

        # Navigation / Focus Button
        nav_btn = QPushButton("✜")
        nav_btn.setToolTip("Focus Center")
        nav_btn.clicked.connect(lambda: (self.view.centerOn(0, 0), self.view.view_changed.emit()))
        ctrl_layout.addWidget(nav_btn)
        
        # Zoom Controls
        ctrl_layout.addSpacing(4)
        fit_btn = QPushButton("⛶")
        fit_btn.setToolTip("Fit View")
        fit_btn.clicked.connect(lambda: (self.view.fitInView(self.scene.itemsBoundingRect(), Qt.KeepAspectRatio), self.view.view_changed.emit()))
        ctrl_layout.addWidget(fit_btn)

        self.zoom_val_btn = QPushButton("100%")
        self.zoom_val_btn.setToolTip("Reset Zoom")
        self.zoom_val_btn.clicked.connect(lambda: (self.view.resetTransform(), self.view.view_changed.emit()))
        ctrl_layout.addWidget(self.zoom_val_btn)
        
        # Minimap Toggle
        ctrl_layout.addSpacing(8)
        self.minimap_toggle_btn = QPushButton()
        self.minimap_toggle_btn.setIcon(load_icon("windowapp"))
        self.minimap_toggle_btn.setCheckable(True)
        self.minimap_toggle_btn.setChecked(True)
        self.minimap_toggle_btn.setToolTip("Toggle Minimap")
        self.minimap_toggle_btn.toggled.connect(self._toggle_minimap)
        ctrl_layout.addWidget(self.minimap_toggle_btn)

        # Minimap Options
        ctrl_layout.addSpacing(4)
        self.minimap_colors_btn = QPushButton()
        self.minimap_colors_btn.setIcon(load_icon("twotone_circle"))
        self.minimap_colors_btn.setCheckable(True)
        self.minimap_colors_btn.setChecked(True)
        self.minimap_colors_btn.setToolTip("Toggle Node Colors in Minimap")
        self.minimap_colors_btn.toggled.connect(lambda checked: self._toggle_minimap_option('colors', checked))
        ctrl_layout.addWidget(self.minimap_colors_btn)
        
        self.minimap_links_btn = QPushButton()
        self.minimap_links_btn.setIcon(load_icon("curve", color=IconColors.CONNECT.name()))
        self.minimap_links_btn.setCheckable(True)
        self.minimap_links_btn.setChecked(True)
        self.minimap_links_btn.setToolTip("Toggle Links in Minimap")
        self.minimap_links_btn.toggled.connect(lambda checked: self._toggle_minimap_option('links', checked))
        ctrl_layout.addWidget(self.minimap_links_btn)
        
        self.minimap_errors_btn = QPushButton()
        self.minimap_errors_btn.setIcon(load_icon("warning", color=COLOR_ERROR))
        self.minimap_errors_btn.setCheckable(True)
        self.minimap_errors_btn.setChecked(True)
        self.minimap_errors_btn.setToolTip("Toggle Error State in Minimap")
        self.minimap_errors_btn.toggled.connect(lambda checked: self._toggle_minimap_option('errors', checked))
        ctrl_layout.addWidget(self.minimap_errors_btn)


        self.view.installEventFilter(self)

        # Update zoom and coordinates when view changes
        self.view.view_changed.connect(self._update_view_info)
        self.view.view_changed.connect(self.minimap_widget.update)

        self._update_minimap_overlay_pos()
        self.scene.graph_changed.connect(self.minimap_widget.update)
        self.scene.changed.connect(lambda _: self.minimap_widget.update())
        
        # Initial update of zoom and coordinates
        self._update_view_info()

    def _toggle_wires_visibility(self, visible: bool) -> None:
        """Toggle visibility of all connection wires in the scene."""
        for pair in self.scene._conn_items:
            pair[1].setVisible(visible)
        self.minimap_widget.show_links = visible
        self.minimap_widget.update()

    def _toggle_minimap_option(self, option: str, enabled: bool) -> None:
        """Toggle minimap display options."""
        if option == 'colors':
            self.minimap_widget.show_node_colors = enabled
        elif option == 'links':
            self.minimap_widget.show_links = enabled
        elif option == 'errors':
            self.minimap_widget.render_error_state = enabled
        self.minimap_widget.update()
        # Save config when minimap options change
        self._save_config()

    def _apply_initial_layout(self) -> None:
        pass

    def _get_default_workspace_path(self) -> str:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "workspace", "default.json")

    def _get_config_path(self) -> str:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, "config", "app_config.json")

    def _save_config(self) -> None:
        """Save application configuration (recent files, last project, path stack)."""
        try:
            config_path = self._get_config_path()
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            config_data = {
                "recent_files": self._recent_files,
                "last_project": self._project_path,
                "time_unit": self.graph.time_unit,
                "wire_style": ConnectionItem.wire_style,
                "minimap": self.get_external_state().get("minimap", {}),
                "disabled_plugins": sorted(self._disabled_plugins),
            }
            with open(config_path, 'w') as f:
                json.dump(config_data, f, indent=4)
        except Exception as e:
            print(f"Failed to save config: {e}")

    def _load_config(self) -> None:
        """Load application configuration (recent files, last project, path stack)."""
        config_path = self._get_config_path()
        if not os.path.exists(config_path):
            return
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
            self._disabled_plugins = set(config_data.get("disabled_plugins", []))

            if "recent_files" in config_data:
                self._recent_files = config_data["recent_files"]
                self._update_recent_files_menu()
            
            # Load Time Unit
            unit = config_data.get("time_unit", "ms")
            self.graph.time_unit = unit
            if hasattr(self, "unit_ms_act"):
                self.unit_ms_act.setChecked(unit == "ms")
                self.unit_s_act.setChecked(unit == "s")

            # Load Wire Style
            style = config_data.get("wire_style", "spline")
            ConnectionItem.wire_style = style
            if hasattr(self, "wire_spline_act"):
                self.wire_spline_act.setChecked(style == "spline")
                self.wire_linear_act.setChecked(style == "linear")
                self.wire_straight_act.setChecked(style == "straight")
                
            if "last_project" in config_data and len(sys.argv) <= 1:
                # Fallback for old config format
                lp = config_data["last_project"]
                if lp and os.path.exists(lp):
                    self._nav_root = None
                    self._current_nav = None
                    self._load_file(lp)
            
            # Load minimap state
            if "minimap" in config_data:
                minimap_state = config_data["minimap"]
                if minimap_state:
                    # Set minimap visibility
                    visible = minimap_state.get("visible", True)
                    self.minimap_toggle_btn.setChecked(visible)
                    self.minimap_widget.setVisible(visible)
                    
                    # Set minimap options
                    self.minimap_colors_btn.setChecked(minimap_state.get("show_colors", True))
                    self.minimap_links_btn.setChecked(minimap_state.get("show_links", True))
                    self.minimap_errors_btn.setChecked(minimap_state.get("show_errors", True))
                    
                    # Apply options to minimap widget
                    self.minimap_widget.show_node_colors = minimap_state.get("show_colors", True)
                    self.minimap_widget.show_links = minimap_state.get("show_links", True)
                    self.minimap_widget.render_error_state = minimap_state.get("show_errors", True)
                    
                    # Update minimap display
                    self.minimap_widget.update()
        except Exception as e:
            print(f"Failed to load config: {e}")

    def _save_layout(self, path: str) -> None:
        """Save layout data (geometry, state) to specified path."""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            layout_data = {
                "geometry": self.saveGeometry().toHex().data().decode(),
                "state": self.saveState().toHex().data().decode(),
            }
            with open(path, 'w') as f:
                json.dump(layout_data, f, indent=4)
        except Exception as e:
            print(f"Failed to save layout: {e}")

    def _load_layout(self, path: str) -> None:
        """Load layout data (geometry, state) from specified path."""
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r') as f:
                layout_data = json.load(f)
            if "geometry" in layout_data:
                self.restoreGeometry(QByteArray.fromHex(layout_data["geometry"].encode()))
            if "state" in layout_data:
                self.restoreState(QByteArray.fromHex(layout_data["state"].encode()))
        except Exception as e:
            print(f"Failed to load layout: {e}")

    def _on_save_layout_clicked(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save Layout", "", "JSON (*.json)")
        if path:
            # Prevent overwriting the default workspace file
            default_path = self._get_default_workspace_path()
            if os.path.abspath(path) == os.path.abspath(default_path):
                QMessageBox.warning(self, "Cannot Overwrite",
                    "Cannot overwrite the default workspace file.\n\n"
                    "Please choose a different filename.")
                return
            self._save_layout(path)
            # Update workspace list after saving
            self._update_workspace_list()

    def _on_load_layout_clicked(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Layout", "", "JSON (*.json)")
        if path:
            self._load_layout(path)

    def _update_workspace_list(self, menu=None) -> None:
        """Update the workspace list in specified menu (max 8 items)."""
        if menu is None:
            menu = self.panels_menu
            
        workspace_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace")
        
        # Clear existing workspace actions (keep the ones before the separator)
        actions = menu.actions()
        separator_index = None
        for i, action in enumerate(actions):
            if action.isSeparator():
                separator_index = i
                break
        
        if separator_index is not None:
            # Remove actions after the first separator and before the last separator
            for i in range(len(actions) - 1, separator_index, -1):
                if actions[i].isSeparator():
                    break
                menu.removeAction(actions[i])
        
        # List workspace files
        try:
            workspace_files = []
            if os.path.exists(workspace_dir):
                for file in os.listdir(workspace_dir):
                    if file.endswith('.json'):
                        workspace_files.append(file)
                
                # Sort by modification time (newest first)
                workspace_files.sort(key=lambda f: os.path.getmtime(os.path.join(workspace_dir, f)), reverse=True)
                
                # Limit to 8 items
                workspace_files = workspace_files[:8]
                
                # Add workspace actions
                for file in workspace_files:
                    workspace_name = os.path.splitext(file)[0]
                    action = QAction(workspace_name, self)
                    action.triggered.connect(lambda checked, f=file: self._load_workspace(f))
                    menu.addAction(action)
                    
        except Exception as e:
            print(f"Failed to update workspace list: {e}")
    
    def _load_workspace(self, filename: str) -> None:
        """Load a specific workspace file."""
        workspace_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace", filename)
        self._load_layout(workspace_path)

    def _reset_layout(self) -> None:
        # Load default.json layout
        default_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace", "default.json")
        self._load_layout(default_path)

    def eventFilter(self, watched, event) -> bool:
        if watched == self.view and event.type() == QEvent.Resize:
            self._update_minimap_overlay_pos()
        return super().eventFilter(watched, event)

    def _update_minimap_overlay_pos(self) -> None:
        if not hasattr(self, "minimap_widget"): return
        w, h = self.view.width(), self.view.height()
        
        minimap_size = self.minimap_widget.size()
        minimap_width = minimap_size.width()
        minimap_height = minimap_size.height()
        
        # Position Minimap at bottom right with margin
        margin_x = 8
        margin_y = 40   
        minimap_x = w - minimap_width - margin_x
        minimap_y = h - minimap_height - margin_y
        self.minimap_widget.move(minimap_x, minimap_y)
        
        # Position Control Bar flush with right edge
        self.view_controls.adjustSize()
        control_bar_x = w - self.view_controls.width() - 10
        control_bar_y = h - self.view_controls.height() - 10
        self.view_controls.move(control_bar_x, control_bar_y)

    
    def _toggle_minimap(self) -> None:
        """Toggle minimap visibility and reposition zoom/coordinate labels."""
        is_visible = self.minimap_toggle_btn.isChecked()
        self.minimap_widget.setVisible(is_visible)
        self._update_minimap_overlay_pos()
        # Save config when minimap visibility changes
        self._save_config()
    
    def _update_view_info(self) -> None:
        """Update zoom and coordinate information displays."""
        if not hasattr(self, "zoom_val_btn"):
            return
            
        # Get zoom level
        transform = self.view.transform()
        zoom = transform.m11() * 100  # Convert to percentage
        self.zoom_val_btn.setText(f"{zoom:.0f}%")

    def closeEvent(self, event) -> None:
        if self._is_executing:
            reply = QMessageBox.warning(
                self, "Execution Running",
                "A graph is currently executing. Force quit anyway?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No:
                event.ignore()
                return
            exec_w = self.panel_manager.get_widget("ExecutionDock")
            if exec_w and hasattr(exec_w, "teardown"):
                exec_w.teardown()

        if self._maybe_save():
            exec_w = self.panel_manager.get_widget("ExecutionDock")
            if exec_w and hasattr(exec_w, "teardown"):
                exec_w.teardown()
            # Save layout to autosave location
            autosave_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "workspace", "autosave.json")
            self._save_layout(autosave_path)
            # Save application config
            self._save_config()

            self._cleanup_crash_reporting()
            event.accept()
        else:
            event.ignore()

    def changeEvent(self, event: QEvent) -> None:
        """Trigger asset status refresh when the application window is activated."""
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            assets = self.panel_manager.get_widget("AssetDock")
            if assets:
                assets.refresh_status()
        super().changeEvent(event)

    def _update_status_right(self) -> None:
        if not hasattr(self, "_status_right"):
            return
        n = len(self.graph.nodes) if self.graph else 0
        c = len(self.graph.connections) if self.graph else 0
        self._status_right.setText(f"{n} nodes  {c} wires")

    def _build_statusbar(self) -> None:
        sb = QStatusBar()
        self.setStatusBar(sb)

        self._status_right = QLabel()
        self._status_right.setStyleSheet("padding-right: 8px; background: transparent;")
        sb.addPermanentWidget(self._status_right)
        self._update_status_right()

    #  slots 

    def remove_asset(self, path: str) -> None:
        """Remove an asset from the project and update all panels."""
        if path not in self.graph.get_ext_store("assets", []):
            return

        with self.scene._undo_manager.transaction(f"Remove Asset: {os.path.basename(path)}"):
            self.graph.get_ext_store("assets", []).remove(path)

            self.scene.on_asset_removed(path)

            assets_panel = self.panel_manager.get_widget("AssetDock")
            if assets_panel:
                assets_panel.refresh()

    def _on_changed(self) -> None:
        self._dirty = True
        self.graph._is_dirty = True
        if self._current_nav:
            self._sync_nav_tree(self._current_nav)

            # Propagate dirty state up the hierarchy so parent SubgraphNodes refresh.
            # This ensures that if a subgraph is modified, its representation in the 
            # parent graph updates immediately.
            curr = self._current_nav
            child_path = os.path.abspath(curr.path) if curr.path else ""
            while curr and curr.parent and child_path:
                p = curr.parent
                notified = False
                for node in p.graph.nodes.values():
                    if node.__class__.__name__ == "SubgraphNode":
                        path = node.inputs.get("graph_path", {}).value
                        if path:
                            full_path = path
                            if not os.path.isabs(path) and p.graph.project_dir:
                                full_path = os.path.normpath(os.path.join(p.graph.project_dir, path))
                            if os.path.abspath(full_path) == child_path:
                                p.scene._after_node_mutation(node.id)
                                notified = True
                if notified:
                    p.scene._flush_updates()
                curr = p
                child_path = os.path.abspath(curr.path) if curr.path else ""

        self.panel_manager.update_context(self.graph, self.scene)
        self._update_status_right()

    def _on_scene_selection_changed(self) -> None:
        inspector = self.panel_manager.get_widget("NodeInspectorDock")
        if inspector:
            inspector.refresh()

    def _setup_undo_registry(self) -> None:
        """Set up node registry for the undo manager to enable proper deserialization."""
        if hasattr(self.scene, '_undo_manager'):
            self.scene._undo_manager.set_node_registry(NODE_CLASS_MAPPINGS)

    def _pre_load_disabled_plugins(self) -> None:
        """Read only disabled_plugins from config before plugins are discovered."""
        config_path = self._get_config_path()
        if not os.path.exists(config_path):
            return
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
            self._disabled_plugins = set(data.get("disabled_plugins", []))
        except Exception:
            pass

    def _setup_plugin_whls(self) -> None:
        """Download missing WHL packages declared by enabled plugins.

        Each plugin stores its ``.whl`` files under ``<plugin>/whl/``.  If a
        WHL is already present (user-placed or previously downloaded) it is
        used as-is without re-downloading.  Mounting happens later inside
        ``PluginLoader.discover()`` via ``mount_plugin_whls()``.

        When any new WHL is downloaded the user is asked to restart so the
        freshly-written files are picked up on the next launch.
        """
        plugins_dir = app_root() / "plugins"
        if not plugins_dir.is_dir():
            return

        needs_download: list[tuple[Path, dict, str]] = []  # (whl_dir, pkg, url)

        for entry in sorted(plugins_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            if entry.name in self._disabled_plugins:
                continue
            if not (entry / "addoninfo.json").exists():
                continue

            whl_dir = get_whl_dir(entry)
            for pkg in resolve_whl_packages(entry):
                pkg_name = pkg["name"]
                found, ver = is_in_main_venv(pkg_name)
                if found:
                    log.info(
                        f"[Packages] '{entry.name}' requires '{pkg_name}'; "
                        f"using main-venv version {ver}."
                    )
                    continue
                # Pre-placed or previously-downloaded WHL takes priority.
                if find_whl_for_package(pkg_name, whl_dir):
                    continue
                url = select_compatible_whl_url(pkg.get("urls") or [])
                if url:
                    needs_download.append((whl_dir, pkg, url))
                else:
                    log.warning(
                        f"[Packages] '{entry.name}' requires '{pkg_name}' but no compatible "
                        f"WHL found in whl/ and no compatible URL declared."
                    )

        if not needs_download:
            return

        console_panel = self.panel_manager.get_panel("ConsoleDock")
        if console_panel:
            console_panel.show()
        self.show()
        QApplication.processEvents()

        downloaded_any = False
        for whl_dir, pkg, url in needs_download:
            def _cb(msg: str, _app: type = QApplication) -> None:
                if msg:
                    log.info(f"  whl | {msg}")
                    _app.processEvents()

            result = download_whl(url, whl_dir, progress_cb=_cb)
            if result:
                downloaded_any = True
                log.info(f"[Packages] Downloaded '{result.name}'.")
            else:
                log.error(
                    f"[Packages] Failed to download '{pkg['name']}' from {url}. "
                    f"Plugin may not work correctly."
                )
            QApplication.processEvents()

        if downloaded_any:
            reply = QMessageBox.question(
                self,
                "Restart Required",
                "New plugin packages were downloaded.\nRestart the application to load them.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if reply == QMessageBox.StandardButton.Yes:
                import os
                os.execv(sys.executable, [sys.executable] + sys.argv)

    def _load_builtin_types(self) -> None:
        """Load built-in port type registrations from the types/ directory."""
        import importlib.util
        types_dir = app_root() / "types"
        if not types_dir.is_dir():
            return
        for py_file in sorted(types_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = f"builtin_type_{py_file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    sys.modules[module_name] = module
                    spec.loader.exec_module(module)
            except Exception as exc:
                print(f"[BuiltinTypes] Failed to load '{py_file.name}': {exc}")

    def _load_plugins(self) -> None:
        """Discover and load plugins from the plugins/ directory."""
        self._load_builtin_types()
        plugins_dir = app_root() / "plugins"
        loaded = PluginLoader(get_default_registry()).discover(plugins_dir, disabled=self._disabled_plugins)
        if loaded:
            log.info(f"Loaded plugins: {', '.join(loaded)}")

    def _open_plugin_manager(self) -> None:
        plugins_dir = app_root() / "plugins"
        dlg = PluginManagerDialog(plugins_dir, self._disabled_plugins, parent=self)
        if dlg.exec() == PluginManagerDialog.Accepted:
            new_disabled = dlg.get_disabled()
            if new_disabled != self._disabled_plugins:
                self._disabled_plugins = new_disabled
                self._save_config()
                btn = QMessageBox.question(
                    self, "Restart Required",
                    "Plugin changes will take effect after restart.\nRestart now?",
                )
                if btn == QMessageBox.Yes:
                    self._reload()

    def _new(self) -> None:
        if self._guard_execution("New File"): return
        if not self._maybe_save(): return
        self._nav_root = None
        self._current_nav = None

        new_graph = Graph()
        new_scene = NodeEditorScene(new_graph)
        
        self._nav_root = NavNode("", new_graph, new_scene)
        self._switch_to_context(self._nav_root)
        self._dirty = False
        self.statusBar().showMessage("New graph")

    def _update_window_title(self) -> None:
        """Update window title based on current project state and settings."""
        if self._project_path:
            if self._show_full_path_in_title:
                # Show full path
                self.setWindowTitle(f"SrcGraph - {self._project_path}")
            else:
                # Show just filename
                project_name = os.path.basename(self._project_path)
                self.setWindowTitle(f"SrcGraph - {project_name}")
        else:
            # Show just app name when no project is loaded
            self.setWindowTitle("SrcGraph")
    
    def _save(self) -> bool:
        """Save all dirty graphs in the navigation stack, or current graph if clean."""
        exec_w = self.panel_manager.get_widget("ExecutionDock")
        if exec_w and getattr(exec_w, '_eyedropper_active', False):
            exec_w._cancel_eyedropper()
        if self.graph:
            if self._current_nav and self._current_nav.path:
                if not self._save_to_path(self._current_nav.path, self.graph):
                    return False
            elif self._current_nav:
                # If no path yet, open Save As dialog
                if not self._save_as():
                    return False

        success = True
        nodes_to_visit = [self._nav_root] if self._nav_root else []
        while nodes_to_visit:
            node = nodes_to_visit.pop()
            nodes_to_visit.extend(node.children.values())
            
            if node == self._current_nav:
                continue
            
            if node.graph._is_dirty:
                # Sync execution state before saving
                exec_p = self.panel_manager.get_widget("ExecutionDock")
                if exec_p and node == self._current_nav:
                    exec_p._sync_to_graph()
                    
                if node.path:
                    if not self._save_to_path(node.path, node.graph):
                        success = False
                elif node == self._current_nav:
                    if not self._save_as():
                        success = False
        return success
    
    def _save_to_path(self, path: str, graph: Graph | None = None, save_type: str = "auto") -> bool:
        """Save specific graph to path."""
        target_graph = graph if graph else self.graph
        
        target_graph.project_dir = os.path.dirname(path)
        
        # Save view state if it's the active graph
        if target_graph == self.graph:
            target_graph.view_state = self.view.get_view_state()
        
        data = target_graph.to_dict()

        try:
            Path(path).write_text(
                json.dumps(data, indent=2), encoding="utf-8"
            )
            
            target_graph._is_dirty = False
            log.debug(f"Successfully {save_type} saved graph to: {path}")
            
            if target_graph == self.graph:
                if self._current_nav:
                    self._current_nav.path = path
                # Check if any part of the tree remains dirty
                any_dirty = False
                stack = [self._nav_root] if self._nav_root else []
                while stack:
                    n = stack.pop()
                    if n.graph._is_dirty:
                        any_dirty = True
                        break
                    stack.extend(n.children.values())
                self._dirty = any_dirty
                self._project_path = path

            self._update_window_title()  # Update window title after saving
            self.statusBar().showMessage(f"Saved  {path}")
            self._add_to_recent_files(path)
            return True
        except Exception as e:
            log.error(f"Failed to save {path}: {e}")
            return False

    def _save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Graph As", self._project_path or "", "SrcGraph (*.srcgraph);;SrcSubgraph (*.srcsubgraph);;All (*)")
        if path:
            self._project_path = path
            self._update_window_title()  # Update window title after save as
            return self._save_to_path(path)  # Call save directly instead of _save() to avoid recursion
        return False

    def _switch_to_context(self, nav_node: NavNode):
        """Swaps the active scene/graph without re-loading from disk if possible."""
        if self._is_executing:
            return
        if self._is_switching:
            return
        self._is_switching = True
        
        # Disable updates on all relevant views to prevent events during transition
        self.view.viewport().setUpdatesEnabled(False)
        graph_map_panel = self.panel_manager.get_panel("GraphMapDock")
        if graph_map_panel and hasattr(graph_map_panel, "map_view"):
            graph_map_panel.map_view.viewport().setUpdatesEnabled(False)

        try:
            if self.scene:
                try: self.scene.graph_changed.disconnect(self._on_changed)
                except: pass
                
                if self.graph: self.graph.view_state = self.view.get_view_state() # Save old view state

                # Auto-save subgraph on navigate-away so the parent SubgraphNode
                # reads a consistent file when it refreshes.
                if (self._current_nav is not None
                        and self._current_nav is not self._nav_root
                        and self._current_nav.path
                        and self._current_nav.graph._is_dirty):
                    try:
                        Path(self._current_nav.path).write_text(
                            json.dumps(self._current_nav.graph.to_dict(), indent=2),
                            encoding="utf-8",
                        )
                        self._current_nav.graph._is_dirty = False
                    except Exception as e:
                        log.error(f"Auto-save subgraph failed: {e}")

            self.graph = nav_node.graph
            self.scene = nav_node.scene

            with self.scene._undo_manager.skip_undo():
                self._project_path = nav_node.path
                self._current_nav = nav_node
                
                self.scene.graph_changed.connect(self._on_changed)
                self._setup_undo_registry()
                
                self.view.setScene(self.scene) # Activate new scene (handles safety flags internally)
                self.panel_manager.update_context(self.graph, self.scene)
                self.view.set_view_state(self.graph.view_state)

                # Force refresh of Subgraph nodes in case their files changed
                # while we were in a different context.
                for node in self.graph.nodes.values():
                    if node.__class__.__name__ == "SubgraphNode":
                        self.scene._after_node_mutation(node.id)
                self.scene._flush_updates()
                
                # Restore execution state for the new context
                exec_p = self.panel_manager.get_widget("ExecutionDock")
                if exec_p and hasattr(self.graph, 'execution_sessions'):
                    exec_p.set_project_state(self.graph.execution_sessions)
            
            self._update_window_title()
            self._update_status_right()
        finally:
            # Re-enable updates on all relevant views
            self.view.viewport().setUpdatesEnabled(True)
            if graph_map_panel and hasattr(graph_map_panel, "map_view"):
                graph_map_panel.map_view.viewport().setUpdatesEnabled(True)
            self._is_switching = False

    def _sync_nav_tree(self, nav_node: NavNode):
        """Recursively discover SubgraphNodes and load them into the tree."""
        if not nav_node or not nav_node.graph:
            return
        nav_node.has_cycle = False
        nav_node.exec_error = False

        subgraph_paths = set()
        for node in nav_node.graph.nodes.values():
            if node.__class__.__name__ == "SubgraphNode":
                path = node.inputs.get("graph_path", {}).value
                if not path:
                    if node.error_msg and "Recursive loop" in node.error_msg:
                        node.error_msg = None
                    continue

                full_path = path
                if not os.path.isabs(path) and nav_node.graph.project_dir:
                    full_path = os.path.normpath(os.path.join(nav_node.graph.project_dir, path))
                abs_path = os.path.abspath(full_path)

                # Cycle Detection: Check if path is an ancestor
                is_cycle = False
                curr_check = nav_node
                while curr_check:
                    if curr_check.path and os.path.abspath(curr_check.path) == abs_path:
                        is_cycle = True
                        break
                    curr_check = curr_check.parent

                item = nav_node.scene._node_items.get(node.id)
                if is_cycle:
                    node.error_msg = f"Recursive loop detected: {os.path.basename(abs_path)}"
                    if item: item.update()
                    nav_node.has_cycle = True
                    log.error(f"[GraphMap] Recursive subgraph loop: '{os.path.basename(abs_path)}' is an ancestor of the current graph")
                else:
                    if node.error_msg and "Recursive loop" in node.error_msg:
                        node.error_msg = None
                    if item: item.update()
                    
                    if os.path.exists(abs_path):
                        subgraph_paths.add(abs_path)

        for p in list(nav_node.children.keys()):
            if p not in subgraph_paths:
                del nav_node.children[p]

        for path in subgraph_paths:
            if path not in nav_node.children:
                try:
                    # Auto-load the subgraph into memory
                    raw = json.loads(Path(path).read_text(encoding="utf-8"))
                    g, s = Graph(), None
                    g.project_dir = os.path.dirname(path)
                    g.load_dict(raw, NODE_CLASS_MAPPINGS)
                    s = NodeEditorScene(g)
                    s._undo_manager.set_node_registry(NODE_CLASS_MAPPINGS)
                    with s._undo_manager.skip_undo(): s.load_from_graph()
                    nav_node.children[path] = NavNode(path, g, s, parent=nav_node)
                except Exception as e:
                    log.error(f"Auto-sync failed for {path}: {e}")
                    continue
            
            self._sync_nav_tree(nav_node.children[path])

    def _maybe_save(self) -> bool:
        """Ask user to save changes if dirty. Returns True to proceed, False to cancel."""
        if not self._dirty:
            return True
        reply = QMessageBox.question(
            self, "Unsaved Changes",
            "You have unsaved changes. Save before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save
        )
        if reply == QMessageBox.Save:
            return self._save()
        elif reply == QMessageBox.Discard:
            return True
        else:
            return False

    def _open(self) -> None:
        if self._guard_execution("Open File"): return
        if not self._maybe_save(): return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Graph", "", "SrcGraph Files (*.srcgraph *.srcsubgraph);;All (*)")
        if path:
            self._nav_root = None
            self._current_nav = None
            self._load_file(path)
            self._add_to_recent_files(path)

    def _load_file(self, path: str) -> None:
        path = os.path.abspath(path)
        if not os.path.exists(path): return

        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            
            new_graph = Graph()
            new_graph.project_dir = os.path.dirname(path)
            new_graph.load_dict(raw, NODE_CLASS_MAPPINGS)
            
            new_scene = NodeEditorScene(new_graph)
            new_scene._undo_manager.set_node_registry(NODE_CLASS_MAPPINGS)
            
            with new_scene._undo_manager.skip_undo():
                new_scene.load_from_graph()

            new_node = NavNode(path, new_graph, new_scene, parent=self._current_nav)
            
            if not self._nav_root:
                self._nav_root = new_node
            elif self._current_nav:
                abs_path = os.path.abspath(path)
                self._current_nav.children[path] = new_node

            self._sync_nav_tree(new_node)
            self._switch_to_context(new_node)
            
            # Restore execution state after switching context
            exec_p = self.panel_manager.get_widget("ExecutionDock")
            if exec_p and hasattr(new_graph, 'execution_sessions'):
                exec_p.set_project_state(new_graph.execution_sessions)
            
            self._dirty = False
            self._update_status_right()
            self.statusBar().showMessage(f"Loaded {path}")

            if getattr(new_graph, '_missing_plugins', []):
                QTimer.singleShot(0, lambda g=new_graph: self._prompt_missing_plugins(g))

            missing = [p for p in new_graph.get_ext_store("assets", []) if not os.path.exists(p)]
            if missing:
                for p in missing:
                    log.info(f"[Assets] Missing file: {p}")
                QTimer.singleShot(0, self._prompt_missing_assets)
        except Exception as e:
            log.error(f"Failed to load {path}: {e}")

    def _prompt_missing_plugins(self, graph) -> None:
        missing = getattr(graph, '_missing_plugins', [])
        if not missing:
            return
        names = "\n".join(f"  • {p}" for p in missing)
        QMessageBox.warning(
            self,
            "Missing Plugins",
            f"This project requires plugins that are not installed:\n\n{names}"
            f"\n\nAffected nodes have been removed from the graph."
            f"\n\nInstall the required plugins and reload the file.",
        )

    def _prompt_missing_assets(self) -> None:
        assets_widget = self.panel_manager.get_widget("AssetDock")
        if assets_widget:
            assets_widget._on_find_missing()

    def _on_subgraph_requested(self, path: str) -> None:
        abs_path = os.path.abspath(path)
        
        # Cycle Detection: Check ancestry
        curr = self._current_nav
        while curr:
            if curr.path == abs_path:
                self.view.show_notification(f"Recursive loop detected!", is_error=True)
                return
            curr = curr.parent

        # Check if already in children (Parallel branch already loaded)
        if self._current_nav and abs_path in self._current_nav.children:
            self._switch_to_context(self._current_nav.children[abs_path])
            return

        self._load_file(abs_path)

    def _reload(self) -> None:
        if not self._maybe_save():
            return
        # Save current layout and config
        default_ws = self._get_default_workspace_path()
        self._save_layout(default_ws)
        self._save_config()

        self._cleanup_crash_reporting()

        # Ensure the next process starts with the current file as the argument
        args = [sys.executable, sys.argv[0]]
        if self._project_path:
            args.append(self._project_path)
        os.execl(sys.executable, *args)

    def _execute(self) -> None:
        """Quick execution - runs current execution panel session."""
        exec = self.panel_manager.get_widget("ExecutionDock")
        if exec:
            exec._execute_current()

    def _add_to_recent_files(self, path: str) -> None:
        if not path or not os.path.exists(path):
            return
        path = os.path.normpath(path)
        if path in self._recent_files:
            self._recent_files.remove(path)
        self._recent_files.insert(0, path)
        self._recent_files = self._recent_files[:8]
        self._update_recent_files_menu()

    def _update_recent_files_menu(self) -> None:
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.clear()
        if not self._recent_files:
            act = self.recent_menu.addAction("No Recent Files")
            act.setEnabled(False)
            return

        for path in self._recent_files:
            name = os.path.basename(path)
            act = self.recent_menu.addAction(name)
            act.setToolTip(path)
            act.triggered.connect(lambda checked=False, p=path: self._on_recent_file_clicked(p))

    def _on_recent_file_clicked(self, path: str) -> None:
        if not self._maybe_save():
            return
        self._nav_root = None
        self._current_nav = None
        self._load_file(path)
        self._add_to_recent_files(path)

    def _setup_crash_reporting(self):
        """Initialize logging for both Python exceptions and C-level fatal crashes."""
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        crash_dir = os.path.join(root_dir, "error")
        os.makedirs(crash_dir, exist_ok=True)

        temp_dir = tempfile.gettempdir()
        try:
            for f in os.listdir(temp_dir):
                if f.startswith("srcgraph_crash_") and f.endswith(".log"):
                    p = os.path.join(temp_dir, f)
                    try:
                        if os.path.getsize(p) > 0:
                            dest = os.path.join(crash_dir, f"fatal_crash_{int(time.time())}_{f}")
                            shutil.move(p, dest)
                        else:
                            os.remove(p)
                    except OSError:
                        pass
        except OSError:
            pass

        # Cleanup empty logs in project crash dir
        for f in os.listdir(crash_dir):
            if f.startswith("fatal_crash_") and f.endswith(".log"):
                p = os.path.join(crash_dir, f)
                try:
                    if os.path.getsize(p) == 0:
                        os.remove(p)
                except OSError:
                    pass

        # We use a temporary file in the system temp directory
        try:
            self._fatal_log_temp = tempfile.NamedTemporaryFile(mode="w", prefix="srcgraph_crash_", suffix=".log", delete=False)
            faulthandler.enable(self._fatal_log_temp)
        except Exception as e:
            print(f"Failed to setup faulthandler: {e}")

        def handle_exception(etype, value, tb):
            timestamp = int(time.time())
            log_path = os.path.join(crash_dir, f"python_exception_{timestamp}.log")
            with open(log_path, "w") as f:
                traceback.print_exception(etype, value, tb, file=f)

            sys.__excepthook__(etype, value, tb)
            QMessageBox.critical(self, "Fatal Error", f"A fatal error occurred.\n\nLog saved to:\n{log_path}")

        sys.excepthook = handle_exception

    def _cleanup_crash_reporting(self):
        """Disable crash reporting and cleanup the temporary log file."""
        if hasattr(self, "_fatal_log_temp"):
            faulthandler.disable()
            temp_path = self._fatal_log_temp.name
            self._fatal_log_temp.close()

            try:
                # If it's not empty, move it to the crash directory
                if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    crash_dir = os.path.join(root_dir, "error")
                    dest = os.path.join(crash_dir, f"fatal_crash_{int(time.time())}.log")
                    shutil.move(temp_path, dest)
                else:
                    # Otherwise delete it
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            except OSError:
                pass