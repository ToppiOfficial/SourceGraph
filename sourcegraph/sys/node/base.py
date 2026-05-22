from __future__ import annotations
import os
import uuid
import json
import copy
from typing import Any, TYPE_CHECKING

from sourcegraph.sys.node.port import (
    Port, PortSpec, In, OptIn, DynIn, Out,
    _PortEntry, _collect_port_specs,
    port_uses_graph_variables, parse_type,
)
from sourcegraph.sys.node.dynamic import sync_dynamic_ports, copy_port_attributes

if TYPE_CHECKING:
    from sourcegraph.sys.graph.graph import Graph


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
            p.default = p.value

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
        from sourcegraph.sys.registry.enum_providers import get_enum_provider
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
        """Recompute dynamic-port slot count and add/remove ports as needed. Returns True if changed."""
        return sync_dynamic_ports(self, allow_value_extra_slot)

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
                        p.is_dynamic = True
                        copy_port_attributes(port, p)
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

    # GUI self-registration
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
    from sourcegraph.sys.registry.port_types import get_port_type_spec
    spec = get_port_type_spec(port.port_type)
    try:
        port.value = spec.coerce_text(text) if spec and spec.coerce_text else text
    except (ValueError, TypeError):
        port.value = text
