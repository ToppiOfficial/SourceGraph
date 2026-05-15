from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.node import BaseNode


class NodeRegistry:
    """Thin wrapper around NODE_CLASS_MAPPINGS for plugin and registry access.

    Uses the existing nodes/__init__.py dicts as backing storage so all
    existing code that reads NODE_CLASS_MAPPINGS continues to work unmodified.
    """

    def __init__(self, backing: "dict[str, type[BaseNode]] | None" = None) -> None:
        if backing is None:
            from nodes import NODE_CLASS_MAPPINGS
            backing = NODE_CLASS_MAPPINGS
        self._classes = backing
        self._sources: dict[str, str] = {}

    def register(self, node_class: "type[BaseNode]", source: str = "core") -> "type[BaseNode]":
        """Register a node class, mirroring into nodes/__init__.py mappings."""
        from nodes import register_node
        if not hasattr(node_class, "CATEGORY"):
            node_class.CATEGORY = source.split(":")[-1].title()
        register_node(node_class)
        self._sources[node_class.__name__] = source
        return node_class

    def get_source(self, name: str) -> "str | None":
        return self._sources.get(name)

    def get(self, name: str) -> "type[BaseNode] | None":
        return self._classes.get(name)

    def node_map(self) -> "dict[str, type[BaseNode]]":
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
