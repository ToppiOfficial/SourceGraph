from core.node import BaseNode


class ModelNameNode(BaseNode):
    """Generates $modelname QC command."""
    title = "Model Name"
    CATEGORY = "QC"
    color = "#2a5a3a"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_path": ("STRING", {"default": "models/mymodel/model.mdl"}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, model_path: str, **kwargs):
        return (f'$modelname "{model_path}"',)


class CDMaterialsNode(BaseNode):
    """Generates $cdmaterials QC command."""
    title = "CD Materials"
    CATEGORY = "QC"
    color = "#2a5a3a"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "path": ("STRING", {"default": "models/mymodel/"}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, path: str, **kwargs):
        return (f'$cdmaterials "{path}"',)


class QCJoinNode(BaseNode):
    """Joins multiple QC commands into one."""
    title = "QC Join"
    CATEGORY = "QC"
    color = "#7a2d2d"
    body_color = "#2b1010"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "optional": {
                "command{n}": ("*", {"dynamic": True, "display_in_inspector": False}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, **kwargs):
        lines = []
        for k, v in kwargs.items():
            if k.startswith("command") and k[7:].isdigit() and v:
                # Extract command string from dict if needed
                if isinstance(v, dict) and "command" in v:
                    lines.append(str(v["command"]))
                else:
                    lines.append(str(v))
        return ("\n".join(lines),)


class MakeQCNode(BaseNode):
    """Combines multiple QC commands into one block."""
    title = "Make QC"
    CATEGORY = "QC"
    color = "#7a2d2d"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "optional": {
                "command{n}": ("*", {"dynamic": True, "display_in_inspector": False}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("qc_text",)

    def execute(self, **kwargs):
        lines = []
        for k, v in kwargs.items():
            if k.startswith("command") and k[7:].isdigit() and v:
                if isinstance(v, dict) and "command" in v:
                    lines.append(str(v["command"]))
                else:
                    lines.append(str(v))
        return ("\n".join(lines) + "\n",)