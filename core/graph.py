from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from .node import BaseNode
    from .execution import ExecutionContext, ExecutionResult
from nodes import NODE_CLASS_MAPPINGS


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
    assets: list[str] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)
    project_dir: str | None = None
    output_dir: str | None = None
    execution_sessions: list[dict] = field(default_factory=list)
    view_state: dict[str, Any] = field(default_factory=dict)
    asset_layout: list[dict] | None = None
    variable_layout: list[dict] | None = None
    time_unit: str = "ms"


class Graph:
    def __init__(self) -> None:
        self.nodes: dict[str, BaseNode] = {}
        self.connections: list[Connection] = []
        self.on_changed: list[Callable] = []
        self._state = GraphState()
        self._is_dirty: bool = False

    @property
    def state(self) -> GraphState:
        return self._state

    @property
    def assets(self) -> list[str]: return self._state.assets
    @assets.setter
    def assets(self, v): self._state.assets = v

    @property
    def variables(self) -> dict[str, Any]: return self._state.variables
    @variables.setter
    def variables(self, v): self._state.variables = v

    @property
    def asset_layout(self) -> list[dict] | None: return self._state.asset_layout
    @asset_layout.setter
    def asset_layout(self, v): self._state.asset_layout = v

    @property
    def variable_layout(self) -> list[dict] | None: return self._state.variable_layout
    @variable_layout.setter
    def variable_layout(self, v): self._state.variable_layout = v

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
        for cb in self.on_changed:
            cb()

    def add_node(self, node: BaseNode) -> None:
        self.nodes[node.id] = node
        self._notify()

    def remove_node(self, node_id: str) -> None:
        self.nodes.pop(node_id, None)
        self.connections = [c for c in self.connections
                            if c.src_node != node_id and c.dst_node != node_id]
        self._notify()

    def connect(self, src_node: str, src_port: str,
                dst_node: str, dst_port: str) -> bool:
        self.connections = [c for c in self.connections
                            if not (c.dst_node == dst_node and c.dst_port == dst_port)]
        self.connections.append(Connection(src_node, src_port, dst_node, dst_port))
        
        if src_node in self.nodes:
            self.nodes[src_node].sync_dynamic_ports()
        if dst_node in self.nodes:
            self.nodes[dst_node].sync_dynamic_ports()
        
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
        from .execution import StandardExecutionEngine

        engine = StandardExecutionEngine()
        return engine.execute(self, context)

    def to_dict(self) -> dict:
        return {
            "version":     "1.0",
            "nodes":       [n.to_dict() for n in self.nodes.values()],
            "connections": [c.to_dict() for c in self.connections],
            "variables":   self.variables,
            "assets":      self.assets,
            "execution":   self.execution_sessions,
            "view_state":  self.view_state,
            "asset_layout":    self._state.asset_layout,
            "variable_layout": self._state.variable_layout,
        }

    def load_dict(self, data: dict, registry: dict | None = None) -> None:
        from gui.logger import log
        
        if registry is None:
            registry = NODE_CLASS_MAPPINGS
        
        self.nodes.clear()
        self.connections.clear()
        
        self.variables.clear()
        vars_data = data.get("variables")
        if isinstance(vars_data, dict):
            self.variables.update(vars_data)

        self.assets.clear()
        assets_data = data.get("assets")
        if isinstance(assets_data, list):
            self.assets.extend(assets_data)

        exec_data = data.get("execution", [])
        if isinstance(exec_data, dict):
            self._state.execution_sessions = exec_data.get("sessions", [])
        else:
            self._state.execution_sessions = exec_data

        view_data = data.get("view_state", {})
        if isinstance(view_data, dict):
            self.view_state = view_data

        self._state.asset_layout = data.get("asset_layout")
        self._state.variable_layout = data.get("variable_layout")
        
        for nd in data.get("nodes", []):
            cls = registry.get(nd["type"])
            if cls:
                n = cls.from_dict(nd)
                n.graph = self
                self.nodes[n.id] = n
            else:
                log.warning(f"Unknown node type '{nd.get('type')}' — skipped")

        for cd in data.get("connections", []):
            self.connections.append(Connection.from_dict(cd))

        for node in self.nodes.values():
            node.sync_dynamic_ports()

        log.info(f"Graph loaded: {len(self.nodes)} nodes, {len(self.connections)} connections")

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def load(self, path: str | Path, registry: dict) -> None:
        self.load_dict(json.loads(Path(path).read_text(encoding="utf-8")), registry)