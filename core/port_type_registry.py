from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PortTypeSpec:
    key: str
    color: str = "#aaaaaa"
    editable: bool = False
    inspector_editable: bool | None = None  # None → inherit from editable
    canvas_widget_factory: Any = None       # (port, parent) -> QWidget | None
    inspector_widget_factory: Any = None    # (port) -> QWidget | None
    aliases: list[str] = field(default_factory=list)


_registry: dict[str, PortTypeSpec] = {}
_alias_map: dict[str, str] = {}  # alias/key → canonical key


def register_port_type(spec: PortTypeSpec) -> None:
    """Register a port type. Silent skip if key already registered (first wins)."""
    if spec.key in _registry:
        return
    _registry[spec.key] = spec
    _alias_map[spec.key] = spec.key
    for alias in spec.aliases:
        if alias not in _alias_map:
            _alias_map[alias] = spec.key


def get_port_type_spec(key) -> PortTypeSpec | None:
    k = key.value if hasattr(key, 'value') else str(key)
    canonical = _alias_map.get(k)
    return _registry.get(canonical) if canonical else None


def get_color(key: str, default: str = "#aaaaaa") -> str:
    spec = get_port_type_spec(key)
    return spec.color if spec else default


def is_editable(key: str) -> bool:
    spec = get_port_type_spec(key)
    return spec.editable if spec else False


def is_inspector_editable(key: str) -> bool:
    spec = get_port_type_spec(key)
    if spec is None:
        return False
    return spec.editable if spec.inspector_editable is None else spec.inspector_editable


def resolve_alias(key: str) -> str:
    """Return canonical key for *key*, or *key* itself if not registered."""
    return _alias_map.get(str(key).lower(), str(key).lower())


def get_all_specs() -> list[PortTypeSpec]:
    return list(_registry.values())
