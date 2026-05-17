from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QUndoCommand

from core.node import _coerce
from gui.logger import log

if TYPE_CHECKING:
    from gui.items.node import NodeItem


class ResizeNodeCommand(QUndoCommand):
    def __init__(self, item: NodeItem, old_w: float, old_h: float, new_w: float, new_h: float):
        super().__init__(f"Resize Node: {item.node.title}")
        self._scene   = item.scene()
        self._node_id = item.node.id
        self.old_w = old_w
        self.old_h = old_h
        self.new_w = new_w
        self.new_h = new_h

    def _get_item(self):
        return self._scene._node_items.get(self._node_id) if self._scene else None

    def undo(self):
        item = self._get_item()
        if item is None:
            return
        item.resize_to(self.old_w, self.old_h)
        sc = item.scene()
        if sc:
            sc._emit_graph_changed()
            sc._undo_manager.sync()

    def redo(self):
        item = self._get_item()
        if item is None:
            return
        item.resize_to(self.new_w, self.new_h)
        sc = item.scene()
        if sc:
            sc._emit_graph_changed()
            sc._undo_manager.sync()
        log.debug(f"Resized node to {self.new_w:.1f}x{self.new_h:.1f}")


class PropertyCommand(QUndoCommand):
    """Undo/redo a single port value change.  Works for both QLineEdit and QComboBox."""

    def __init__(self, node_item: NodeItem, port_name: str, old_val, new_val):
        super().__init__(f"Change {port_name}")
        self._scene   = node_item.scene()
        self._node_id = node_item.node.id
        self.port_name = port_name
        self.old_val   = old_val
        self.new_val   = new_val

    def _get_item(self):
        return self._scene._node_items.get(self._node_id) if self._scene else None

    def undo(self):
        item = self._get_item()
        if item is None:
            return
        self._apply(item, self.old_val)
        sc = item.scene()
        if sc:
            sc._undo_manager.sync()

    def redo(self):
        item = self._get_item()
        if item is None:
            return
        self._apply(item, self.new_val)
        sc = item.scene()
        if sc:
            sc._undo_manager.sync()

    def _apply(self, node_item, val) -> None:
        port = node_item.node.inputs.get(self.port_name)

        val_str = str(val) if val is not None else ""

        if port:
            _coerce(port, val_str)

        scene = node_item.scene()
        if scene and port:
            scene._after_node_mutation(node_item.node.id)
            scene._emit_graph_changed()


class FoldCommand(QUndoCommand):
    """Undo/redo node fold/unfold operations."""

    def __init__(self, node_item: NodeItem, old_folded: bool, new_folded: bool):
        super().__init__(f"{'Fold' if new_folded else 'Unfold'} Node: {node_item.node.title}")
        self._scene   = node_item.scene()
        self._node_id = node_item.node.id
        self.old_folded = old_folded
        self.new_folded = new_folded
        self.old_height = node_item._unfolded_height

    def _get_item(self):
        return self._scene._node_items.get(self._node_id) if self._scene else None

    def undo(self):
        item = self._get_item()
        if item is None:
            return
        self._apply(item, self.old_folded)
        sc = item.scene()
        if sc:
            sc._undo_manager.sync()

    def redo(self):
        item = self._get_item()
        if item is None:
            return
        self._apply(item, self.new_folded)
        sc = item.scene()
        if sc:
            sc._undo_manager.sync()

    def _apply(self, node_item, folded: bool) -> None:
        if not node_item.node.folded and folded:
            node_item._unfolded_height = node_item._h

        node_item.node.folded = folded
        node_item.refresh_ports()

        if not folded and self.old_height is not None:
            node_item.prepareGeometryChange()
            node_item._h = self.old_height
            node_item.node.height = self.old_height
            node_item.handle.setPos(node_item._w, node_item._h)
            node_item._unfolded_height = None

        node_item.handle.setVisible(not folded)

        scene = node_item.scene()
        if scene:
            scene.refresh_connections(node_item)
            scene._emit_graph_changed()
