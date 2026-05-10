from core.node import BaseNode, string_in, float_in, file_in, Out
from nodes.qc.shared_categories import QC_CATEGORY

class SequenceNode(BaseNode):
    """Generates $sequence QC command."""
    title = "Sequence"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    name = string_in(default="animation")
    animation_file = file_in()
    fps = float_in(default=30.0)

    command = Out("QC_COMMAND")

    def execute(self, name: str, animation_file: str, fps: float, _preview: bool = False, **kwargs):
        path = self.validate_file_input(animation_file, must_exist=not _preview)
        return (f'$sequence "{name}" "{path}" fps {fps}',)