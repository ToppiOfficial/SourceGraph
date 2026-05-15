from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from core.registry import NodeRegistry
    from core.node import BaseNode


class PluginLoader:
    """Discovers and loads node and panel classes from plugins/ subdirectories.

    Expected layout:
        plugins/<plugin_name>/nodes/<module>.py    — BaseNode subclasses
        plugins/<plugin_name>/panels/<module>.py   — BasePanel subclasses (optional)

    Errors in individual plugins are logged and skipped — they never crash the app.
    """

    def __init__(self, registry: "NodeRegistry") -> None:
        self._registry = registry
        self._loaded: list[str] = []

    def discover(self, plugins_dir: Path, disabled: set[str] | None = None) -> list[str]:
        """Scan *plugins_dir* for plugin subdirs and load node/panel classes from each."""
        if not plugins_dir.is_dir():
            return []

        _disabled = disabled or set()

        plugins_str = str(plugins_dir)
        if plugins_str not in sys.path:
            sys.path.insert(0, plugins_str)

        for entry in sorted(plugins_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            if entry.name in _disabled:
                continue
            loaded_something = False

            # Types must load before nodes so parse_type() resolves them
            # when node module-level code runs.
            types_dir = entry / "types"
            if types_dir.is_dir():
                try:
                    self._load_plugin_types(types_dir, entry.name)
                    loaded_something = True
                except Exception as exc:
                    print(f"[PluginLoader] Failed to load plugin types '{entry.name}': {exc}")

            nodes_dir = entry / "nodes"
            if nodes_dir.is_dir():
                try:
                    self._load_plugin_nodes(nodes_dir, entry.name)
                    loaded_something = True
                except Exception as exc:
                    print(f"[PluginLoader] Failed to load plugin nodes '{entry.name}': {exc}")

            panels_dir = entry / "panels"
            if panels_dir.is_dir():
                try:
                    self._load_plugin_panels(panels_dir, entry.name)
                    loaded_something = True
                except Exception as exc:
                    print(f"[PluginLoader] Failed to load plugin panels '{entry.name}': {exc}")

            if loaded_something:
                self._loaded.append(entry.name)

        return list(self._loaded)

    def _load_plugin_nodes(self, nodes_dir: Path, plugin_name: str) -> None:
        from core.node import BaseNode

        for py_file in sorted(nodes_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = f"plugin_{plugin_name}_{py_file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                for _name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, BaseNode)
                            and obj is not BaseNode
                            and obj.__module__ == module_name
                            and obj.__name__ not in self._registry.node_map()):
                        self._registry.register(obj, source=f"plugin:{plugin_name}")

            except Exception as exc:
                print(f"[PluginLoader] Error loading '{py_file}': {exc}")

    def _load_plugin_types(self, types_dir: Path, plugin_name: str) -> None:
        for py_file in sorted(types_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = f"plugin_{plugin_name}_{py_file.stem}_types"
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)
                # No class scanning — registration is a side effect of exec.
            except Exception as exc:
                print(f"[PluginLoader] Error loading types '{py_file}': {exc}")

    def _load_plugin_panels(self, panels_dir: Path, plugin_name: str) -> None:
        from gui.panels.base_panel import BasePanel
        from core.panel_registry import register_panel

        for py_file in sorted(panels_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = f"plugin_{plugin_name}_{py_file.stem}_panel"
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = module
                spec.loader.exec_module(module)

                for _name, obj in inspect.getmembers(module, inspect.isclass):
                    if (issubclass(obj, BasePanel)
                            and obj is not BasePanel
                            and obj.__module__ == module_name):
                        register_panel(obj)

            except Exception as exc:
                print(f"[PluginLoader] Error loading panel '{py_file}': {exc}")
