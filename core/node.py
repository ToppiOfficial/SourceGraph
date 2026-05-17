from __future__ import annotations
import os
import uuid
import json
import copy
from typing import Any, TYPE_CHECKING
from dataclasses import dataclass

if TYPE_CHECKING:
    from .graph import Graph

_SENTINEL = object()  # used as default sentinel in Port.set_value


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
            from core.events import NodePropertyChangedEvent
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
    from core.port_type_registry import resolve_alias
    return resolve_alias(type_str.lower())


# ---------------------------------------------------------------------------
# PortSpec declarations - the only way to define ports on a node
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
# Stored per-port spec used internally after class creation
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

    # Merge with parent entries (parent entries first, child entries override by name)
    parent_entries: list[_PortEntry] = getattr(cls, '_port_entries', [])
    merged: dict[str, _PortEntry] = {e.name: e for e in parent_entries}
    for e in entries:
        merged[e.name] = e

    cls._port_entries = list(merged.values())


class BaseNode:
    title: str | None = None
    description: str = ""
    category: str = "General"
    color: str = "#2d4a7a"
    body_color: str | None = None
    locked_title: bool = False
    allow_folding: bool = True
    default_width: int | None = None

    dynamic_input_prefix: str | None = None
    dynamic_output_prefix: str | None = None

    _port_entries: list[_PortEntry] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if 'title' not in cls.__dict__:
            name = cls.__name__
            if name.endswith("Node"):
                name = name[:-4]
            cls.title = name.lower()

        _collect_port_specs(cls)

    def __init__(self) -> None:
        self.id: str = str(uuid.uuid4())
        self.graph: Graph | None = None
        self.x: float = 0.0
        self.y: float = 0.0
        self.width: float | None = None
        self.height: float | None = None
        self.label_width: float | None = None
        self.custom_name: str | None = None
        self.inputs: dict[str, Port] = {}
        self.outputs: dict[str, Port] = {}

        self.last_execution_time: float | None = None
        self._gui_builders: dict[str, callable] = {}
        self._gui_builders_registered = False

        self._build_ports()
        self._register_gui_builders()

        self.error_msg: str | None = None
        self.folded: bool = False
        self.title = getattr(self.__class__, 'title', self.__class__.__name__.lower())

    @property
    def display_name(self) -> str:
        if self.custom_name and self.custom_name.strip():
            return self.custom_name.strip()
        if self.title and self.title.strip():
            return self.title.strip()
        name = self.__class__.__name__
        if name.endswith("Node"):
            name = name[:-4]
        return name.lower()

    def _build_ports(self) -> None:
        for entry in self.__class__._port_entries:
            if entry.is_input:
                self._add_input_from_entry(entry)
            else:
                self._add_output_from_entry(entry)

    def _add_input_from_entry(self, entry: _PortEntry) -> Port:
        port_type = parse_type(entry.type_str)
        cfg = entry.cfg

        default          = cfg.get("default")
        editable         = cfg.get("editable", True)
        display_in_insp  = cfg.get("display_in_inspector", True)
        enum_options     = cfg.get("enum_options")
        enum_filter      = cfg.get("enum_filter")
        graph_enum       = cfg.get("graph_enum")
        label            = cfg.get("label", "")
        allow_connection = cfg.get("allow_connection", True)
        full_row         = cfg.get("full_row", False)
        below_ports      = cfg.get("below_ports", False)
        row_height       = cfg.get("row_height")
        row_stretch      = cfg.get("row_stretch", False)
        number_increment = cfg.get("step")

        if port_type == "bool" and default is None:
            default = False

        name = entry.name
        if entry.is_dynamic:
            prefix = entry.dyn_prefix or entry.name
            name = f"{prefix}1"
            self.dynamic_input_prefix = prefix

        p = Port(
            name=name,
            is_input=True,
            port_type=port_type,
            node_id=self.id,
            value=default,
        )
        p.default              = default
        p.editable             = editable
        p.display_in_inspector = display_in_insp
        p.required             = entry.required
        p.label                = label
        p.is_dynamic           = entry.is_dynamic
        p.allow_connection     = allow_connection
        p.full_row             = full_row
        p.below_ports          = below_ports
        p.row_height           = row_height
        p.row_stretch          = row_stretch
        p.number_increment     = number_increment
        p.linked_prefix        = cfg.get("linked_prefix")

        if enum_options is not None:
            p.enum_options = [str(opt) for opt in enum_options]
        if enum_filter is not None:
            p.enum_filter = enum_filter
        if graph_enum is not None:
            p.graph_enum = graph_enum

        if port_type == "bool" and enum_options is None:
            p.enum_options = ["True", "False"]
            if isinstance(default, bool):
                p.value = "True" if default else "False"
            p.default = p.value  # sync default to the string form stored at runtime

        self.inputs[name] = p
        return p

    def _add_output_from_entry(self, entry: _PortEntry) -> Port:
        p = Port(
            name=entry.name,
            is_input=False,
            port_type=parse_type(entry.type_str),
            node_id=self.id,
        )
        self.outputs[entry.name] = p
        return p

    def validate(self) -> str | None:
        self.error_msg = None
        if not self.graph:
            return None

        missing = []
        for pname, port in self.inputs.items():
            if port.required:
                if not self.graph.get_input_connection(self.id, pname):
                    val = port.value
                    if val is None or (isinstance(val, str) and not val.strip()):
                        missing.append(port.label or pname)

        if missing:
            self.error_msg = f"Required inputs missing: {', '.join(missing)}"
            return f"[{self.title}] {self.error_msg}"
        return None

    def execute(self, **kwargs) -> tuple | dict:
        return ()

    def _tuple_to_dict(self, result: tuple) -> dict[str, Any]:
        names = list(self.outputs.keys())
        return {names[i]: val for i, val in enumerate(result) if i < len(names)}

    def on_property_changed(self) -> None:
        pass

    def sync_presentation(self) -> None:
        pass

    def reconcile_graph_bound_inputs(self) -> None:
        from core.enum_providers import get_enum_provider
        if not self.graph:
            return
        for port in self.inputs.values():
            if port.port_type != "enum" or port.enum_options is not None:
                continue
            key = port.graph_enum
            if key is None:
                if port.name == "var_name":
                    key = "variables"
                else:
                    continue
            provider = get_enum_provider(key)
            if provider:
                provider.resolve(self.graph, port)

    def fail(self, msg: str) -> None:
        self.error_msg = msg
        raise RuntimeError(msg)

    def collect_dynamic(self, prefix: str, kwargs: dict) -> list:
        n = len(prefix)
        pairs = [
            (int(k[n:]), v)
            for k, v in kwargs.items()
            if k.startswith(prefix) and k[n:].isdigit() and v is not None
        ]
        return [v for _, v in sorted(pairs)]

    def resolve_path(self, path: str) -> str:
        if not path:
            return ""
        norm_path = os.path.normpath(str(path)).replace("\\", "/")
        base_dir = self._graph_base_dir()
        if base_dir:
            if os.path.isabs(norm_path):
                return norm_path
            return os.path.normpath(os.path.join(base_dir, norm_path)).replace("\\", "/")
        return norm_path

    def _graph_base_dir(self) -> str | None:
        if not self.graph:
            return None
        if self.graph.file_path:
            return str(self.graph.file_path.parent)
        return getattr(self.graph, "output_dir", None) or getattr(self.graph, "project_dir", None)

    def _try_make_relative(self, abs_path: str, base_dir: str) -> str:
        try:
            rel = os.path.relpath(abs_path, base_dir).replace("\\", "/")
            if not os.path.isabs(rel):
                return rel
        except ValueError:
            pass
        return abs_path.replace("\\", "/")

    def validate_file_input(self, path: str, must_exist: bool = True, absolute_path: bool = False) -> str:
        resolved = self.resolve_path(path)
        if not resolved:
            self.fail("File path is empty.")
        if must_exist and not os.path.exists(resolved):
            self.fail(f"File not found: {resolved}")
        if absolute_path:
            return resolved
        base_dir = self._graph_base_dir()
        if base_dir:
            return self._try_make_relative(resolved, base_dir)
        return resolved

    def get_dict_value(self, inputs: dict[str, Any], port_name: str, key: str, default: Any = None) -> Any:
        data = inputs.get(port_name)
        if isinstance(data, dict):
            return data.get(key, default)
        if isinstance(data, str) and data.strip().startswith("{"):
            try:
                return json.loads(data).get(key, default)
            except Exception:
                pass
        return default

    def sync_dynamic_ports(self, allow_value_extra_slot: bool = False) -> bool:
        if not self.graph:
            return False

        changed = False

        groups: dict[tuple[str, bool], str] = {}
        for p in self.inputs.values():
            if p.is_dynamic:
                groups[(p.name.rstrip("0123456789"), True)] = p.port_type
        for p in self.outputs.values():
            if p.is_dynamic:
                groups[(p.name.rstrip("0123456789"), False)] = p.port_type

        # Compute raw target_count per prefix 
        target_counts: dict[tuple[str, bool], int] = {}

        for (prefix, is_input), ptype in groups.items():
            connected_ports = {}
            for c in self.graph.connections:
                if is_input:
                    if c.dst_node == self.id and c.dst_port.startswith(prefix):
                        suffix = c.dst_port[len(prefix):]
                        if suffix.isdigit():
                            connected_ports[int(suffix)] = c.dst_port
                else:
                    if c.src_node == self.id and c.src_port.startswith(prefix):
                        suffix = c.src_port[len(prefix):]
                        if suffix.isdigit():
                            connected_ports[int(suffix)] = c.src_port

            port_dict = self.inputs if is_input else self.outputs

            #  Value compaction: pack non-default/non-empty values forward 
            # Runs BEFORE renumber_map so compacted values are visible to
            # _val_occupied, letting renumber_map skip over them correctly.
            # Only unconnected ports are touched; connected ports keep position.
            if is_input:
                connected_port_names = set(connected_ports.values())
                unconnected = sorted(
                    (int(n[len(prefix):]), n)
                    for n in port_dict
                    if n.startswith(prefix) and n[len(prefix):].isdigit()
                    and n not in connected_port_names
                )
                if unconnected:
                    default_val = port_dict[unconnected[0][1]].default

                    def _occupied(v: Any, _dflt=default_val) -> bool:
                        if v is None:
                            return False
                        if isinstance(v, str) and not str(v).strip():
                            return False
                        return v != _dflt

                    vals = [port_dict[n].value for _, n in unconnected]
                    packed = [v for v in vals if _occupied(v)] + [v for v in vals if not _occupied(v)]
                    for (_, name), old_v, new_v in zip(unconnected, vals, packed):
                        if old_v != new_v:
                            port_dict[name].value = new_v
                            changed = True

            sorted_indices = sorted(connected_ports.keys())

            def _val_occupied(idx: int) -> bool:
                if idx in connected_ports:
                    return False
                p = port_dict.get(f"{prefix}{idx}")
                if p is None or p.value is None:
                    return False
                if isinstance(p.value, str) and not str(p.value).strip():
                    return False
                return p.value != p.default

            renumber_map = {}
            new_idx = 1
            for old_idx in sorted_indices:
                while _val_occupied(new_idx):
                    new_idx += 1
                if old_idx != new_idx:
                    renumber_map[old_idx] = new_idx
                    changed = True
                new_idx += 1

            if renumber_map:
                new_connections = []
                for c in self.graph.connections:
                    if is_input:
                        if c.dst_node == self.id and c.dst_port.startswith(prefix):
                            suffix = c.dst_port[len(prefix):]
                            if suffix.isdigit():
                                old_idx = int(suffix)
                                if old_idx in renumber_map:
                                    new_port = f"{prefix}{renumber_map[old_idx]}"
                                    new_connections.append(
                                        type(c)(c.src_node, c.src_port, c.dst_node, new_port)
                                    )
                                    continue
                    else:
                        if c.src_node == self.id and c.src_port.startswith(prefix):
                            suffix = c.src_port[len(prefix):]
                            if suffix.isdigit():
                                old_idx = int(suffix)
                                if old_idx in renumber_map:
                                    new_port = f"{prefix}{renumber_map[old_idx]}"
                                    new_connections.append(
                                        type(c)(c.src_node, new_port, c.dst_node, c.dst_port)
                                    )
                                    continue
                    new_connections.append(c)
                self.graph.connections = new_connections

            max_conn_idx = 0
            for c in self.graph.connections:
                if is_input:
                    if c.dst_node == self.id and c.dst_port.startswith(prefix):
                        suffix = c.dst_port[len(prefix):]
                        if suffix.isdigit():
                            max_conn_idx = max(max_conn_idx, int(suffix))
                else:
                    if c.src_node == self.id and c.src_port.startswith(prefix):
                        suffix = c.src_port[len(prefix):]
                        if suffix.isdigit():
                            max_conn_idx = max(max_conn_idx, int(suffix))

            max_val_idx = 0
            if is_input:
                for p in port_dict.values():
                    if (p.is_dynamic and p.name.startswith(prefix)
                            and p.name[len(prefix):].isdigit()
                            and p.value != p.default
                            and str(p.value if p.value is not None else "").strip() != ""):
                        max_val_idx = max(max_val_idx, int(p.name[len(prefix):]))

            if allow_value_extra_slot:
                # Create one empty slot after the last used (conn or value) port
                target_count = max(1, max(max_conn_idx, max_val_idx) + 1)
            else:
                # Keep non-default-value ports alive but don't add an extra empty slot
                target_count = max(1, max_conn_idx + 1, max_val_idx)

            target_counts[(prefix, is_input)] = target_count

        #  Honour linked_prefix grouping 
        for (prefix, is_input) in list(target_counts):
            if not is_input:
                continue
            port_dict = self.inputs
            tmpl = next(
                (p for p in port_dict.values()
                 if p.is_dynamic and p.name.startswith(prefix)
                 and p.name[len(prefix):].isdigit() and p.linked_prefix),
                None,
            )
            if tmpl and tmpl.linked_prefix:
                src_key = (tmpl.linked_prefix, True)
                if src_key in target_counts:
                    target_counts[(prefix, is_input)] = max(
                        target_counts[(prefix, is_input)],
                        target_counts[src_key],
                    )

        #  create / remove ports 
        for (prefix, is_input), ptype in groups.items():
            target_count = target_counts[(prefix, is_input)]
            port_dict = self.inputs if is_input else self.outputs

            template_port = next(
                (p for p in port_dict.values() if p.is_dynamic and p.name.startswith(prefix)),
                None,
            )

            for i in range(1, target_count + 1):
                name = f"{prefix}{i}"
                if name not in port_dict:
                    p = Port(name=name, is_input=is_input, port_type=ptype, node_id=self.id)
                    p.is_dynamic = True
                    p.allow_connection = True
                    if template_port:
                        p.editable             = template_port.editable
                        p.display_in_inspector = template_port.display_in_inspector
                        p.allow_connection     = template_port.allow_connection
                        p.label                = template_port.label
                        p.default              = template_port.default
                        p.value                = template_port.default
                        p.linked_prefix        = template_port.linked_prefix

                    # Insert after the last sibling of the same prefix to keep order
                    all_keys = list(port_dict.keys())
                    last_pos = max(
                        (j for j, k in enumerate(all_keys)
                         if k.startswith(prefix) and k[len(prefix):].isdigit()),
                        default=-1,
                    )
                    if last_pos >= 0:
                        insert_after = all_keys[last_pos]
                        new_dict: dict = {}
                        for k in all_keys:
                            new_dict[k] = port_dict[k]
                            if k == insert_after:
                                new_dict[name] = p
                        port_dict.clear()
                        port_dict.update(new_dict)
                    else:
                        port_dict[name] = p

                    changed = True

            ports_to_remove = [
                name for name in list(port_dict)
                if name.startswith(prefix)
                and name[len(prefix):].isdigit()
                and int(name[len(prefix):]) > target_count
            ]
            for name in ports_to_remove:
                del port_dict[name]
                changed = True

        return changed

    def get_reads(self) -> set[str]:
        return set()

    def get_writes(self) -> set[str]:
        p = self.inputs.get("var_name")
        if p and p.value and "value" in self.inputs:
            return {f"var:{p.value}"}
        return set()

    def to_dict(self) -> dict:
        values = {}
        for k, v in self.inputs.items():
            if v.value == v.default:
                continue
            val = copy.deepcopy(v.value)
            if v.port_type == "file" and val and self.graph and self.graph.file_path:
                try:
                    abs_val = os.path.abspath(self.resolve_path(val))
                    base_dir = self.graph.file_path.parent
                    val = self._try_make_relative(str(abs_val), str(base_dir))
                except (ValueError, TypeError):
                    pass
            values[k] = val

        return {
            "id": self.id,
            "type": self.__class__.__name__,
            "title": self.title,
            "custom_name": self.custom_name,
            "x": self.x,
            "y": self.y,
            "width": getattr(self, 'width', None),
            "height": getattr(self, 'height', None),
            "label_width": getattr(self, 'label_width', None),
            "folded": self.folded,
            "values": values,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BaseNode:
        node = cls()
        node.id = data["id"]
        node.x = data.get("x", 0.0)
        node.y = data.get("y", 0.0)
        node.width = data.get("width")
        node.height = data.get("height")
        node.label_width = data.get("label_width")
        node.folded = data.get("folded", False)
        node.title = cls.title
        node.custom_name = data.get("custom_name")

        values = data.get("values", {})

        # Restore dynamic ports that were saved but don't yet exist on the node
        for name in list(values.keys()):
            if name not in node.inputs:
                for port in node.inputs.values():
                    if not port.is_dynamic:
                        continue
                    prefix = port.name.rstrip("0123456789")
                    if name.startswith(prefix) and name[len(prefix):].isdigit():
                        p = Port(name=name, is_input=True, port_type=port.port_type, node_id=node.id)
                        p.is_dynamic           = True
                        p.editable             = port.editable
                        p.display_in_inspector = port.display_in_inspector
                        p.allow_connection     = port.allow_connection
                        p.full_row             = port.full_row
                        p.below_ports          = port.below_ports
                        p.label                = port.label
                        p.row_height           = port.row_height
                        p.row_stretch          = port.row_stretch
                        p.enum_options         = port.enum_options
                        p.enum_filter          = port.enum_filter
                        p.graph_enum           = port.graph_enum
                        p.default              = port.default
                        p.linked_prefix        = port.linked_prefix
                        node.inputs[name] = p
                        break

        for name, val in values.items():
            if name in node.inputs:
                port = node.inputs[name]
                if port.port_type == "bool" and isinstance(val, bool):
                    val = "True" if val else "False"
                if val is None and port.is_dynamic and port.default is not None:
                    val = port.default
                port.value = val

        for p in (*node.inputs.values(), *node.outputs.values()):
            p.node_id = node.id

        node._gui_builders_registered = False
        node._register_gui_builders()

        if hasattr(node, 'on_property_changed'):
            node.on_property_changed()
        return node

    # GUI Self-Registration System
    def _register_gui_builders(self) -> None:
        self._gui_builders_registered = True

    def register_gui_builder(self, port_name: str, builder_func: callable) -> None:
        self._gui_builders[port_name] = builder_func

    def get_gui_builder(self, port_name: str) -> callable | None:
        return self._gui_builders.get(port_name)

    def has_gui_builder(self, port_name: str) -> bool:
        return port_name in self._gui_builders

    def create_widget_for_port(self, port):
        builder = self.get_gui_builder(port.name)
        if builder:
            return builder(port)
        return None


def _coerce(port, text: str) -> None:
    """Write a validated string value back into a port, coercing to the port's native type."""
    from core.port_type_registry import get_port_type_spec
    spec = get_port_type_spec(port.port_type)
    try:
        port.value = spec.coerce_text(text) if spec and spec.coerce_text else text
    except (ValueError, TypeError):
        port.value = text