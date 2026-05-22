from __future__ import annotations
import asyncio
import inspect
import time
from collections import defaultdict, deque
from typing import Any, Callable, Protocol

from sourcegraph.sys.execution.context import ExecutionContext, ExecutionResult
from sourcegraph.sys.utils.stores import backup_volatile_stores, restore_volatile_stores


class ExecutionEngine(Protocol):
    def execute(self, graph: Any, context: ExecutionContext) -> dict[str, ExecutionResult]:
        ...


class BaseExecutionEngine:
    """Shared helpers for topological-sort execution, input preparation, and result finalisation."""

    def _coerce_type(self, value: Any, target_type: str) -> Any:
        """Coerce value to target port type for type safety."""
        from sourcegraph.sys.registry.port_types import get_port_type_spec
        spec = get_port_type_spec(target_type)
        return spec.coerce_value(value) if spec and spec.coerce_value else value

    def _get_execution_order(self, graph: Any, subset_ids: list[str] | None = None) -> list[str]:
        """Return topologically sorted node IDs, optionally restricted to a needed subset."""
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

    def _prepare_node_execution(
        self,
        nid: str,
        graph: Any,
        context: ExecutionContext,
        results: dict[str, ExecutionResult],
    ) -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
        """Resolve inputs, coerce types, and return (node, kwargs, orig_inputs, orig_outputs)."""
        node = graph.nodes.get(nid)
        if node is None:
            raise RuntimeError(f"Node not found in graph: {nid}")

        if context.on_node_start:
            context.on_node_start(nid, node.title)

        validation_error = node.validate()
        if validation_error:
            raise ValueError(node.error_msg)

        original_input_values  = {k: p.value for k, p in node.inputs.items()}
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

        kwargs["_prompt"]  = graph
        kwargs["_id"]      = nid
        kwargs["_context"] = context

        for pname, val in kwargs.items():
            if pname.startswith("_"):
                continue
            in_port = node.inputs.get(pname)
            if in_port is not None:
                in_port.value = val

        node.on_property_changed()
        return node, kwargs, original_input_values, original_output_values

    def _finalize_node_execution(
        self,
        node: Any,
        nid: str,
        result: Any,
        context: ExecutionContext,
        start_time: float,
    ) -> ExecutionResult:
        """Convert node execute() return value into an ExecutionResult."""
        node.last_execution_time = time.perf_counter() - start_time

        if isinstance(result, tuple):
            out_dict = node._tuple_to_dict(result)
        elif isinstance(result, dict):
            out_dict = result
        else:
            names = list(node.outputs.keys())
            out_dict = {names[0]: result} if names else {}

        if out_dict is None:
            out_dict = {}

        for out_name, out_val in out_dict.items():
            if out_name in node.outputs:
                node.outputs[out_name].value = out_val

        status = str(out_dict["status"]) if "status" in out_dict else None
        result_obj = ExecutionResult(nid, out_dict, status=status)

        if context.on_node_complete:
            context.on_node_complete(nid, result_obj)

        return result_obj

    def _handle_node_error(
        self,
        node: Any,
        nid: str,
        exc: Exception,
        context: ExecutionContext,
        start_time: float,
    ) -> ExecutionResult:
        """Record error on node and return an error ExecutionResult, or re-raise if no handler."""
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
        """Restore port values to their pre-execution state when context requests it."""
        for k, v in original_inputs.items():
            node.inputs[k].value = v
        for k, v in original_outputs.items():
            node.outputs[k].value = v

    def _gather_dependency_info(self, graph: Any):
        """Return (in_degree_map, adjacency_list) for Kahn's topological sort."""
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
        """Find all nodes that must execute before any node in subset_ids (transitive deps)."""
        rev_adj = defaultdict(list)
        for src, neighbors in adj.items():
            for dst in neighbors:
                rev_adj[dst].append(src)

        needed: set[str] = set()

        def collect(nid):
            if nid in needed or nid not in graph.nodes:
                return
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

        volatile_backup = backup_volatile_stores(graph)
        try:
            for nid in execution_order:
                results[nid] = self.execute_node(nid, graph, context, results)
        finally:
            restore_volatile_stores(graph, volatile_backup)

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

    async def execute(self, graph: Any, context: ExecutionContext,
                      is_cancelled: Callable[[], bool] | None = None) -> dict[str, ExecutionResult]:
        """Execute the entire graph concurrently."""
        return await self.execute_subset(graph, list(graph.nodes.keys()), context, is_cancelled)

    async def execute_subset(self, graph: Any, node_ids: list[str], context: ExecutionContext,
                             is_cancelled: Callable[[], bool] | None = None) -> dict[str, ExecutionResult]:
        """Execute a subset of nodes and their dependencies concurrently."""
        results: dict[str, ExecutionResult] = {}

        in_deg_full, adj = self._gather_dependency_info(graph)
        needed = self._collect_needed_nodes(node_ids, adj, graph)
        in_deg = {nid: in_deg_full[nid] for nid in needed}
        queue = [nid for nid in needed if in_deg[nid] == 0]

        volatile_backup = backup_volatile_stores(graph)

        try:
            pending_tasks: dict[str, asyncio.Task] = {}
            task_to_nid:  dict[int, str]           = {}

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
                            pass
                        del pending_tasks[nid]
                        needed.discard(nid)
                        for nb in adj.get(nid, []):
                            if nb in in_deg:
                                in_deg[nb] -= 1
                                if in_deg[nb] == 0:
                                    queue.append(nb)

        finally:
            restore_volatile_stores(graph, volatile_backup)

        return results


_default_engine: ExecutionEngine | None = None


def get_execution_engine() -> ExecutionEngine:
    global _default_engine
    if _default_engine is None:
        _default_engine = AsyncExecutionEngine()
    return _default_engine


def set_execution_engine(engine: ExecutionEngine) -> None:
    global _default_engine
    _default_engine = engine


def execute_graph(
    graph: Any,
    mode: "ExecutionMode" = None,
    target: "ExecutionTarget" = None,
    output_dir: str | None = None,
    project_dir: str | None = None,
    **kwargs,
) -> dict[str, ExecutionResult]:
    from sourcegraph.sys.execution.context import ExecutionMode, ExecutionTarget
    context = ExecutionContext(
        mode=mode if mode is not None else ExecutionMode.EXPORT,
        target=target if target is not None else ExecutionTarget.JSON,
        output_dir=output_dir,
        project_dir=project_dir,
        config=kwargs,
    )
    engine = get_execution_engine()
    if inspect.iscoroutinefunction(engine.execute):
        return asyncio.run(engine.execute(graph, context))
    return engine.execute(graph, context)
