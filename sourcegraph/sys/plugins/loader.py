from __future__ import annotations

import inspect
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from sourcegraph.sys.utils.modules import load_plugin_module

if TYPE_CHECKING:
    from sourcegraph.sys.registry.nodes import NodeRegistry
    from sourcegraph.sys.node.base import BaseNode


class PluginLoader:
    """Discovers and loads node and panel classes from plugins/ subdirectories.

    Expected layout:
        plugins/<plugin_name>/nodes/<module>.py    - BaseNode subclasses
        plugins/<plugin_name>/panels/<module>.py   - BasePanel subclasses (optional)

    Errors in individual plugins are logged and skipped - they never crash the app.
    """

    def __init__(self, registry: "NodeRegistry") -> None:
        self._registry = registry
        self._loaded: list[str] = []

    def discover(self, plugins_dir: Path, disabled: set[str] | None = None) -> list[str]:
        """Scan *plugins_dir* for plugin subdirs and load node/panel classes from each.

        Requires each plugin to have an ``addoninfo.json`` with an ``addonid`` field.
        Plugins with duplicate addonids, unresolvable dependencies, or circular
        dependencies are skipped with a console warning.
        Remaining plugins load in dependency order.
        """
        if not plugins_dir.is_dir():
            return []

        _disabled = disabled or set()

        plugins_str = str(plugins_dir)
        if plugins_str not in sys.path:
            sys.path.insert(0, plugins_str)

        from collections import deque
        from sourcegraph.sys.plugins.packages import (
            mount_plugin_whls,
            read_addonid,
            read_plugin_deps,
        )

        # Phase 1: collect valid candidates, deduplicate by addonid.
        candidates: dict[str, dict] = {}
        seen_ids: dict[str, str] = {}

        for entry in sorted(plugins_dir.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            if entry.name in _disabled:
                continue
            addonid = read_addonid(entry)
            if addonid is None:
                print(f"[PluginLoader] Skipping '{entry.name}': no addoninfo.json")
                continue
            if not addonid:
                print(f"[PluginLoader] WARNING: Skipping '{entry.name}': addoninfo.json is missing 'addonid'")
                continue
            if addonid in seen_ids:
                print(
                    f"[PluginLoader] Skipping '{entry.name}': addonid '{addonid}' "
                    f"already claimed by '{seen_ids[addonid]}'"
                )
                continue
            seen_ids[addonid] = entry.name
            candidates[entry.name] = {
                "addonid": addonid,
                "deps": read_plugin_deps(entry),
                "dir": entry,
            }

        if not candidates:
            return []

        # Phase 2: resolve dependencies, propagate skips.
        id_to_folder: dict[str, str] = {v["addonid"]: k for k, v in candidates.items()}
        skipped: set[str] = set()

        changed = True
        while changed:
            changed = False
            for folder, info in candidates.items():
                if folder in skipped:
                    continue
                for dep_id in info["deps"]:
                    dep_folder = id_to_folder.get(dep_id)
                    if dep_folder is None:
                        print(f"[PluginLoader] Skipping '{folder}': dependency '{dep_id}' not found")
                        skipped.add(folder)
                        changed = True
                        break
                    if dep_folder in skipped:
                        print(
                            f"[PluginLoader] Skipping '{folder}': "
                            f"dependency '{dep_id}' ('{dep_folder}') could not load"
                        )
                        skipped.add(folder)
                        changed = True
                        break

        active: dict[str, dict] = {f: info for f, info in candidates.items() if f not in skipped}

        # Phase 3: topological sort (Kahn's algorithm).
        in_degree: dict[str, int] = {f: 0 for f in active}
        dependents: dict[str, list[str]] = {f: [] for f in active}

        for folder, info in active.items():
            for dep_id in info["deps"]:
                dep_folder = id_to_folder.get(dep_id)
                if dep_folder and dep_folder in active:
                    in_degree[folder] += 1
                    dependents[dep_folder].append(folder)

        queue: deque[str] = deque(f for f in active if in_degree[f] == 0)
        load_order: list[str] = []

        while queue:
            folder = queue.popleft()
            load_order.append(folder)
            for dependent in dependents[folder]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        for folder in active:
            if folder not in load_order:
                print(f"[PluginLoader] Skipping '{folder}': circular dependency detected")

        # Phase 4: load in dependency order.
        for folder in load_order:
            entry = active[folder]["dir"]
            loaded_something = False

            mount_plugin_whls(entry)

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
        from sourcegraph.sys.node.base import BaseNode

        for py_file in sorted(nodes_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = f"plugin_{plugin_name}_{py_file.stem}"
            module = load_plugin_module(py_file, module_name)
            if module is None:
                continue

            for _name, obj in inspect.getmembers(module, inspect.isclass):
                if (issubclass(obj, BaseNode)
                        and obj is not BaseNode
                        and obj.__module__ == module_name
                        and obj.__name__ not in self._registry.node_map()):
                    self._registry.register(obj, source=f"plugin:{plugin_name}")

    def _load_plugin_types(self, types_dir: Path, plugin_name: str) -> None:
        for py_file in sorted(types_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = f"plugin_{plugin_name}_{py_file.stem}_types"
            # Registration is a side effect of exec - no class scanning needed.
            load_plugin_module(py_file, module_name)

    def _load_plugin_panels(self, panels_dir: Path, plugin_name: str) -> None:
        from sourcegraph.gui.panels.base_panel import BasePanel
        from sourcegraph.sys.registry.panels import register_panel

        for py_file in sorted(panels_dir.glob("*.py")):
            if py_file.name.startswith("_"):
                continue
            module_name = f"plugin_{plugin_name}_{py_file.stem}_panel"
            module = load_plugin_module(py_file, module_name)
            if module is None:
                continue

            for _name, obj in inspect.getmembers(module, inspect.isclass):
                if (issubclass(obj, BasePanel)
                        and obj is not BasePanel
                        and obj.__module__ == module_name):
                    register_panel(obj)
