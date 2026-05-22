from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable


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
