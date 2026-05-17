from __future__ import annotations
import copy
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
import time
import asyncio
from enum import Enum, auto
from collections import defaultdict, deque
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


class BaseExecutionEngine:
    """Base class for execution engines with shared logic."""

    def _coerce_type(self, value: Any, target_type: str) -> Any:
        """Coerce value to target port type for type safety."""
        from core.port_type_registry import get_port_type_spec
        spec = get_port_type_spec(target_type)
        return spec.coerce_value(value) if spec and spec.coerce_value else value

    def _get_execution_order(self, graph: Any, subset_ids: list[str] | None = None) -> list[str]:
        """Compute topological sort of the graph or a subset of it."""
        in_deg, adj = self._gather_dependency_info(graph)
        
        queue = deque(nid for nid, d in in_deg.items() if d == 0)
        execution_order: list[str] = []
        
        while queue:
            nid = queue.popleft()
            execution_order.append(nid)
            for nb in adj[nid]:
                in_deg[nb] -= 1
                if in_deg[nb] == 0:
                    queue.append(nb)
        
        if subset_ids is not None:
            needed = self._collect_needed_nodes(subset_ids, adj, graph)
            return [nid for nid in execution_order if nid in needed]
            
        return execution_order

    def _prepare_node_execution(self, nid: str, graph: Any, context: ExecutionContext, 
                                results: dict[str, ExecutionResult]) -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Prepares a node for execution, gathering inputs and coercion."""
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

        connected = {
            c.dst_port: (results.get(c.src_node).outputs if results.get(c.src_node) else {}).get(c.src_port)
            for c in graph.connections if c.dst_node == nid
        }
        
        kwargs: dict[str, Any] = {}
        for pname, port in node.inputs.items():
            value = connected.get(pname, port.value)
            if value is not None and port.port_type != "any":
                value = self._coerce_type(value, port.port_type)
            kwargs[pname] = value
            port.value = value
        
        kwargs["_prompt"] = graph
        kwargs["_id"] = nid
        kwargs["_context"] = context
        
        for pname, val in kwargs.items():
            if pname.startswith("_"): continue
            in_port = node.inputs.get(pname)
            if in_port is not None: in_port.value = val
        
        node.on_property_changed()
        return node, kwargs, original_input_values, original_output_values

    def _finalize_node_execution(self, node: Any, nid: str, result: Any, 
                                 context: ExecutionContext, start_time: float) -> ExecutionResult:
        """Processes the result of a node execution."""
        node.last_execution_time = time.perf_counter() - start_time

        if isinstance(result, tuple):
            out_dict = node._tuple_to_dict(result)
        elif isinstance(result, dict):
            out_dict = result
        else:
            names = list(node.outputs.keys())
            out_dict = {names[0]: result} if names else {}
        
        if out_dict is None: out_dict = {}
        
        for out_name, out_val in out_dict.items():
            if out_name in node.outputs:
                node.outputs[out_name].value = out_val
        
        status = str(out_dict["status"]) if "status" in out_dict else None
        result_obj = ExecutionResult(nid, out_dict, status=status)
        
        if context.on_node_complete:
            context.on_node_complete(nid, result_obj)
            
        return result_obj

    def _handle_node_error(self, node: Any, nid: str, exc: Exception, 
                           context: ExecutionContext, start_time: float) -> ExecutionResult:
        """Handles errors during node execution."""
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

    def _restore_port_values(self, node: Any, original_inputs: dict, original_outputs: dict):
        """Restores port values if context requires it."""
        for k, v in original_inputs.items():
            node.inputs[k].value = v
        for k, v in original_outputs.items():
            node.outputs[k].value = v

    def _gather_dependency_info(self, graph: Any):
        """Returns in-degree and adjacency list for the graph."""
        in_deg: dict[str, int] = {nid: 0 for nid in graph.nodes}
        adj: dict[str, list[str]] = defaultdict(list)
        
        for c in graph.connections:
            if c.src_node in in_deg and c.dst_node in in_deg:
                adj[c.src_node].append(c.dst_node)
                in_deg[c.dst_node] += 1
        
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
        return in_deg, adj

    def _collect_needed_nodes(self, subset_ids: list[str], adj: dict[str, list[str]], graph: Any) -> set[str]:
        """Finds all nodes needed by the subset (recursively through dependencies)."""
        rev_adj = defaultdict(list)
        for src, neighbors in adj.items():
            for dst in neighbors:
                rev_adj[dst].append(src)
                
        needed = set()
        def collect(nid):
            if nid in needed or nid not in graph.nodes: return
            needed.add(nid)
            for dep in rev_adj[nid]:
                collect(dep)
                
        for tid in subset_ids:
            collect(tid)
        return needed


class StandardExecutionEngine(BaseExecutionEngine):
    
    def execute_node(self, nid: str, graph: Any, context: ExecutionContext, 
                     results: dict[str, ExecutionResult]) -> ExecutionResult:
        node = None
        start_time = time.perf_counter()
        original_inputs, original_outputs = {}, {}
        try:
            node, kwargs, original_inputs, original_outputs = self._prepare_node_execution(nid, graph, context, results)
            result = node.execute(**kwargs)
            return self._finalize_node_execution(node, nid, result, context, start_time)
        except Exception as exc:
            return self._handle_node_error(node, nid, exc, context, start_time)
        finally:
            if context.restore_port_values and node:
                self._restore_port_values(node, original_inputs, original_outputs)
                
    def execute(self, graph: Any, context: ExecutionContext) -> dict[str, ExecutionResult]:
        results: dict[str, ExecutionResult] = {}
        execution_order = self._get_execution_order(graph)
        
        volatile_backup: dict[str, Any] = {}
        for spec in get_volatile_store_specs():
            volatile_backup.update(spec.dump(graph))
        volatile_backup = copy.deepcopy(volatile_backup)
        try:
            for nid in execution_order:
                results[nid] = self.execute_node(nid, graph, context, results)
        finally:
            graph._state.ext_stores.update(volatile_backup)
        
        return results


class AsyncExecutionEngine(BaseExecutionEngine):
    """Execution engine that supports async node execution and parallel branches."""

    async def execute_node(self, nid: str, graph: Any, context: ExecutionContext, 
                          results: dict[str, ExecutionResult]) -> ExecutionResult:
        node = None
        start_time = time.perf_counter()
        original_inputs, original_outputs = {}, {}
        try:
            node, kwargs, original_inputs, original_outputs = self._prepare_node_execution(nid, graph, context, results)
            
            if inspect.iscoroutinefunction(node.execute):
                result = await node.execute(**kwargs)
            elif getattr(node, 'THREAD_SAFE', False):
                # Offload CPU/IO-bound sync nodes to the thread pool so the event
                # loop stays free to dispatch other independent nodes in parallel.
                # Only safe for nodes whose execute() never mutates shared graph state.
                result = await asyncio.to_thread(node.execute, **kwargs)
            else:
                result = node.execute(**kwargs)
                
            return self._finalize_node_execution(node, nid, result, context, start_time)
        except Exception as exc:
            return self._handle_node_error(node, nid, exc, context, start_time)
        finally:
            if context.restore_port_values and node:
                self._restore_port_values(node, original_inputs, original_outputs)

    async def execute(self, graph: Any, context: ExecutionContext, is_cancelled: Callable[[], bool] | None = None) -> dict[str, ExecutionResult]:
        """Executes the entire graph concurrently."""
        return await self.execute_subset(graph, list(graph.nodes.keys()), context, is_cancelled)

    async def execute_subset(self, graph: Any, node_ids: list[str], context: ExecutionContext, 
                             is_cancelled: Callable[[], bool] | None = None) -> dict[str, ExecutionResult]:
        """Executes a subset of nodes and their dependencies concurrently."""
        results: dict[str, ExecutionResult] = {}
        
        in_deg_full, adj = self._gather_dependency_info(graph)
        needed = self._collect_needed_nodes(node_ids, adj, graph)
        in_deg = {nid: in_deg_full[nid] for nid in needed}
        queue = [nid for nid in needed if in_deg[nid] == 0]
        
        volatile_backup: dict[str, Any] = {}
        for spec in get_volatile_store_specs():
            volatile_backup.update(spec.dump(graph))
        volatile_backup = copy.deepcopy(volatile_backup)
        
        try:
            pending_tasks: dict[str, asyncio.Task] = {}  # nid -> Task
            task_to_nid:  dict[int, str]           = {}  # id(task) -> nid for O(1) reverse lookup

            while needed or pending_tasks:
                if is_cancelled and is_cancelled():
                    for t in pending_tasks.values():
                        t.cancel()
                    raise asyncio.CancelledError("Execution cancelled by user")

                for nid in list(queue):
                    queue.remove(nid)
                    task = asyncio.create_task(self.execute_node(nid, graph, context, results))
                    pending_tasks[nid] = task
                    task_to_nid[id(task)] = nid

                if not pending_tasks and needed:
                    raise RuntimeError(f"Deadlock detected in execution graph. Remaining: {list(needed)}")

                if pending_tasks:
                    # React the moment any task completes; timeout keeps is_cancelled responsive.
                    done, _ = await asyncio.wait(
                        set(pending_tasks.values()),
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=0.1,
                    )
                    for task in done:
                        nid = task_to_nid.pop(id(task), None)
                        if nid is None:
                            continue
                        try:
                            results[nid] = task.result()
                        except (asyncio.CancelledError, Exception):
                            pass  # execute_node already stores error in results when on_node_error is set
                        del pending_tasks[nid]
                        needed.discard(nid)
                        for nb in adj.get(nid, []):
                            if nb in in_deg:
                                in_deg[nb] -= 1
                                if in_deg[nb] == 0:
                                    queue.append(nb)

        finally:
            graph._state.ext_stores.update(volatile_backup)
            
        return results


# Global execution engine instance
_default_engine: ExecutionEngine | None = None


def get_execution_engine() -> ExecutionEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = AsyncExecutionEngine()
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
    if inspect.iscoroutinefunction(engine.execute):
        return asyncio.run(engine.execute(graph, context))
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
