from __future__ import annotations
import os
from core.node import BaseNode, In, Out


class SequenceNode(BaseNode):
    """Generates $sequence QC command."""
    title = "Sequence"
    CATEGORY = "QC Animation"
    color = "#2a5a3a"

    name = In("STRING", default="animation")
    animation_file = In("FILE", allow_connection=False)
    fps = In("FLOAT", default=30.0)

    command = Out("QC_COMMAND")

    def execute(self, name: str, animation_file: str, fps: float, _preview: bool = False, **kwargs):
        if not _preview and not os.path.exists(self.resolve_path(animation_file)):
            self.fail(f"File not found: {animation_file}")
        return (f'$sequence "{name}" "{animation_file}" fps {fps}',)
