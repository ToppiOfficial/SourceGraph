from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable
import traceback


class GraphEvent:
    """Base class for all graph events."""
    pass


@dataclass
class NodeAddedEvent(GraphEvent):
    node_id: str
    node_type: str
    x: float = 0.0
    y: float = 0.0


@dataclass
class NodeRemovedEvent(GraphEvent):
    node_id: str
    snapshot: dict = field(default_factory=dict)


@dataclass
class ConnectionAddedEvent(GraphEvent):
    src_node: str
    src_port: str
    dst_node: str
    dst_port: str


@dataclass
class ConnectionRemovedEvent(GraphEvent):
    src_node: str
    src_port: str
    dst_node: str
    dst_port: str


@dataclass
class NodeMovedEvent(GraphEvent):
    """List of (node_id, new_x, new_y) for batch position updates."""
    moves: list = field(default_factory=list)


@dataclass
class NodePropertyChangedEvent(GraphEvent):
    node_id: str
    port_name: str
    old_value: Any = None
    new_value: Any = None


@dataclass
class NodeResizedEvent(GraphEvent):
    node_id: str
    old_w: float = 0.0
    old_h: float = 0.0
    new_w: float = 0.0
    new_h: float = 0.0


@dataclass
class NodeFoldedEvent(GraphEvent):
    node_id: str
    folded: bool = False
    old_height: float | None = None
    unfolded_height: float | None = None


@dataclass
class GraphLoadedEvent(GraphEvent):
    """Emitted after a bulk load to trigger a full scene rebuild."""
    pass


@dataclass
class NodeExecutedEvent(GraphEvent):
    node_id: str


@dataclass
class NodeErrorEvent(GraphEvent):
    node_id: str
    error: str = ""


class EventBus:
    """
    Synchronous publish-subscribe bus. Plain Python, no Qt dependency.
    Handlers called synchronously in subscription order.
    """

    def __init__(self) -> None:
        self._subs: dict[type, list[Callable]] = {}

    def subscribe(self, event_type: type, handler: Callable) -> None:
        if event_type not in self._subs:
            self._subs[event_type] = []
        if handler not in self._subs[event_type]:
            self._subs[event_type].append(handler)

    def unsubscribe(self, event_type: type, handler: Callable) -> None:
        if event_type in self._subs:
            try:
                self._subs[event_type].remove(handler)
            except ValueError:
                pass

    def emit(self, event: GraphEvent) -> None:
        for klass in type(event).__mro__:
            if klass is object:
                continue
            for handler in list(self._subs.get(klass, [])):
                try:
                    handler(event)
                except Exception:
                    print(f"[EventBus] Error in handler for {type(event).__name__}:\n"
                          f"{traceback.format_exc()}")
