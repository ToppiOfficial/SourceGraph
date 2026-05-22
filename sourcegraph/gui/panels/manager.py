import importlib
import inspect
import pkgutil
from typing import Dict, Type

from PySide6.QtCore import Qt
from sourcegraph.gui.panels.base_panel import BasePanel
from sourcegraph.gui.logger import log

_SKIP = frozenset(('base', 'manager', 'base_panel', 'graph_hierarchy', 'console', '__init__'))


class PanelManager:
    def __init__(self, main_window) -> None:
        self.main_window = main_window
        self.panels: Dict[str, BasePanel] = {}

    def discover_and_load(self):
        """Load all BasePanel subclasses from gui.panels.

        Uses pkgutil.iter_modules instead of os.listdir so this works both
        when running from source and when frozen by PyInstaller (modules live
        in the PYZ archive, not as .py files on disk).

        ConsolePanel is loaded first so it can capture errors from other panels.
        """
        # Load ConsolePanel early so it captures startup errors
        try:
            module = importlib.import_module("sourcegraph.gui.panels.console")
            for _, obj in inspect.getmembers(module):
                if (inspect.isclass(obj) and
                        issubclass(obj, BasePanel) and
                        obj is not BasePanel):
                    self._instantiate_panel(obj)
                    panel = self.panels.get(obj.ID)
                    if panel:
                        panel.setup()
        except Exception as e:
            print(f"Failed to load ConsolePanel early: {e}")

        import sourcegraph.gui.panels as _pkg
        for _finder, modname, _ispkg in sorted(
            pkgutil.iter_modules(_pkg.__path__, _pkg.__name__ + '.')
        ):
            if modname.split('.')[-1] in _SKIP:
                continue
            try:
                module = importlib.import_module(modname)
                for _, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and
                            issubclass(obj, BasePanel) and
                            obj is not BasePanel):
                        self._instantiate_panel(obj)
            except Exception as e:
                log.error(f"Failed to load panel module {modname}: {e}")

    def _instantiate_panel(self, panel_class: Type[BasePanel]):
        try:
            panel = panel_class(self.main_window)
            self.panels[panel.ID] = panel

            self.main_window.addDockWidget(panel.DEFAULT_AREA, panel)

            if hasattr(self.main_window, "panels_menu"):
                self.main_window.panels_menu.addAction(panel.toggleViewAction())
        except Exception as e:
            log.error(f"Error instantiating panel {panel_class.__name__}: {e}")

    def initialize_all(self):
        """Call setup() on all loaded panels except ConsolePanel (already initialized)."""
        for panel in self.panels.values():
            if panel.ID != "ConsoleDock":
                panel.setup()

    def get_panel(self, panel_id: str) -> BasePanel:
        return self.panels.get(panel_id)

    def get_widget(self, panel_id: str):
        panel = self.get_panel(panel_id)
        return panel.get_widget() if panel else None

    def load_and_setup_plugin_panels(self) -> None:
        """Instantiate and initialize panels registered by plugins. Called after _load_plugins()."""
        from sourcegraph.sys.registry import get_plugin_panels
        for panel_class in get_plugin_panels():
            if panel_class.ID not in self.panels:
                self._instantiate_panel(panel_class)
                panel = self.panels.get(panel_class.ID)
                if panel:
                    panel.setup()

    def update_context(self, graph, scene):
        """Propagate graph/scene changes to all panels."""
        for panel in self.panels.values():
            panel.update_context(graph, scene)

    def notify_execution_lock(self, locked: bool) -> None:
        """Broadcast execution lock state to all panels (opt-in via on_execution_lock)."""
        for panel in self.panels.values():
            try:
                panel.on_execution_lock(locked)
            except Exception:
                pass
