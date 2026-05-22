from __future__ import annotations
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from sourcegraph.sys.graph.graph import Graph

_SENTINEL = object()  # sentinel for Port.set_value old_value default


@dataclass
class Port:
    name:      str
    is_input:  bool
    port_type: str = "any"
    node_id:   str      = ""
    value:     Any      = None
    default:   Any      = None
    label:     str      = ""
    allow_connection: bool = True
    is_dynamic: bool = False
    display_in_inspector: bool = True
    editable: bool = True
    full_row: bool = False
    below_ports: bool = False
    row_height: int | None = None
    row_stretch: bool = False

    enum_options: list[str] | None = None
    enum_filter: list[str] | None = None
    required: bool = False
    graph_enum: str | None = None
    number_increment: float | None = None
    linked_prefix:   str | None = None

    def can_connect_to(self, other: Port) -> bool:
        if self.is_input == other.is_input:
            return False
        if not self.allow_connection or not other.allow_connection:
            return False
        if self.port_type == "any" or other.port_type == "any":
            return True
        return self.port_type == other.port_type

    def set_value(self, value: Any, bus=None, old_value: Any = _SENTINEL) -> None:
        """Set port value and optionally emit a NodePropertyChangedEvent."""
        if old_value is _SENTINEL:
            old_value = self.value
        self.value = value
        if bus is not None and old_value != value:
            from sourcegraph.sys.events import NodePropertyChangedEvent
            bus.emit(NodePropertyChangedEvent(
                node_id=self.node_id,
                port_name=self.name,
                old_value=old_value,
                new_value=value,
            ))


def port_uses_graph_variables(port: Port) -> bool:
    return port.graph_enum == "variables" or (
        port.graph_enum is None and port.name == "var_name"
    )


def parse_type(type_str: str) -> str:
    from sourcegraph.sys.registry.port_types import resolve_alias
    return resolve_alias(type_str.lower())


# ---------------------------------------------------------------------------
# PortSpec declarations - the only way to define ports on a node class body
# ---------------------------------------------------------------------------

class PortSpec:
    """Port declaration placed on BaseNode subclass bodies.

    Collected by _collect_port_specs() during class creation.
    Instances are removed from the class dict after collection.
    """
    _is_required: bool = True
    _is_input:    bool = True

    def __init__(
        self,
        type_str: str,
        default: Any = None,
        *,
        label: str = "",
        allow_connection: bool = True,
        editable: bool = True,
        display_in_inspector: bool = True,
        full_row: bool = False,
        below_ports: bool = False,
        row_height: int | None = None,
        row_stretch: bool = False,
        enum_options: list | None = None,
        enum_filter: list | None = None,
        graph_enum: str | None = None,
        step: float | None = None,
    ) -> None:
        self.type_str = type_str
        cfg: dict[str, Any] = {}
        if default is not None:          cfg["default"] = default
        if label:                        cfg["label"] = label
        if not allow_connection:         cfg["allow_connection"] = False
        if not editable:                 cfg["editable"] = False
        if not display_in_inspector:     cfg["display_in_inspector"] = False
        if full_row:                     cfg["full_row"] = True
        if below_ports:                  cfg["below_ports"] = True
        if row_height is not None:       cfg["row_height"] = row_height
        if row_stretch:                  cfg["row_stretch"] = True
        if enum_options is not None:     cfg["enum_options"] = enum_options
        if enum_filter is not None:      cfg["enum_filter"] = enum_filter
        if graph_enum is not None:       cfg["graph_enum"] = graph_enum
        if step is not None:             cfg["step"] = step
        self._cfg = cfg


class In(PortSpec):
    """Required input port declaration."""
    _is_required = True
    _is_input    = True


class OptIn(PortSpec):
    """Optional input port declaration."""
    _is_required = False
    _is_input    = True


class DynIn(PortSpec):
    """Dynamic (variable-count) optional input port."""
    _is_required = False
    _is_input    = True

    def __init__(self, type_str: str = "*", *, prefix: str | None = None, link: str | None = None, **kwargs: Any) -> None:
        super().__init__(type_str, **kwargs)
        self._cfg["dynamic"] = True
        self._prefix: str | None = prefix
        if link:
            self._cfg["linked_prefix"] = link


class Out(PortSpec):
    """Output port declaration."""
    _is_input = False

    def __init__(self, type_str: str) -> None:
        self.type_str = type_str
        self._cfg: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Internal per-port entry stored after class creation
# ---------------------------------------------------------------------------

@dataclass
class _PortEntry:
    name:       str
    type_str:   str
    cfg:        dict
    required:   bool
    is_input:   bool
    is_dynamic: bool = False
    dyn_prefix: str | None = None


def _collect_port_specs(cls: type) -> None:
    """Scan *cls* for PortSpec declarations and store parsed entries on the class.

    Markers are removed from the class dict after collection.
    """
    entries: list[_PortEntry] = []
    to_remove: list[str] = []

    for attr, val in list(cls.__dict__.items()):
        if not isinstance(val, PortSpec):
            continue
        to_remove.append(attr)

        if isinstance(val, Out):
            entries.append(_PortEntry(
                name=attr, type_str=val.type_str, cfg=val._cfg,
                required=False, is_input=False,
            ))
        elif isinstance(val, DynIn):
            prefix = val._prefix if val._prefix else attr
            entries.append(_PortEntry(
                name=attr, type_str=val.type_str, cfg=val._cfg,
                required=False, is_input=True,
                is_dynamic=True, dyn_prefix=prefix,
            ))
        else:
            entries.append(_PortEntry(
                name=attr, type_str=val.type_str, cfg=val._cfg,
                required=val._is_required, is_input=True,
            ))

    for name in to_remove:
        try:
            delattr(cls, name)
        except AttributeError:
            pass

    # Merge with parent entries (parent first, child overrides by name)
    parent_entries: list[_PortEntry] = getattr(cls, '_port_entries', [])
    merged: dict[str, _PortEntry] = {e.name: e for e in parent_entries}
    for e in entries:
        merged[e.name] = e

    cls._port_entries = list(merged.values())
