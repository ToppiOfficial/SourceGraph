from __future__ import annotations
import os
import uuid
import json
import copy
from typing import Any, TYPE_CHECKING
from dataclasses import dataclass
from enum import Enum

if TYPE_CHECKING:
    from .graph import Graph


class PortType(str, Enum):
    ANY        = "any"
    STRING     = "string"
    INT        = "int"
    FLOAT      = "float"
    FILE       = "file"
    BOOL       = "bool"
    ENUM       = "enum"
    QC_COMMAND = "qc_command"
    DICT       = "dict"
    ARRAY      = "array"
    SIGNAL     = "signal"


PORT_COLORS: dict[PortType, str] = {
    PortType.ANY:        "#aaaaaa",
    PortType.STRING:     "#4ec9b0",
    PortType.INT:        "#569cd6",
    PortType.FLOAT:      "#9cdcfe",
    PortType.FILE:       "#ce9178",
    PortType.BOOL:       "#ff8c00",
    PortType.ENUM:       "#b4629d",
    PortType.QC_COMMAND: "#dcdcaa",
    PortType.DICT:       "#ef8ed8",
    PortType.ARRAY:      "#bd93f9",
    PortType.SIGNAL:     "#f1fa8c",
}


@dataclass
class Port:
    name:      str
    is_input:  bool
    port_type: PortType = PortType.ANY
    node_id:   str      = ""
    value:     Any      = None
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

    def can_connect_to(self, other: Port) -> bool:
        if self.is_input == other.is_input:
            return False
        if not self.allow_connection or not other.allow_connection:
            return False
        if self.port_type == PortType.ANY or other.port_type == PortType.ANY:
            return True
        return self.port_type == other.port_type


def port_uses_graph_variables(port: Port) -> bool:
    return port.graph_enum == "variables" or (
        port.graph_enum is None and port.name == "var_name"
    )


TYPE_MAP: dict[str, PortType] = {
    "*": PortType.ANY,
    "any": PortType.ANY,
    "string": PortType.STRING,
    "str": PortType.STRING,
    "int": PortType.INT,
    "float": PortType.FLOAT,
    "number": PortType.FLOAT,
    "file": PortType.FILE,
    "path": PortType.FILE,
    "bool": PortType.BOOL,
    "boolean": PortType.BOOL,
    "enum": PortType.ENUM,
    "command": PortType.QC_COMMAND,
    "qc_command": PortType.QC_COMMAND,
    "dict": PortType.DICT,
    "object": PortType.DICT,
    "array": PortType.ARRAY,
    "list": PortType.ARRAY,
    "signal": PortType.SIGNAL,
    "flow": PortType.SIGNAL,
}


def parse_type(type_str: str) -> PortType:
    return TYPE_MAP.get(type_str.lower(), PortType.ANY)


# ---------------------------------------------------------------------------
# PortSpec declarations — the only way to define ports on a node
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

    def __init__(self, type_str: str = "*", *, prefix: str | None = None, **kwargs: Any) -> None:
        super().__init__(type_str, **kwargs)
        self._cfg["dynamic"] = True
        self._prefix: str | None = prefix


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

        if port_type == PortType.BOOL and default is None:
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

        if enum_options is not None:
            p.enum_options = [str(opt) for opt in enum_options]
        if enum_filter is not None:
            p.enum_filter = enum_filter
        if graph_enum is not None:
            p.graph_enum = graph_enum

        if port_type == PortType.BOOL and enum_options is None:
            p.enum_options = ["True", "False"]
            if isinstance(default, bool):
                p.value = "True" if default else "False"

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
        if not self.graph:
            return
        for port in self.inputs.values():
            if port.port_type != PortType.ENUM or port.enum_options is not None:
                continue
            if port_uses_graph_variables(port):
                self._reconcile_variables_enum(port)
            else:
                self._reconcile_assets_enum(port)

    def _reconcile_variables_enum(self, port: Port) -> None:
        vars_dict = getattr(self.graph, "variables", None) or {}
        if not vars_dict:
            return
        pv = "" if port.value is None else str(port.value)
        if not pv or pv in vars_dict:
            return
        if len(vars_dict) == 1:
            port.value = next(iter(vars_dict))
        else:
            port.value = ""

    def _reconcile_assets_enum(self, port: Port) -> None:
        assets = getattr(self.graph, "assets", None) or []
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

    def sync_dynamic_ports(self) -> bool:
        if not self.graph:
            return False

        changed = False

        groups: dict[tuple[str, bool], PortType] = {}
        for p in self.inputs.values():
            if p.is_dynamic:
                groups[(p.name.rstrip("0123456789"), True)] = p.port_type
        for p in self.outputs.values():
            if p.is_dynamic:
                groups[(p.name.rstrip("0123456789"), False)] = p.port_type

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

            sorted_indices = sorted(connected_ports.keys())

            renumber_map = {}
            new_idx = 1
            for old_idx in sorted_indices:
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

            target_count = max(1, max_conn_idx + 1)
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
                    port_dict[name] = p
                    changed = True

            ports_to_remove = [
                name for name in port_dict
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
            val = copy.deepcopy(v.value)
            if v.port_type == PortType.FILE and val and self.graph and self.graph.file_path:
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
                        node.inputs[name] = p
                        break

        for name, val in values.items():
            if name in node.inputs:
                port = node.inputs[name]
                if port.port_type == PortType.BOOL and isinstance(val, bool):
                    val = "True" if val else "False"
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