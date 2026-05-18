from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GraphState:
    project_dir: str | None = None
    output_dir: str | None = None
    execution_sessions: list[dict] = field(default_factory=list)
    view_state: dict[str, Any] = field(default_factory=dict)
    time_unit: str = "ms"
    ext_stores: dict[str, Any] = field(default_factory=dict)
