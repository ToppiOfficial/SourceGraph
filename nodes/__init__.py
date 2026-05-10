import os
import importlib
import inspect
from typing import Callable
from core.node import BaseNode

# ComfyUI-style mappings
NODE_CLASS_MAPPINGS: dict[str, type[BaseNode]] = {}
NODE_DISPLAY_NAME_MAPPINGS: dict[str, str] = {}

# Category organization (folder-based)
NODE_CATEGORIES: dict[str, list[type[BaseNode]]] = {}

# Custom registration callbacks
_registration_hooks: list[Callable[[type[BaseNode]], None]] = []


def register_node(node_class: type[BaseNode]) -> type[BaseNode]:
    """Register a node class manually. Can be used as decorator or called directly."""
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
    
    # Remove from categories
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
    """Add a callback to be called when a node is registered."""
    _registration_hooks.append(callback)


def remove_registration_hook(callback: Callable[[type[BaseNode]], None]) -> None:
    """Remove a registration callback."""
    if callback in _registration_hooks:
        _registration_hooks.remove(callback)


def _auto_discover_nodes():
    """Dynamically scan subdirectories in the 'nodes' folder."""
    global NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, NODE_CATEGORIES

    NODE_CATEGORIES.clear()

    base_path = os.path.dirname(__file__)

    for entry in os.scandir(base_path):
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


def reload_nodes():
    """Reload all nodes. Useful for development."""
    global NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS, NODE_CATEGORIES
    
    manual_nodes = dict(NODE_CLASS_MAPPINGS)
    
    NODE_CLASS_MAPPINGS.clear()
    NODE_DISPLAY_NAME_MAPPINGS.clear()
    NODE_CATEGORIES.clear()
    
    for node_class in manual_nodes.values():
        register_node(node_class)
    
    _auto_discover_nodes()


_auto_discover_nodes()

__all__ = [
    'NODE_CLASS_MAPPINGS',
    'NODE_DISPLAY_NAME_MAPPINGS', 
    'NODE_CATEGORIES',
    'register_node',
    'unregister_node',
    'get_node_class',
    'get_node_title',
    'reload_nodes',
]
