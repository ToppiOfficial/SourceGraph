from core.node import BaseNode


class BodyNode(BaseNode):
    """Generates $body QC command."""
    title = "Body"
    CATEGORY = "QC"
    color = "#2a5a3a"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "studio"}),
                "mesh_file": ("FILE", {}),
            },
            "hidden": {
                "_preview": "BOOL",
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, name: str, mesh_file: str, _preview: bool = False, **kwargs):
        mesh = self.validate_file_input(mesh_file, must_exist=not _preview)
        return (f'$body "{name}" "{mesh}"',)