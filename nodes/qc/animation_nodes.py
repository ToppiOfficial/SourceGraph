from core.node import BaseNode
from nodes.qc.shared_categories import QC_CATEGORY

class SequenceNode(BaseNode):
    """Generates $sequence QC command."""
    title = "Sequence"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "animation"}),
                "animation_file": ("FILE", {}),
                "fps": ("FLOAT", {"default": 30.0}),
            },
            "hidden": {
                "_preview": "BOOL",
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, name: str, animation_file: str, fps: float, _preview: bool = False, **kwargs):
        path = self.validate_file_input(animation_file, must_exist=not _preview)
        return (f'$sequence "{name}" "{path}" fps {fps}',)