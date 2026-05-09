from __future__ import annotations
import os
import uuid
import json
import copy
from typing import Any, TYPE_CHECKING
from dataclasses import dataclass, field
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
    visible:   bool     = True
    allow_connection: bool = True
    is_dynamic: bool = False
    display_in_inspector: bool = True
    editable: bool = True

    enum_options: list[str] | None = None
    enum_filter: list[str] | None = None
    required: bool = False
    graph_enum: str | None = None

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


def parse_type(type_spec: str | tuple) -> PortType:
    if isinstance(type_spec, PortType):
        return type_spec
    
    if isinstance(type_spec, tuple):
        type_name = type_spec[0]
        if isinstance(type_name, PortType):
            return type_name
        type_spec = type_name
    
    if isinstance(type_spec, str):
        type_lower = type_spec.lower()
        if type_lower in TYPE_MAP:
            return TYPE_MAP[type_lower]
    
    return PortType.ANY


def get_type_config(type_spec: str | tuple) -> dict:
    if isinstance(type_spec, tuple) and len(type_spec) > 1:
        config = type_spec[1]
        if isinstance(config, dict):
            return config.copy()
    return {}


class BaseNode:
    title: str | None = None
    description: str = ""
    category: str = "General"
    color: str = "#2d4a7a"
    body_color: str | None = None
    locked_title: bool = False
    allow_folding: bool = True
    
    dynamic_input_prefix: str | None = None
    dynamic_output_prefix: str | None = None
    
    RETURN_TYPES: tuple = ()
    RETURN_NAMES: tuple | None = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        if 'title' not in cls.__dict__:
            name = cls.__name__
            if name.endswith("Node"):
                name = name[:-4]
            cls.title = name.lower()

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
        # GUI self-registration system
        self._gui_builders: dict[str, callable] = {}
        self._gui_builders_registered = False
        
        # Custom GUI properties for layout control
        self._custom_widget_height = 0
        self._custom_widget_below_ports = False
        self._custom_widget_full_width = False

        self._build_ports_from_schema()
        self._register_gui_builders()

        self.error_msg: str | None = None
        self.folded: bool = False
        self.title = getattr(self.__class__, 'title', self.__class__.__name__.lower())

    @property
    def display_name(self) -> str:
        """Get the display name for this node - uses custom name if set, otherwise title or class name."""
        # Use custom name if set and not empty
        if self.custom_name and self.custom_name.strip():
            return self.custom_name.strip()
        # Use title if set and not empty
        if self.title and self.title.strip():
            return self.title.strip()
        # Fall back to class name (without "Node" suffix)
        name = self.__class__.__name__
        if name.endswith("Node"):
            name = name[:-4]
        return name.lower()

    @classmethod
    def INPUT_TYPES(cls) -> dict:
        return {}

    def _build_ports_from_schema(self) -> None:
        schema = self.INPUT_TYPES()
        
        for name, spec in schema.get("required", {}).items():
            self._add_port_from_spec(name, spec, required=True)
        
        for name, spec in schema.get("optional", {}).items():
            self._add_port_from_spec(name, spec, required=False)
        
        self._build_outputs()

    def _add_port_from_spec(self, name: str, spec: Any, required: bool = False) -> Port:
        port_type = parse_type(spec)
        config = get_type_config(spec)
        
        default = config.get("default")
        visible = config.get("visible", True)
        editable = config.get("editable", True)
        display_in_inspector = config.get("display_in_inspector", True)
        enum_options = config.get("enum_options")
        enum_filter = config.get("enum_filter")
        graph_enum = config.get("graph_enum")
        label = config.get("label", "")
        is_dynamic = config.get("dynamic", False)
        allow_connection = config.get("allow_connection", True)
        
        # Set default for boolean ports
        if port_type == PortType.BOOL and default is None:
            default = False
        
        # Handle dynamic input ports with {n} pattern
        if is_dynamic or (isinstance(name, str) and "{n}" in name):
            base_name = name.replace("{n}", "")
            name = f"{base_name}1"
            is_dynamic = True
            self.dynamic_input_prefix = base_name
        
        p = Port(
            name=name,
            is_input=True,
            port_type=port_type,
            node_id=self.id,
            value=default
        )
        p.visible = visible
        p.editable = editable
        p.display_in_inspector = display_in_inspector
        p.required = required
        p.label = label
        p.is_dynamic = is_dynamic
        p.allow_connection = allow_connection
        
        # Set enum options if provided
        if enum_options is not None:
            p.enum_options = [str(opt) for opt in enum_options]
        if enum_filter is not None:
            p.enum_filter = enum_filter
        if graph_enum is not None:
            p.graph_enum = graph_enum
        
        # Set boolean enum options for UI compatibility
        if port_type == PortType.BOOL and enum_options is None:
            p.enum_options = ["True", "False"]
            if isinstance(default, bool):
                p.value = "True" if default else "False"
        
        self.inputs[name] = p
        return p

    def _build_outputs(self) -> None:
        types = self.RETURN_TYPES
        names = self.RETURN_NAMES
        
        for i, type_spec in enumerate(types):
            port_type = parse_type(type_spec)
            
            if names and i < len(names):
                name = names[i]
            else:
                name = f"output_{i}"
            
            p = Port(
                name=name,
                is_input=False,
                port_type=port_type,
                node_id=self.id
            )
            self.outputs[name] = p

    def validate(self) -> str | None:
        self.error_msg = None
        if not self.graph:
            return None

        missing = []
        for pname, port in self.inputs.items():
            if port.required and not self.graph.get_input_connection(self.id, pname):
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

    def resolve_path(self, path: str) -> str:
        if not path:
            return ""

        norm_path = os.path.normpath(str(path)).replace("\\", "/")

        base_dir = self._graph_base_dir()
        if base_dir:
            if os.path.isabs(norm_path):
                return norm_path
            return os.path.normpath(os.path.join(base_dir, norm_path)).replace("\\", "/")

        # Fallback: return as-is
        return norm_path

    def _graph_base_dir(self) -> str | None:
        """Returns the best available base directory for resolving/relativizing paths."""
        if not self.graph:
            return None
        if self.graph.file_path:
            return str(self.graph.file_path.parent)
        return getattr(self.graph, "output_dir", None) or getattr(self.graph, "project_dir", None)

    def _try_make_relative(self, abs_path: str, base_dir: str) -> str:
        """Return a relative path if abs_path is on the same drive as base_dir, else abs_path."""
        try:
            rel = os.path.relpath(abs_path, base_dir).replace("\\", "/")
            # Reject only if relpath couldn't find a common root (different Windows drives).
            # Leading '..' traversal is fine — it's valid relative syntax on all platforms.
            if not os.path.isabs(rel):
                return rel
        except ValueError:
            pass  # Different drives on Windows — keep absolute
        return abs_path.replace("\\", "/")

    def validate_file_input(self, path: str, must_exist: bool = True) -> str:
        resolved = self.resolve_path(path)
        if not resolved:
            self.fail("File path is empty.")
        if must_exist and not os.path.exists(resolved):
            self.fail(f"File not found: {resolved}")
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
        """Ensure one empty dynamic port at the end and auto-renumber when ports are removed."""
        if not self.graph:
            return False

        changed = False

        # Group dynamic ports by prefix and direction
        groups: dict[tuple[str, bool], PortType] = {}
        for p in self.inputs.values():
            if p.is_dynamic:
                groups[(p.name.rstrip("0123456789"), True)] = p.port_type
        for p in self.outputs.values():
            if p.is_dynamic:
                groups[(p.name.rstrip("0123456789"), False)] = p.port_type

        for (prefix, is_input), ptype in groups.items():
            # Collect all connected ports and their original indices
            connected_ports = {}
            for c in self.graph.connections:
                if is_input:
                    if c.dst_node == self.id and c.dst_port.startswith(prefix):
                        suffix = c.dst_port[len(prefix):]
                        if suffix.isdigit():
                            idx = int(suffix)
                            connected_ports[idx] = c.dst_port
                else:
                    if c.src_node == self.id and c.src_port.startswith(prefix):
                        suffix = c.src_port[len(prefix):]
                        if suffix.isdigit():
                            idx = int(suffix)
                            connected_ports[idx] = c.src_port

            # Sort connected ports by their original indices
            sorted_indices = sorted(connected_ports.keys())

            # Renumber ports to be consecutive (1, 2, 3, ...)
            renumber_map = {}
            new_idx = 1
            for old_idx in sorted_indices:
                if old_idx != new_idx:
                    renumber_map[old_idx] = new_idx
                    changed = True
                new_idx += 1

            # Apply renumbering to connections if needed
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

            # Calculate maximum connected port index
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

            # Ensure ports exist up to target count (at least one empty port)
            # Calculate target based on connected ports + minimum empty ports
            min_empty_ports = 1
            target_count = max(min_empty_ports, max_conn_idx + 1)
            port_dict = self.inputs if is_input else self.outputs

            for i in range(1, target_count + 1):
                name = f"{prefix}{i}"
                if name not in port_dict:
                    p = Port(name=name, is_input=is_input, port_type=ptype, node_id=self.id)
                    p.is_dynamic = True
                    p.visible = True
                    p.allow_connection = True
                    port_dict[name] = p
                    changed = True

            # Remove unused ports beyond target count
            ports_to_remove = []
            for name in port_dict.keys():
                if name.startswith(prefix):
                    suffix = name[len(prefix):]
                    if suffix.isdigit():
                        idx = int(suffix)
                        if idx > target_count:
                            ports_to_remove.append(name)
            
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
            # Store file paths relative to the graph file's directory if possible
            if v.port_type == PortType.FILE and val and self.graph and self.graph.file_path:
                try:
                    # Get the resolved absolute path of the file
                    abs_val = os.path.abspath(self.resolve_path(val))
                    base_dir = self.graph.file_path.parent
                    
                    # Compute relative path
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

        # Restore dynamic ports that may not exist in the base class
        # This isn't efficient at all but too bad
        values = data.get("values", {})
        for name in list(values.keys()):
            if name not in node.inputs:
                # Check if this matches a dynamic pattern
                for port in node.inputs.values():
                    if port.is_dynamic:
                        prefix = port.name.rstrip("0123456789")
                        if name.startswith(prefix) and name[len(prefix):].isdigit():
                            # Create the missing dynamic port
                            p = Port(name=name, is_input=True, port_type=port.port_type, node_id=node.id)
                            p.is_dynamic = True
                            node.inputs[name] = p
                            break

        # Restore input values with boolean normalization for UI compatibility
        for name, val in values.items():
            if name in node.inputs:
                port = node.inputs[name]
                if port.port_type == PortType.BOOL and isinstance(val, bool):
                    val = "True" if val else "False"
                port.value = val
        
        # Update node IDs for all ports
        for p in (*node.inputs.values(), *node.outputs.values()):
            p.node_id = node.id

        node._gui_builders_registered = False  # Reset flag to force re-registration. This is dumb.
        node._register_gui_builders()
        
        # Call on_property_changed after all ports and values are set
        if hasattr(node, 'on_property_changed'):
            node.on_property_changed()
        return node

    def configure_custom_widget(self, height: int = 0, below_ports: bool = False, full_width: bool = False):
        """
        Configure how custom widgets should be handled by the UI.
        """
        self._custom_widget_height = height
        self._custom_widget_below_ports = below_ports
        self._custom_widget_full_width = full_width

    # GUI Self-Registration System
    def _register_gui_builders(self) -> None:
        """Register GUI builders for this node. Override in subclasses."""
        self._gui_builders_registered = True
    
    def register_gui_builder(self, port_name: str, builder_func: callable) -> None:
        self._gui_builders[port_name] = builder_func
    
    def get_gui_builder(self, port_name: str) -> callable | None:
        return self._gui_builders.get(port_name)
    
    def has_gui_builder(self, port_name: str) -> bool:
        return port_name in self._gui_builders
    
    def create_widget_for_port(self, port, parent=None):
        """
        Create a widget for a port. Override in subclasses for custom widgets.
        
        Args:
            port: The port to create a widget for
            parent: Parent widget
            
        Returns:
            QWidget or None if no custom widget
        """
        builder = self.get_gui_builder(port.name)
        if builder:
            return builder(port, parent)
        
        if hasattr(self, 'create_custom_widget'):
            return self.create_custom_widget(port, parent)
        
        return None