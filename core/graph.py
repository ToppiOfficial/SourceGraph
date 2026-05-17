from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from core.registry import get_default_registry, NODE_CLASS_MAPPINGS
from core.graph_store_registry import get_all_store_specs
from core.execution import StandardExecutionEngine

if TYPE_CHECKING:
    from .node import BaseNode
    from .execution import ExecutionContext, ExecutionResult
from core.events import (
    EventBus, NodeAddedEvent, NodeRemovedEvent,
    ConnectionAddedEvent, ConnectionRemovedEvent, GraphLoadedEvent,
)

_logger = logging.getLogger(__name__)


@dataclass
class Connection:
    src_node: str
    src_port: str
    dst_node: str
    dst_port: str

    def to_dict(self) -> dict:
        return {"src_node": self.src_node, "src_port": self.src_port,
                "dst_node": self.dst_node, "dst_port": self.dst_port}

    @classmethod
    def from_dict(cls, d: dict) -> Connection:
        return cls(d["src_node"], d["src_port"], d["dst_node"], d["dst_port"])


@dataclass
class GraphState:
    project_dir: str | None = None
    output_dir: str | None = None
    execution_sessions: list[dict] = field(default_factory=list)
    view_state: dict[str, Any] = field(default_factory=dict)
    time_unit: str = "ms"
    ext_stores: dict[str, Any] = field(default_factory=dict)


class Graph:
    def __init__(self, bus: EventBus | None = None) -> None:
        self.nodes: dict[str, BaseNode] = {}
        self.connections: list[Connection] = []
        self.on_changed: list[Callable] = []
        self._state = GraphState()
        self._is_dirty: bool = False
        self.file_path: Path | None = None
        self.bus: EventBus = bus if bus is not None else EventBus()

    @property
    def state(self) -> GraphState:
        return self._state

    @property
    def variables(self) -> dict[str, Any]:
        return self._state.ext_stores.setdefault("variables", {})
    @variables.setter
    def variables(self, v): self._state.ext_stores["variables"] = v

    @property
    def variable_layout(self) -> list[dict] | None:
        return self._state.ext_stores.get("variable_layout")
    @variable_layout.setter
    def variable_layout(self, v): self._state.ext_stores["variable_layout"] = v

    def get_ext_store(self, key: str, default: Any = None) -> Any:
        return self._state.ext_stores.get(key, default)

    def set_ext_store(self, key: str, value: Any) -> None:
        self._state.ext_stores[key] = value

    @property
    def project_dir(self) -> str | None: return self._state.project_dir
    @project_dir.setter
    def project_dir(self, v): self._state.project_dir = v

    @property
    def output_dir(self) -> str | None: return self._state.output_dir
    @output_dir.setter
    def output_dir(self, v): self._state.output_dir = v

    @property
    def execution_sessions(self) -> list[dict]: return self._state.execution_sessions
    @execution_sessions.setter
    def execution_sessions(self, v): self._state.execution_sessions = v

    @property
    def view_state(self) -> dict[str, Any]: return self._state.view_state
    @view_state.setter
    def view_state(self, v): self._state.view_state = v

    @property
    def time_unit(self) -> str: return self._state.time_unit
    @time_unit.setter
    def time_unit(self, v: str): self._state.time_unit = v

    def _notify(self) -> None:
        self._is_dirty = True
        for cb in self.on_changed:
            cb()

    def commit_change(self, description: str = "Change") -> None:
        """Force an immediate history commit via the associated scene."""
        self._notify()
        scene = getattr(self, "_scene_ref", lambda: None)()
        if scene and hasattr(scene, "_undo_manager"):
            scene._undo_manager.notify_immediate(description)

    def add_node(self, node: BaseNode) -> None:
        node.graph = self
        self.nodes[node.id] = node
        self.bus.emit(NodeAddedEvent(
            node_id=node.id,
            node_type=type(node).__name__,
            x=node.x or 0.0,
            y=node.y or 0.0,
        ))
        self._notify()

    def remove_node(self, node_id: str) -> None:
        node = self.nodes.get(node_id)
        snapshot = node.to_dict() if node else {}
        self.nodes.pop(node_id, None)
        self.connections = [c for c in self.connections
                            if c.src_node != node_id and c.dst_node != node_id]
        self.bus.emit(NodeRemovedEvent(node_id=node_id, snapshot=snapshot))
        self._notify()

    def connect(self, src_node: str, src_port: str,
                dst_node: str, dst_port: str) -> bool:
        # Find connection being replaced on this dst port
        replaced = next((c for c in self.connections
                         if c.dst_node == dst_node and c.dst_port == dst_port), None)

        self.connections = [c for c in self.connections
                            if not (c.dst_node == dst_node and c.dst_port == dst_port)]
        self.connections.append(Connection(src_node, src_port, dst_node, dst_port))

        if src_node in self.nodes:
            self.nodes[src_node].sync_dynamic_ports()
        if dst_node in self.nodes:
            self.nodes[dst_node].sync_dynamic_ports()

        if replaced:
            self.bus.emit(ConnectionRemovedEvent(
                replaced.src_node, replaced.src_port,
                replaced.dst_node, replaced.dst_port,
            ))
        self.bus.emit(ConnectionAddedEvent(src_node, src_port, dst_node, dst_port))
        self._notify()
        return True

    def disconnect(self, src_node: str, src_port: str,
                   dst_node: str, dst_port: str) -> None:
        self.connections = [
            c for c in self.connections
            if not (c.src_node == src_node and c.src_port == src_port
                    and c.dst_node == dst_node and c.dst_port == dst_port)
        ]

        if src_node in self.nodes:
            self.nodes[src_node].sync_dynamic_ports()
        if dst_node in self.nodes:
            self.nodes[dst_node].sync_dynamic_ports()

        self.bus.emit(ConnectionRemovedEvent(src_node, src_port, dst_node, dst_port))
        self._notify()

    def get_input_connection(self, dst_node: str, dst_port: str) -> Connection | None:
        for c in self.connections:
            if c.dst_node == dst_node and c.dst_port == dst_port:
                return c
        return None

    def connections_for_node(self, node_id: str) -> list[Connection]:
        return [c for c in self.connections
                if c.src_node == node_id or c.dst_node == node_id]

    def execute_with_context(self, context: ExecutionContext) -> dict[str, ExecutionResult]:
        engine = StandardExecutionEngine()
        return engine.execute(self, context)

    def to_dict(self) -> dict:
        registry = get_default_registry()
        plugin_deps: set[str] = set()
        for node in self.nodes.values():
            src = registry.get_source(node.__class__.__name__)
            if src and src.startswith("plugin:"):
                plugin_deps.add(src[len("plugin:"):])

        d = {
            "version":          "1.0",
            "required_plugins": sorted(plugin_deps),
            "nodes":            [n.to_dict() for n in self.nodes.values()],
            "connections":      [c.to_dict() for c in self.connections],
            "execution":        self.execution_sessions,
            "view_state":       self.view_state,
        }
        for spec in get_all_store_specs():
            d.update(spec.dump(self))
        return d

    def load_dict(self, data: dict, registry: dict | None = None) -> None:
        _reg = get_default_registry()
        loaded_plugins = {s[len("plugin:"):] for s in _reg._sources.values() if s.startswith("plugin:")}
        self._missing_plugins: list[str] = [p for p in data.get("required_plugins", []) if p not in loaded_plugins]

        if registry is None:
            registry = NODE_CLASS_MAPPINGS

        self.nodes.clear()
        self.connections.clear()

        self._state.ext_stores.clear()
        for spec in get_all_store_specs():
            self._state.ext_stores.update(spec.load(data))

        exec_data = data.get("execution", [])
        if isinstance(exec_data, dict):
            self._state.execution_sessions = exec_data.get("sessions", [])
        else:
            self._state.execution_sessions = exec_data

        view_data = data.get("view_state", {})
        if isinstance(view_data, dict):
            self.view_state = view_data

        for nd in data.get("nodes", []):
            cls = registry.get(nd["type"])
            if cls:
                n = cls.from_dict(nd)
                n.graph = self
                self.nodes[n.id] = n
            else:
                _logger.warning(f"Unknown node type '{nd.get('type')}' - skipped")

        for cd in data.get("connections", []):
            self.connections.append(Connection.from_dict(cd))

        # Synchronize dynamic ports after connections so numbered slots (item1, item2…)
        # are created based on actual wiring rather than defaulting to 1 empty slot.
        for node in self.nodes.values():
            node.sync_dynamic_ports()

        _logger.info(f"Graph loaded: {len(self.nodes)} nodes, {len(self.connections)} connections")

        # Signal bulk load complete - scene subscribes to this and rebuilds
        self.bus.emit(GraphLoadedEvent())

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def load(self, path: str | Path, registry: dict) -> None:
        self.file_path = Path(path).resolve()
        self.load_dict(json.loads(self.file_path.read_text(encoding="utf-8")), registry)
