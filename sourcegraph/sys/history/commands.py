"""
Delta-based command objects for undo/redo.

All commands are plain Python - no Qt imports.
Scene access is via weakref to avoid circular imports.
Commands execute immediately when pushed; history/manager.py handles Qt undo-stack integration.
"""
from __future__ import annotations
import weakref
from typing import Any, TYPE_CHECKING

from sourcegraph.sys.utils.refs import safe_deref

if TYPE_CHECKING:
    from sourcegraph.sys.graph.graph import Graph


class Command:
    """Base class for all undoable commands."""
    description: str = "Command"

    def execute(self) -> None: ...
    def undo(self) -> None: ...


class AddNodeCommand(Command):
    """Add a node to the graph. Undo removes it."""

    def __init__(self, graph: Graph, node, scene_ref=None, registry: dict | None = None):
        self.graph = graph
        self.node = node
        self._scene_ref = scene_ref
        self._registry = registry
        self.description = f"Add {getattr(node, 'display_name', type(node).__name__)}"

    def execute(self) -> None:
        self.graph.add_node(self.node)

    def undo(self) -> None:
        self.graph.remove_node(self.node.id)


class RemoveNodeCommand(Command):
    """Remove a node from the graph. Undo re-adds it from snapshot."""

    def __init__(self, graph: Graph, node_id: str, snapshot: dict,
                 conn_snapshots: list[dict], registry: dict | None = None,
                 scene_ref=None):
        self.graph = graph
        self.node_id = node_id
        self.snapshot = snapshot
        self.conn_snapshots = conn_snapshots
        self._registry = registry
        self._scene_ref = scene_ref
        title = snapshot.get("title", node_id)
        self.description = f"Delete {title}"

    def execute(self) -> None:
        scene = safe_deref(self._scene_ref)

        affected = set()
        for c in self.graph.connections:
            if c.src_node == self.node_id:
                affected.add(c.dst_node)
            elif c.dst_node == self.node_id:
                affected.add(c.src_node)

        self.graph.remove_node(self.node_id)

        if scene:
            for nid in affected:
                if nid in self.graph.nodes:
                    scene._after_node_mutation(nid)
            scene._flush_updates()
            scene.graph_changed.emit()

    def undo(self) -> None:
        scene = safe_deref(self._scene_ref)

        if self._registry is None:
            return
        cls = self._registry.get(self.snapshot.get("type"))
        if cls is None:
            return
        node = cls.from_dict(self.snapshot)
        self.graph.add_node(node)

        affected = set()
        for cd in self.conn_snapshots:
            try:
                self.graph.connect(cd["src_node"], cd["src_port"],
                                   cd["dst_node"], cd["dst_port"])
                for nid in (cd["src_node"], cd["dst_node"]):
                    if nid != self.node_id:
                        affected.add(nid)
            except Exception:
                pass

        if scene:
            for nid in affected:
                if nid in self.graph.nodes:
                    scene._after_node_mutation(nid)
            scene._flush_updates()
            scene.graph_changed.emit()


class ConnectCommand(Command):
    """Connect two ports. Undo disconnects."""

    def __init__(self, graph: Graph, src_node: str, src_port: str,
                 dst_node: str, dst_port: str,
                 replaced_conn=None, scene_ref=None):
        self.graph = graph
        self.src_node = src_node
        self.src_port = src_port
        self.dst_node = dst_node
        self.dst_port = dst_port
        self.replaced_conn = replaced_conn
        self._scene_ref = scene_ref
        self.description = "Connect Ports"

    def execute(self) -> None:
        scene = safe_deref(self._scene_ref)

        if scene and self.replaced_conn:
            rc = self.replaced_conn
            for pair in list(scene._conn_items):
                if pair[0] == rc:
                    try:
                        scene.removeItem(pair[1])
                    except RuntimeError:
                        pass
                    scene._conn_items.remove(pair)
                    break

        if scene:
            scene._suppress_bus = True
        try:
            self.graph.connect(self.src_node, self.src_port,
                               self.dst_node, self.dst_port)
        finally:
            if scene:
                scene._suppress_bus = False

        if scene:
            scene._cleanup_ghost_connections()
            conn = self.graph.get_input_connection(self.dst_node, self.dst_port)
            if conn:
                scene._materialise_conn(conn)
            scene._after_node_mutation(self.src_node)
            scene._after_node_mutation(self.dst_node)
            scene._flush_updates()
            scene.graph_changed.emit()

    def undo(self) -> None:
        scene = safe_deref(self._scene_ref)

        if scene:
            scene._suppress_bus = True
        try:
            self.graph.disconnect(self.src_node, self.src_port,
                                  self.dst_node, self.dst_port)
        finally:
            if scene:
                scene._suppress_bus = False

        if scene:
            key = (self.src_node, self.src_port, self.dst_node, self.dst_port)
            for pair in list(scene._conn_items):
                c, ci = pair
                if (c.src_node, c.src_port, c.dst_node, c.dst_port) == key:
                    try:
                        scene.removeItem(ci)
                    except RuntimeError:
                        pass
                    scene._conn_items.remove(pair)
                    break

        if self.replaced_conn:
            rc = self.replaced_conn
            if scene:
                scene._suppress_bus = True
            try:
                self.graph.connect(rc.src_node, rc.src_port, rc.dst_node, rc.dst_port)
            finally:
                if scene:
                    scene._suppress_bus = False
            if scene:
                scene._cleanup_ghost_connections()
                conn = self.graph.get_input_connection(rc.dst_node, rc.dst_port)
                if conn:
                    scene._materialise_conn(conn)
                scene._after_node_mutation(rc.src_node)
                scene._after_node_mutation(rc.dst_node)
                scene._flush_updates()
        elif scene:
            scene._after_node_mutation(self.src_node)
            scene._after_node_mutation(self.dst_node)
            scene._flush_updates()

        if scene:
            scene.graph_changed.emit()


class DisconnectCommand(Command):
    """Disconnect two ports. Undo reconnects."""

    def __init__(self, graph: Graph, src_node: str, src_port: str,
                 dst_node: str, dst_port: str, scene_ref=None):
        self.graph = graph
        self.src_node = src_node
        self.src_port = src_port
        self.dst_node = dst_node
        self.dst_port = dst_port
        self._scene_ref = scene_ref
        self.description = "Disconnect"

    def execute(self) -> None:
        scene = safe_deref(self._scene_ref)

        if scene:
            scene._suppress_bus = True
        try:
            self.graph.disconnect(self.src_node, self.src_port,
                                  self.dst_node, self.dst_port)
        finally:
            if scene:
                scene._suppress_bus = False

        if scene:
            key = (self.src_node, self.src_port, self.dst_node, self.dst_port)
            for pair in list(scene._conn_items):
                c, ci = pair
                if (c.src_node, c.src_port, c.dst_node, c.dst_port) == key:
                    try:
                        scene.removeItem(ci)
                    except RuntimeError:
                        pass
                    scene._conn_items.remove(pair)
                    break

            scene._after_node_mutation(self.src_node)
            scene._after_node_mutation(self.dst_node)
            scene._flush_updates()
            scene.graph_changed.emit()

    def undo(self) -> None:
        scene = safe_deref(self._scene_ref)

        if scene:
            scene._suppress_bus = True
        try:
            self.graph.connect(self.src_node, self.src_port,
                               self.dst_node, self.dst_port)
        finally:
            if scene:
                scene._suppress_bus = False

        if scene:
            scene._cleanup_ghost_connections()
            conn = self.graph.get_input_connection(self.dst_node, self.dst_port)
            if conn:
                scene._materialise_conn(conn)
            scene._after_node_mutation(self.src_node)
            scene._after_node_mutation(self.dst_node)
            scene._flush_updates()
            scene.graph_changed.emit()


class MoveNodesCommand(Command):
    """Move one or more nodes. Stores (node_id, old_x, old_y, new_x, new_y) tuples."""

    def __init__(self, graph: Graph, moves: list[tuple], scene_ref=None):
        self.graph = graph
        self.moves = moves
        self._scene_ref = scene_ref
        self.description = "Move Nodes"

    def _apply(self, use_new: bool) -> None:
        scene = safe_deref(self._scene_ref)
        for node_id, old_x, old_y, new_x, new_y in self.moves:
            x, y = (new_x, new_y) if use_new else (old_x, old_y)
            node = self.graph.nodes.get(node_id)
            if node:
                node.x, node.y = x, y
            if scene:
                item = scene._node_items.get(node_id)
                if item:
                    item.setPos(x, y)
                    scene.refresh_connections(item)
        if scene:
            scene.graph_changed.emit()

    def execute(self) -> None:
        self._apply(use_new=True)

    def undo(self) -> None:
        self._apply(use_new=False)


class ChangePropertyCommand(Command):
    """Change a port value. Undo restores the old value."""

    def __init__(self, graph: Graph, node_id: str, port_name: str,
                 old_val: Any, new_val: Any, scene_ref=None):
        self.graph = graph
        self.node_id = node_id
        self.port_name = port_name
        self.old_val = old_val
        self.new_val = new_val
        self._scene_ref = scene_ref
        self.description = f"Change {port_name}"

    def _apply(self, val: Any) -> None:
        node = self.graph.nodes.get(self.node_id)
        if node is None:
            return
        port = node.inputs.get(self.port_name)
        if port is None:
            return
        from sourcegraph.sys.node.base import _coerce
        val_str = str(val) if val is not None else ""
        _coerce(port, val_str)

        scene = safe_deref(self._scene_ref)
        if scene:
            scene._after_node_mutation(self.node_id)
            scene._emit_graph_changed()

    def execute(self) -> None:
        self._apply(self.new_val)

    def undo(self) -> None:
        self._apply(self.old_val)


class CompositeCommand(Command):
    """Groups multiple commands into one undoable step."""

    def __init__(self, commands: list[Command], description: str):
        self.commands = list(commands)
        self.description = description

    def execute(self) -> None:
        for cmd in self.commands:
            cmd.execute()

    def undo(self) -> None:
        for cmd in reversed(self.commands):
            cmd.undo()
