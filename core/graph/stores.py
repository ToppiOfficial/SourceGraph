from __future__ import annotations
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from core.graph.graph import Graph


class GraphStoreSpec:
    """Describes one named data collection that lives in graph.ext_stores.

    load(data) -> dict       - read from raw JSON, return {ext_key: value, ...}
    dump(graph) -> dict      - read from graph, return {json_key: value, ...}
    execution_volatile=True  - store is saved/restored around graph execution
    """
    def __init__(
        self,
        key: str,
        default: Callable[[], Any],
        load: Callable[[dict], dict[str, Any]],
        dump: Callable[["Graph"], dict[str, Any]],
        execution_volatile: bool = False,
    ) -> None:
        self.key = key
        self.default = default
        self._load = load
        self._dump = dump
        self.execution_volatile = execution_volatile

    def load(self, data: dict) -> dict[str, Any]:
        return self._load(data)

    def dump(self, graph: "Graph") -> dict[str, Any]:
        return self._dump(graph)


_specs: dict[str, GraphStoreSpec] = {}


def register_graph_store(spec: GraphStoreSpec) -> None:
    _specs[spec.key] = spec


def get_all_store_specs() -> list[GraphStoreSpec]:
    return list(_specs.values())


def get_volatile_store_specs() -> list[GraphStoreSpec]:
    """Return store specs whose data is saved and restored around each graph execution."""
    return [s for s in _specs.values() if s.execution_volatile]


# Built-in stores
register_graph_store(GraphStoreSpec(
    key="variables",
    default=dict,
    execution_volatile=True,
    load=lambda data: {
        "variables":       dict(data["variables"]) if isinstance(data.get("variables"), dict) else {},
        "variable_layout": data.get("variable_layout"),
    },
    dump=lambda g: {
        "variables":       g.variables,
        "variable_layout": g.variable_layout,
    },
))

register_graph_store(GraphStoreSpec(
    key="assets",
    default=list,
    load=lambda data: {
        "assets":       list(data["assets"]) if isinstance(data.get("assets"), list) else [],
        "asset_layout": data.get("asset_layout"),
    },
    dump=lambda g: {
        "assets":       g.get_ext_store("assets", []),
        "asset_layout": g.get_ext_store("asset_layout"),
    },
))
