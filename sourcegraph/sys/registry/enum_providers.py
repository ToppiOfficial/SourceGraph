from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sourcegraph.sys.graph.graph import Graph
    from sourcegraph.sys.node.port import Port


class EnumProvider:
    """Protocol for graph-bound enum reconcilers.

    Implement `resolve(graph, port)` to validate and fix port.value in-place.
    Set port.value to '' when the current value has no valid match.
    """

    def resolve(self, graph: "Graph", port: "Port") -> None:
        raise NotImplementedError


_providers: dict[str, EnumProvider] = {}


def register_enum_provider(key: str, provider: EnumProvider) -> None:
    """Register a provider under *key*. Overwrites silently if already set."""
    _providers[key] = provider


def get_enum_provider(key: str) -> EnumProvider | None:
    return _providers.get(key)


class VariablesEnumProvider(EnumProvider):
    def resolve(self, graph: "Graph", port: "Port") -> None:
        vars_dict = getattr(graph, "variables", None) or {}
        if not vars_dict:
            return
        pv = "" if port.value is None else str(port.value)
        if not pv or pv in vars_dict:
            return
        port.value = next(iter(vars_dict)) if len(vars_dict) == 1 else ""


register_enum_provider("variables", VariablesEnumProvider())
