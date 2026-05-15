from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.graph import Graph
    from core.node import Port


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


# ---------------------------------------------------------------------------
# Built-in providers
# ---------------------------------------------------------------------------

class VariablesEnumProvider(EnumProvider):
    def resolve(self, graph: "Graph", port: "Port") -> None:
        vars_dict = getattr(graph, "variables", None) or {}
        if not vars_dict:
            return
        pv = "" if port.value is None else str(port.value)
        if not pv or pv in vars_dict:
            return
        port.value = next(iter(vars_dict)) if len(vars_dict) == 1 else ""


class AssetsEnumProvider(EnumProvider):
    def resolve(self, graph: "Graph", port: "Port") -> None:
        assets = getattr(graph, "assets", None) or []
        if not assets:
            return
        ext_filter = port.enum_filter
        valid: list[str] = []
        for a in assets:
            if ext_filter and os.path.splitext(a)[1].lower() not in ext_filter:
                continue
            valid.append(os.path.normpath(str(a)).replace("\\", "/"))

        pv_raw = "" if port.value is None else str(port.value)
        if not pv_raw:
            return
        pv = os.path.normpath(pv_raw).replace("\\", "/")
        if pv in valid:
            port.value = pv
            return
        base = os.path.basename(pv)
        matches = [a for a in valid if os.path.basename(a) == base]
        if len(matches) == 1:
            port.value = matches[0]
        elif len(valid) == 1:
            port.value = valid[0]
        else:
            port.value = ""


register_enum_provider("variables", VariablesEnumProvider())
register_enum_provider("assets", AssetsEnumProvider())
