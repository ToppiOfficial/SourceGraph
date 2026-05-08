import os
import importlib
import inspect
from typing import Dict, Type
from PySide6.QtCore import Qt
from gui.panels.base_panel import BasePanel
from gui.logger import log

class PanelManager:
    def __init__(self, main_window) -> None:
        self.main_window = main_window
        self.panels: Dict[str, BasePanel] = {}

    def discover_and_load(self):
        """Scans the gui/panels directory and loads all BasePanel subclasses."""
        manager_path = os.path.abspath(__file__)
        panels_dir = os.path.dirname(manager_path)

        for filename in sorted(os.listdir(panels_dir)):
            if filename.endswith(".py") and filename not in ("base.py", "manager.py", "__init__.py", "base_panel.py", "graph_hierarchy.py"):
                module_name = f"gui.panels.{filename[:-3]}"
                try:
                    module = importlib.import_module(module_name)
                    for name, obj in inspect.getmembers(module):
                        if (inspect.isclass(obj) and 
                            issubclass(obj, BasePanel) and 
                            obj is not BasePanel):
                            self._instantiate_panel(obj)
                except Exception as e:
                    log.error(f"Failed to load panel module {module_name}: {e}")

    def _instantiate_panel(self, panel_class: Type[BasePanel]):
        try:
            panel = panel_class(self.main_window)
            self.panels[panel.ID] = panel
            
            # Standard placement
            self.main_window.addDockWidget(panel.DEFAULT_AREA, panel)
            
            # Add to the View menu (Window toggle)
            if hasattr(self.main_window, "panels_menu"):
                self.main_window.panels_menu.addAction(panel.toggleViewAction())
        except Exception as e:
            log.error(f"Error instantiating panel {panel_class.__name__}: {e}")

    def initialize_all(self):
        """Calls setup() on all loaded panels."""
        for panel in self.panels.values():
            panel.setup()

    def get_panel(self, panel_id: str) -> BasePanel:
        return self.panels.get(panel_id)

    def get_widget(self, panel_id: str):
        panel = self.get_panel(panel_id)
        return panel.get_widget() if panel else None

    def update_context(self, graph, scene):
        """Propagate graph/scene changes to all panels."""
        for panel in self.panels.values():
            panel.update_context(graph, scene)