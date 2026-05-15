from __future__ import annotations

import copy
import weakref
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

from PySide6.QtCore import QTimer
from PySide6.QtGui  import QUndoCommand, QUndoStack

if TYPE_CHECKING:
    from .graph import Graph
    from .node import BaseNode
    from .commands import Command


@dataclass
class StateSnapshot:
    """Immutable capture of graph state used as the before/after in a command."""
    nodes:       dict[str, dict] = field(default_factory=dict)
    connections: list[dict]      = field(default_factory=list)
    variables:   dict[str, Any]  = field(default_factory=dict)
    assets:      list[str]       = field(default_factory=list)
    execution:   list[dict]      = field(default_factory=list)
    asset_layout: list[dict] | None = None
    variable_layout: list[dict] | None = None

    @classmethod
    def capture(cls, graph: Graph, external: dict | None = None) -> StateSnapshot:
        ext = external or {}
        return cls(
            nodes       = {nid: n.to_dict() for nid, n in graph.nodes.items()},
            connections = [c.to_dict() for c in graph.connections],
            variables   = copy.deepcopy(graph.variables),
            assets      = list(graph.assets),
            execution   = copy.deepcopy(ext.get("execution", [])),
            asset_layout = copy.deepcopy(graph.asset_layout) if graph.asset_layout is not None else None,
            variable_layout = copy.deepcopy(graph.variable_layout) if graph.variable_layout is not None else None,
        )

    def to_dict(self) -> dict:
        return {
            "nodes":       self.nodes,
            "connections": self.connections,
            "variables":   self.variables,
            "assets":      self.assets,
            "execution":   self.execution,
            "asset_layout": self.asset_layout,
            "variable_layout": self.variable_layout,
        }


class HistoryCommand(QUndoCommand):
    """
    Snapshot-based undo command.
    Qt calls redo() once immediately on push(). We skip that first call
    because the graph is already in the 'after' state.
    """

    def __init__(
        self,
        graph:       Graph,
        before:      StateSnapshot,
        after:       StateSnapshot,
        description: str,
        registry:    dict | None,
        manager:     "HistoryManager | None" = None,
    ) -> None:
        super().__init__(description)
        self.graph    = graph
        self.before   = before
        self.after    = after
        self.registry = registry
        self._mgr     = weakref.ref(manager) if manager else None
        self._first   = True

    def undo(self) -> None:
        self._first = False
        self._apply(self.before)

    def redo(self) -> None:
        if self._first:
            self._first = False
            return
        self._apply(self.after)

    def _apply(self, snapshot: StateSnapshot) -> None:
        from .graph import Connection

        mgr = self._mgr() if self._mgr else None

        already = mgr._restoring if mgr else False
        if mgr and not already:
            mgr._restoring = True

        try:
            selected: set[str] = set()
            if mgr:
                scene = getattr(mgr.graph, "_scene_ref", lambda: None)()
                if scene:
                    selected = {
                        item.node.id
                        for item in scene.selectedItems()
                        if hasattr(item, "node")
                    }

            self.graph.nodes.clear()
            self.graph.connections.clear()

            if self.registry:
                for nid, data in snapshot.nodes.items():
                    cls = self.registry.get(data.get("type"))
                    if cls:
                        node = cls.from_dict(data)
                        node.graph = self.graph
                        self.graph.nodes[nid] = node

            for cd in snapshot.connections:
                self.graph.connections.append(Connection.from_dict(cd))

            self.graph.variables.clear()
            self.graph.variables.update(copy.deepcopy(snapshot.variables))
            self.graph.assets.clear()
            self.graph.assets.extend(snapshot.assets)

            self.graph.asset_layout = copy.deepcopy(snapshot.asset_layout)
            self.graph.variable_layout = copy.deepcopy(snapshot.variable_layout)

            for node in self.graph.nodes.values():
                node.sync_dynamic_ports()
                if hasattr(node, "on_property_changed"):
                    node.on_property_changed()

            if mgr:
                scene = getattr(mgr.graph, "_scene_ref", lambda: None)()
                if scene and hasattr(scene, "set_external_state"):
                    scene.set_external_state({
                        "execution": snapshot.execution
                    })

                if scene and hasattr(scene, "_rebuild_from_graph"):
                    scene._rebuild_from_graph(selected)

                # Snapshot IS the new committed state — no re-capture needed.
                mgr._committed = snapshot

        finally:
            if mgr and not already:
                mgr._restoring = False


class _QCommandWrapper(QUndoCommand):
    """Wraps a core Command for the Qt undo stack.

    Skips the first redo() call because the command was already executed at
    push time. On subsequent redo/undo calls it re-executes/reverts.
    """

    def __init__(self, cmd: "Command", mgr: "HistoryManager") -> None:
        super().__init__(cmd.description)
        self._cmd  = cmd
        self._mgr  = weakref.ref(mgr) if mgr else None
        self._first = True

    def redo(self) -> None:
        if self._first:
            self._first = False
            return
        mgr = self._mgr() if self._mgr else None
        if mgr:
            mgr._restoring = True
        try:
            self._cmd.execute()
        finally:
            if mgr:
                mgr._restoring = False
        if mgr:
            mgr._committed = StateSnapshot.capture(mgr.graph, mgr._get_ext())

    def undo(self) -> None:
        self._first = False
        mgr = self._mgr() if self._mgr else None
        if mgr:
            mgr._restoring = True
        try:
            self._cmd.undo()
        finally:
            if mgr:
                mgr._restoring = False
        if mgr:
            mgr._committed = StateSnapshot.capture(mgr.graph, mgr._get_ext())


class CommandStack:
    """Executes Commands and records them on the Qt undo stack."""

    def __init__(self, qt_stack: QUndoStack, mgr: "HistoryManager") -> None:
        self._qt_stack = qt_stack
        self._mgr = mgr
        # Non-None while a transaction is collecting commands.
        self._current_batch: list | None = None

    def push(self, cmd: "Command") -> None:
        """Execute cmd and record it for undo (unless skipping or batching)."""
        cmd.execute()
        if self._mgr.is_skipping():
            return
        if self._current_batch is not None:
            self._current_batch.append(cmd)
            return
        self._push_wrapper(_QCommandWrapper(cmd, self._mgr))

    def _push_wrapper(self, wrapper: QUndoCommand) -> None:
        """Push a wrapper to the Qt stack with proper restoring guards."""
        self._mgr._debounce.stop()
        self._mgr._restoring = True
        try:
            self._qt_stack.push(wrapper)
        finally:
            self._mgr._restoring = False
        self._mgr._committed = StateSnapshot.capture(
            self._mgr.graph, self._mgr._get_ext()
        )

    def clear(self) -> None:
        self._qt_stack.clear()
        self._current_batch = None


class HistoryManager:
    """Hybrid history manager: delta Commands + snapshot fallback."""

    DEBOUNCE_MS = 600

    def __init__(self, graph: Graph, stack: QUndoStack | None = None) -> None:
        self.graph         = graph
        self.stack         = stack or QUndoStack()
        self.node_registry: dict[str, type] = {}

        self._skip_counter      = 0
        self._transaction_depth = 0
        self._restoring         = False
        self._immediate_next    = False
        self._pending_desc      = "Change"
        self._committed         = StateSnapshot.capture(graph, self._get_ext())

        self._debounce = QTimer()
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._auto_commit)

        self._cmd_stack = CommandStack(self.stack, self)

        if hasattr(graph, "on_changed"):
            graph.on_changed.append(self._on_change)
            self._committed = StateSnapshot.capture(graph, self._get_ext())

    def attach(self, scene) -> None:
        """Connect to a NodeEditorScene after it is created."""
        if self._on_change in self.graph.on_changed:
            self.graph.on_changed.remove(self._on_change)
        scene.graph_changed.connect(self._on_change)
        self._committed = StateSnapshot.capture(self.graph, self._get_ext())

    def register_undo(self, description: str, func: Callable) -> Callable:
        """Wrap a function so its execution is a named undo entry."""
        def wrapper(*args, **kwargs):
            with self.transaction(description):
                return func(*args, **kwargs)
        return wrapper

    def set_node_registry(self, registry: dict[str, type]) -> None:
        self.node_registry = registry

    @property
    def undo_stack(self) -> QUndoStack:
        return self.stack

    def _get_ext(self) -> dict:
        scene = getattr(self.graph, "_scene_ref", lambda: None)()
        if scene and hasattr(scene, "get_external_state"):
            return scene.get_external_state()
        return {}

    def notify_immediate(self, description: str = "Change") -> None:
        """Flush any pending diff immediately."""
        if self._skip_counter > 0 or self._transaction_depth > 0 or self._restoring:
            return
        self._debounce.stop()
        self._pending_desc = description
        self._auto_commit()

    def push(self, cmd: QUndoCommand) -> None:
        """Directly push a raw QUndoCommand (backward compatibility)."""
        if self._skip_counter > 0:
            return
        self._debounce.stop()
        self._restoring = True
        try:
            self.stack.push(cmd)
        finally:
            self._restoring = False
        self._committed = StateSnapshot.capture(self.graph, self._get_ext())

    def sync(self) -> None:
        """Re-sync committed baseline after a non-managed QUndoCommand completes."""
        if self._restoring:
            return
        self._debounce.stop()
        self._committed = StateSnapshot.capture(self.graph, self._get_ext())

    def clear(self) -> None:
        self._cmd_stack.clear()
        self._committed = StateSnapshot.capture(self.graph, self._get_ext())

    def set_undo_limit(self, limit: int) -> None:
        self.stack.setUndoLimit(limit)

    def is_skipping(self) -> bool:
        return self._skip_counter > 0

    def is_in_transaction(self) -> bool:
        return self._transaction_depth > 0

    @contextmanager
    def skip_undo(self):
        """Suppress all tracking (use for load / new / batch-rebuild)."""
        self._debounce.stop()
        self._skip_counter += 1
        try:
            yield
        finally:
            self._skip_counter -= 1
            if self._skip_counter == 0:
                self._committed = StateSnapshot.capture(self.graph, self._get_ext())

    @contextmanager
    def transaction(self, name: str = "Change"):
        """Group mutations into one undo entry (Commands if pushed, else snapshot diff)."""
        self._debounce.stop()
        before = self._committed if self._transaction_depth == 0 else None
        self._transaction_depth += 1
        outer = self._transaction_depth == 1
        if outer:
            self._cmd_stack._current_batch = []
        try:
            yield
        finally:
            self._transaction_depth -= 1
            if outer:
                batch = self._cmd_stack._current_batch
                self._cmd_stack._current_batch = None

                if batch:
                    from core.commands import CompositeCommand
                    composite = CompositeCommand(batch, name)
                    wrapper = _QCommandWrapper(composite, self)
                    self._cmd_stack._push_wrapper(wrapper)
                elif before is not None:
                    after = StateSnapshot.capture(self.graph, self._get_ext())
                    if after != before:
                        self._push_snapshot(before, after, name)

    def _on_change(self) -> None:
        """Slot wired to scene.graph_changed by attach()."""
        if self._skip_counter > 0 or self._restoring or self._transaction_depth > 0:
            return
        if self._immediate_next:
            self._immediate_next = False
            self._debounce.stop()
            self._auto_commit()
        else:
            self._debounce.start(self.DEBOUNCE_MS)

    def _auto_commit(self) -> None:
        """Diff current graph against _committed; push a command if changed."""
        if self._restoring or self._skip_counter > 0:
            return
        current = StateSnapshot.capture(self.graph, self._get_ext())
        if current != self._committed:
            desc = self._pending_desc
            self._pending_desc = "Change"
            self._push_snapshot(self._committed, current, desc)

    def _push_snapshot(
        self,
        before:      StateSnapshot,
        after:       StateSnapshot,
        description: str,
    ) -> None:
        cmd = HistoryCommand(
            self.graph, before, after, description, self.node_registry, self
        )
        self._restoring = True
        try:
            self.stack.push(cmd)
        finally:
            self._restoring = False
        self._committed = after


def undoable(manager: HistoryManager, description: str):
    """Decorator to wrap a method in an undo transaction."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            with manager.transaction(description):
                return func(*args, **kwargs)
        return wrapper
    return decorator


def create_history_manager(graph: Graph, stack: QUndoStack | None = None) -> HistoryManager:
    return HistoryManager(graph, stack)
