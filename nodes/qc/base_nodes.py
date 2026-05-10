from core.node import BaseNode, In, DynIn, Out, string_in, any_out, command_out, dyn_in
from nodes.qc.shared_categories import QC_CATEGORY


class ModelNameNode(BaseNode):
    """Generates $modelname QC command."""
    title = "Model Name"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    model_path = string_in(default="models/mymodel/model.mdl", full_row=True)
    command    = Out("COMMAND")

    def execute(self, model_path: str, **kwargs):
        return (f'$modelname "{model_path}"',)


class CDMaterialsNode(BaseNode):
    """Generates $cdmaterials QC command."""
    title = "CD Materials"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    path    = string_in(default="models/mymodel/")
    command = Out("COMMAND")

    def execute(self, path: str, **kwargs):
        return (f'$cdmaterials "{path}"',)


class QCJoinNode(BaseNode):
    """Joins multiple QC commands into one."""
    title = "QC Join"
    CATEGORY = QC_CATEGORY
    color = "#7a2d2d"
    body_color = "#2b1010"

    cmds    = DynIn("*", prefix="command", editable=False)
    command = Out("COMMAND")

    def execute(self, **kwargs):
        parts = self.collect_dynamic("command", kwargs)
        return ("\n".join(str(p) for p in parts if p),)
