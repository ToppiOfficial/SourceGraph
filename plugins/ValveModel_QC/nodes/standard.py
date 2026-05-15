from __future__ import annotations
from core.node import BaseNode, In, DynIn, Out


class ModelNameNode(BaseNode):
    """Generates $modelname QC command."""
    title = "Model Name"
    CATEGORY = "QC"
    color = "#2a5a3a"

    model_path = In("STRING", default="models/mymodel/model.mdl", full_row=True)
    command    = Out("QC_COMMAND")

    def execute(self, model_path: str, **kwargs):
        return (f'$modelname "{model_path}"',)


class CDMaterialsNode(BaseNode):
    """Generates $cdmaterials QC command."""
    title = "CD Materials"
    CATEGORY = "QC Material"
    color = "#2a5a3a"

    path    = In("STRING", default="models/mymodel/")
    command = Out("QC_COMMAND")

    def execute(self, path: str, **kwargs):
        return (f'$cdmaterials "{path}"',)


class ConcatenateQCcommands(BaseNode):
    """Joins multiple QC commands into one."""
    title = "Concatenate QC commands"
    CATEGORY = "QC"
    color = "#7a2d2d"
    body_color = "#2b1010"

    cmds    = DynIn("ANY", prefix="command", editable=False)
    command = Out("QC_COMMAND")

    def execute(self, **kwargs):
        parts = self.collect_dynamic("command", kwargs)
        return ("\n".join(str(p) for p in parts if p),)
