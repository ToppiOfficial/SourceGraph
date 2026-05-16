from __future__ import annotations
import copy
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
import time
from enum import Enum, auto
from collections import defaultdict, deque
from .node import PortType
from core.graph_store_registry import get_volatile_store_specs


class ExecutionMode(Enum):
    PREVIEW = auto()
    EXPORT = auto()


class ExecutionTarget(Enum):
    JSON = "json"
    CUSTOM = "custom"


@dataclass
class ExecutionContext:
    mode: ExecutionMode = ExecutionMode.EXPORT
    target: ExecutionTarget = ExecutionTarget.JSON
    output_dir: str | None = None
    project_dir: str | None = None
    restore_port_values: bool = True

    on_node_start: Callable[[str, str], None] | None = None
    on_node_complete: Callable[[str, Any], None] | None = None
    on_node_error: Callable[[str, str], None] | None = None

    config: dict[str, Any] = field(default_factory=dict)

    def is_preview(self) -> bool:
        return self.mode == ExecutionMode.PREVIEW

    def should_write_files(self) -> bool:
        return self.mode == ExecutionMode.EXPORT and not self.is_preview()


class ExecutionResult:
    def __init__(self, node_id: str, outputs: dict[str, Any], 
                 status: str | None = None, error: str | None = None):
        self.node_id = node_id
        self.outputs = outputs
        self.status = status
        self.error = error
        self.success = error is None
    
    def get(self, port_name: str, default: Any = None) -> Any:
        return self.outputs.get(port_name, default)


class ExecutionEngine(Protocol):
    def execute(self, graph: Any, context: ExecutionContext) -> dict[str, ExecutionResult]:
        ...


class StandardExecutionEngine:
    
    def execute_node(self, nid: str, graph: Any, context: ExecutionContext, 
                     results: dict[str, ExecutionResult]) -> ExecutionResult:
        """
        Executes a single node, handling the full lifecycle (hooks, coercion, etc).
        This unifies execution logic between the main engine and the GUI panels.
        """
        node = None
        start_time = time.perf_counter()
        try:
            node = graph.nodes.get(nid)
            if node is None:
                raise RuntimeError(f"Node not found in graph: {nid}")

            if context.on_node_start:
                context.on_node_start(nid, node.title)

            validation_error = node.validate()
            if validation_error:
                raise ValueError(node.error_msg)
            
            original_input_values = {k: p.value for k, p in node.inputs.items()}
            original_output_values = {k: p.value for k, p in node.outputs.items()}

            # Gather input values from connected nodes
            connected = {
                c.dst_port: (results.get(c.src_node).outputs if results.get(c.src_node) else {}).get(c.src_port)
                for c in graph.connections if c.dst_node == nid
            }
            
            kwargs: dict[str, Any] = {}
            
            # Process input ports with type coercion
            for pname, port in node.inputs.items():
                value = connected.get(pname, port.value)
                
                if value is not None and port.port_type != PortType.ANY:
                    value = self._coerce_type(value, port.port_type)
                
                kwargs[pname] = value
                port.value = value
            
            # Add execution context parameters
            kwargs["_prompt"] = graph
            kwargs["_id"] = nid
            kwargs["_context"] = context
            
            # Sync port objects with processed values
            for pname, val in kwargs.items():
                if pname.startswith("_"):
                    continue
                in_port = node.inputs.get(pname)
                if in_port is not None:
                    in_port.value = val
            
            # Sync internal state before execution
            node.on_property_changed()
            
            result = node.execute(**kwargs)
            
            node.last_execution_time = time.perf_counter() - start_time

            # Normalize result to dictionary format
            if isinstance(result, tuple):
                out_dict = node._tuple_to_dict(result)
            elif isinstance(result, dict):
                out_dict = result
            else:
                names = list(node.outputs.keys())
                out_dict = {names[0]: result} if names else {}
            
            if out_dict is None:
                out_dict = {}
            
            # Update output port values
            for out_name, out_val in out_dict.items():
                if out_name in node.outputs:
                    node.outputs[out_name].value = out_val
            
            node.sync_presentation()
            
            status = None
            if "status" in out_dict:
                status = str(out_dict["status"])
            
            result_obj = ExecutionResult(nid, out_dict, status=status)
            
            if context.on_node_complete:
                context.on_node_complete(nid, result_obj)
                
            return result_obj
                
        except Exception as exc:
            error_msg = str(exc)
            if node is not None:
                node.error_msg = error_msg
                node.last_execution_time = time.perf_counter() - start_time
            result_obj = ExecutionResult(nid, {}, error=error_msg)
            
            if context.on_node_error:
                context.on_node_error(nid, error_msg)
            else:
                raise
            return result_obj

        finally:
            if context.restore_port_values:
                for k, v in original_input_values.items():
                    node.inputs[k].value = v
                for k, v in original_output_values.items():
                    node.outputs[k].value = v
                
    def execute(self, graph: Any, context: ExecutionContext) -> dict[str, ExecutionResult]:
        results: dict[str, ExecutionResult] = {}
        
        # Build dependency graph for topological sorting
        in_deg: dict[str, int] = {nid: 0 for nid in graph.nodes}
        adj: dict[str, list[str]] = defaultdict(list)
        
        for c in graph.connections:
            if c.src_node in in_deg and c.dst_node in in_deg:
                adj[c.src_node].append(c.dst_node)
                in_deg[c.dst_node] += 1
        
        # Add implicit dependencies (variable writers before readers)
        resource_writers: dict[str, list[str]] = defaultdict(list)
        for nid, node in graph.nodes.items():
            for res in node.get_writes():
                resource_writers[res].append(nid)
        
        for nid, node in graph.nodes.items():
            for res in node.get_reads():
                for w_nid in resource_writers.get(res, []):
                    if w_nid != nid and nid not in adj[w_nid]:
                        adj[w_nid].append(nid)
                        in_deg[nid] += 1
        
        # Topological sort to determine execution order
        queue = deque(nid for nid, d in in_deg.items() if d == 0)
        execution_order: list[str] = []
        
        while queue:
            nid = queue.popleft()
            execution_order.append(nid)
            for nb in adj[nid]:
                in_deg[nb] -= 1
                if in_deg[nb] == 0:
                    queue.append(nb)
        
        volatile_backup: dict[str, Any] = {}
        for spec in get_volatile_store_specs():
            volatile_backup.update(spec.dump(graph))
        volatile_backup = copy.deepcopy(volatile_backup)
        try:
            # Execute nodes in topological order
            for nid in execution_order:
                results[nid] = self.execute_node(nid, graph, context, results)
        finally:
            graph._state.ext_stores.update(volatile_backup)
        
        return results
    
    def _coerce_type(self, value: Any, target_type: Any) -> Any:
        """Coerce value to target port type for type safety."""
        
        if target_type == PortType.INT:
            return int(value)
        elif target_type == PortType.FLOAT:
            return float(value)
        elif target_type == PortType.BOOL:
            if isinstance(value, str):
                v = value.lower()
                if v in ("true", "1", "yes"):
                    return True
                elif v in ("false", "0", "no"):
                    return False
                else:
                    raise ValueError(f"Invalid boolean: '{value}'")
            return bool(value)
        elif target_type == PortType.DICT:
            if isinstance(value, str):
                return json.loads(value)
            return dict(value)
        elif target_type == PortType.ARRAY:
            if isinstance(value, list):
                return value
            return [value]
        
        return value


# Global execution engine instance
_default_engine: ExecutionEngine | None = None


def get_execution_engine() -> ExecutionEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = StandardExecutionEngine()
    return _default_engine


def set_execution_engine(engine: ExecutionEngine) -> None:
    global _default_engine
    _default_engine = engine


def execute_graph(graph: Any, 
                  mode: ExecutionMode = ExecutionMode.EXPORT,
                  target: ExecutionTarget = ExecutionTarget.JSON,
                  output_dir: str | None = None,
                  project_dir: str | None = None,
                  **kwargs) -> dict[str, ExecutionResult]:
    context = ExecutionContext(
        mode=mode,
        target=target,
        output_dir=output_dir,
        project_dir=project_dir,
        config=kwargs
    )
    
    engine = get_execution_engine()
    return engine.execute(graph, context)

# Type exports for convenience
__all__ = [
    "ExecutionMode",
    "ExecutionTarget", 
    "ExecutionContext",
    "ExecutionResult",
    "ExecutionEngine",
    "StandardExecutionEngine",
    "get_execution_engine",
    "set_execution_engine",
    "execute_graph",
]
