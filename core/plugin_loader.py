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
    """Discovers and loads node classes from plugins/ subdirectories.

    Expected layout:
        plugins/<plugin_name>/nodes/<module>.py

    Each .py file is scanned for BaseNode subclasses and registered.
    Errors in individual plugins are logged and skipped — they never crash the app.
    """

    def __init__(self, registry: "NodeRegistry") -> None:
        self._registry = registry
        self._loaded: list[str] = []

    def discover(self, plugins_dir: Path) -> list[str]:
        """Scan *plugins_dir* for plugin subdirs and load node classes from each."""
        if not plugins_dir.is_dir():
            return []

        plugins_str = str(plugins_dir)
        if plugins_str not in sys.path:
            sys.path.insert(0, plugins_str)

        for entry in sorted(plugins_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            nodes_dir = entry / "nodes"
            if nodes_dir.is_dir():
                try:
                    self._load_plugin_nodes(nodes_dir, entry.name)
                    self._loaded.append(entry.name)
                except Exception as exc:
                    print(f"[PluginLoader] Failed to load plugin '{entry.name}': {exc}")

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
