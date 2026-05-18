from __future__ import annotations

import os
import importlib
import inspect
from typing import TYPE_CHECKING, Callable

from core.node.base import BaseNode

if TYPE_CHECKING:
    pass

# ComfyUI-style mappings
NODE_CLASS_MAPPINGS: dict[str, type[BaseNode]] = {}
NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {}

# Category organization (folder-based)
NODE_CATEGORIES: dict[str, list[type[BaseNode]]] = {}

# Custom registration callbacks
_registration_hooks: list[Callable[[type[BaseNode]], None]] = []

# Path to nodes directory, set by discover_nodes()
_nodes_dir: str = ""


def register_node(node_class: type[BaseNode]) -> type[BaseNode]:
    """Register a node class manually. Can be used as a decorator or called directly."""
    global NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

    class_name = node_class.__name__

    if node_class.title is None or node_class.title == class_name:
        name = class_name
        if name.endswith("Node"):
            name = name[:-4]
        result = []
        for i, char in enumerate(name):
            if i > 0 and char.isupper():
                result.append(" ")
            result.append(char)
        node_class.title = "".join(result)

    NODE_CLASS_MAPPINGS[class_name] = node_class
    NODE_DISPLAY_NAME_MAPPINGS[class_name] = node_class.title or class_name

    category = getattr(node_class, 'CATEGORY').upper()
    if category not in NODE_CATEGORIES:
        NODE_CATEGORIES[category] = []
    if node_class not in NODE_CATEGORIES[category]:
        NODE_CATEGORIES[category].append(node_class)

    for hook in _registration_hooks:
        hook(node_class)

    return node_class


def unregister_node(node_class: type[BaseNode] | str) -> None:
    """Remove a node from the registry."""
    global NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

    class_name = node_class if isinstance(node_class, str) else node_class.__name__

    NODE_CLASS_MAPPINGS.pop(class_name, None)
    NODE_DISPLAY_NAME_MAPPINGS.pop(class_name, None)

    for category in NODE_CATEGORIES.values():
        category[:] = [n for n in category
                       if (isinstance(node_class, str) and n.__name__ != node_class)
                       or (not isinstance(node_class, str) and n != node_class)]


def get_node_class(class_name: str) -> type[BaseNode] | None:
    """Get a node class by name."""
    return NODE_CLASS_MAPPINGS.get(class_name)


def get_node_title(class_name: str) -> str:
    """Get the display title for a node class."""
    return NODE_DISPLAY_NAME_MAPPINGS.get(class_name, class_name)


def add_registration_hook(callback: Callable[[type[BaseNode]], None]) -> None:
    """Add a callback to be called whenever a node is registered."""
    _registration_hooks.append(callback)


def remove_registration_hook(callback: Callable[[type[BaseNode]], None]) -> None:
    """Remove a registration callback."""
    if callback in _registration_hooks:
        _registration_hooks.remove(callback)


def discover_nodes(nodes_dir: str = "") -> None:
    """Scan subdirectories in nodes_dir and register all BaseNode subclasses found."""
    global NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, NODE_CATEGORIES, _nodes_dir

    if nodes_dir:
        _nodes_dir = nodes_dir

    if not _nodes_dir:
        print("[Node Registration] No nodes directory path set, skipping discovery")
        return

    NODE_CATEGORIES.clear()

    for entry in os.scandir(_nodes_dir):
        if entry.is_dir() and not entry.name.startswith("__"):
            for file in os.scandir(entry.path):
                if file.name.endswith(".py") and not file.name.startswith("__"):
                    module_name = f"nodes.{entry.name}.{file.name[:-3]}"
                    try:
                        module = importlib.import_module(module_name)

                        for name, obj in inspect.getmembers(module):
                            if (inspect.isclass(obj) and
                                    issubclass(obj, BaseNode) and
                                    obj is not BaseNode and
                                    obj.__module__ == module.__name__ and
                                    obj.__name__ not in NODE_CLASS_MAPPINGS):

                                if not hasattr(obj, 'CATEGORY'):
                                    obj.CATEGORY = entry.name.title()
                                register_node(obj)

                    except Exception as e:
                        print(f"[Node Registration] Failed to load module {module_name}: {e}")


def reload_nodes() -> None:
    """Reload all nodes. Useful for development."""
    global NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, NODE_CATEGORIES

    if not _nodes_dir:
        print("[Node Registration] No nodes directory path set, cannot reload")
        return

    manual_nodes = dict(NODE_CLASS_MAPPINGS)

    NODE_CLASS_MAPPINGS.clear()
    NODE_DISPLAY_NAME_MAPPINGS.clear()
    NODE_CATEGORIES.clear()

    for node_class in manual_nodes.values():
        register_node(node_class)

    discover_nodes()


class NodeRegistry:
    """Thin wrapper around NODE_CLASS_MAPPINGS for plugin and registry access.

    Uses the existing core.registry dicts as backing storage so all
    existing code that reads NODE_CLASS_MAPPINGS continues to work unmodified.
    """

    def __init__(self, backing: dict[str, type[BaseNode]] | None = None) -> None:
        if backing is None:
            backing = NODE_CLASS_MAPPINGS
        self._classes = backing
        self._sources: dict[str, str] = {}

    def register(self, node_class: type[BaseNode], source: str = "core") -> type[BaseNode]:
        """Register a node class, mirroring into registry dicts."""
        if not hasattr(node_class, "CATEGORY"):
            node_class.CATEGORY = source.split(":")[-1].title()
        register_node(node_class)
        self._sources[node_class.__name__] = source
        return node_class

    def get_source(self, name: str) -> str | None:
        return self._sources.get(name)

    def get(self, name: str) -> type[BaseNode] | None:
        return self._classes.get(name)

    def node_map(self) -> dict[str, type[BaseNode]]:
        """Return the full class map (same object as NODE_CLASS_MAPPINGS)."""
        return self._classes

    def __contains__(self, name: str) -> bool:
        return name in self._classes

    def __len__(self) -> int:
        return len(self._classes)


_default_registry: NodeRegistry | None = None


def get_default_registry() -> NodeRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = NodeRegistry()
    return _default_registry
