from __future__ import annotations
import copy
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.graph.graph import Graph


def backup_volatile_stores(graph: "Graph") -> dict[str, Any]:
    """Deep-copy all volatile ext_store entries before execution so they can be restored."""
    from core.graph.stores import get_volatile_store_specs
    backup: dict[str, Any] = {}
    for spec in get_volatile_store_specs():
        backup.update(spec.dump(graph))
    return copy.deepcopy(backup)


def restore_volatile_stores(graph: "Graph", backup: dict[str, Any]) -> None:
    """Write a previously backed-up volatile store snapshot back into the graph."""
    graph._state.ext_stores.update(backup)
