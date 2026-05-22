from __future__ import annotations
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from PySide6.QtCore import QPointF, Qt
    from sourcegraph.gui.node_editor import NodeEditorScene

# handler signature: (scene, pos, value, modifiers) -> bool  (True = handled)
DropHandler = Callable[["NodeEditorScene", "QPointF", str, "Qt.KeyboardModifiers"], bool]

_handlers: dict[str, DropHandler] = {}


def register_drop_handler(kind: str, handler: DropHandler) -> None:
    _handlers[kind] = handler


def dispatch(kind: str, scene, pos, value, modifiers) -> bool:
    handler = _handlers.get(kind)
    if handler:
        return handler(scene, pos, value, modifiers)
    return False
