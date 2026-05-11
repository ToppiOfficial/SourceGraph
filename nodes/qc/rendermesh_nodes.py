from __future__ import annotations
from core.node import BaseNode, In, DynIn, Out
from nodes.qc.shared_categories import RENDERMESH_PARAMETER_CATEGORY, QC_CATEGORY


class BodyNode(BaseNode):
    """Generates $body QC command."""
    title = "Body"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    name = In("STRING", default="studio")
    mesh_file = In("FILE")

    command = Out("QC_COMMAND")

    def execute(self, name: str, mesh_file: str, **kwargs):
        return (f'$body "{name}" "{mesh_file}"',)


class BodygroupNode(BaseNode):
    """Generates $bodygroup QC block."""
    title = "Bodygroup"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    name = In("STRING", default="bodygroup")
    item = DynIn(prefix="item", editable=False)

    command = Out("QC_COMMAND")

    def execute(self, name: str, **kwargs):
        lines = [f'$bodygroup "{name}"', "{"]
        # Dynamic inputs are passed via kwargs
        for k, v in kwargs.items():
            if k.startswith("item") and k[4:].isdigit() and v:
                lines.append(f"    {v}")
        lines.append("}")
        return ("\n".join(lines),)


class StudioNode(BaseNode):
    """Generates 'studio' sub-command for Bodygroup or LOD blocks."""
    title = "Studio Mesh"
    CATEGORY = RENDERMESH_PARAMETER_CATEGORY
    color = "#2a5a3a"

    mesh_file = In("FILE", enum_filter=[".dmx", ".smd"], editable=False)

    command = Out("QC_COMMAND")

    def execute(self, mesh_file: str, **kwargs):
        return (f'studio "{mesh_file}"',)


class BlankNode(BaseNode):
    """Generates 'blank' sub-command for Bodygroup blocks."""
    title = "Blank Mesh"
    CATEGORY = RENDERMESH_PARAMETER_CATEGORY
    color = "#2a5a3a"

    command = Out("QC_COMMAND")

    def execute(self, **kwargs):
        return ("blank",)


class LODNode(BaseNode):
    """Generates $lod QC block."""
    title = "LOD"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    threshold = In("INT", default=10)
    item = DynIn(prefix="item")

    command = Out("QC_COMMAND")

    def execute(self, threshold: int, **kwargs):
        lines = [f'$lod {threshold}', "{"]
        for k, v in kwargs.items():
            if k.startswith("item") and k[4:].isdigit() and v:
                lines.append(f"    {v}")
        lines.append("}")
        return ("\n".join(lines),)


class ReplaceModelNode(BaseNode):
    """Generates 'replacemodel' sub-command for LOD blocks."""
    title = "Replace Model"
    CATEGORY = RENDERMESH_PARAMETER_CATEGORY
    color = "#2a5a3a"

    source_mesh = In("ANY")
    target_mesh = In("ANY")

    command = Out("QC_COMMAND")

    def execute(self, source_mesh: str, target_mesh: str, **kwargs):
        return (f'replacemodel "{source_mesh}" "{target_mesh}"',)


class ReplaceBoneNode(BaseNode):
    """Generates 'replacebone' sub-command for LOD blocks."""
    title = "Replace Bone"
    CATEGORY = RENDERMESH_PARAMETER_CATEGORY
    color = "#2a5a3a"

    source_bone = In("STRING", default="bone_src")
    target_bone = In("STRING", default="bone_tgt")

    command = Out("QC_COMMAND")

    def execute(self, source_bone: str, target_bone: str, **kwargs):
        return (f'replacebone "{source_bone}" "{target_bone}"',)


class RemoveMeshNode(BaseNode):
    """Generates 'removemesh' sub-command for LOD blocks."""
    title = "Remove Mesh"
    CATEGORY = RENDERMESH_PARAMETER_CATEGORY
    color = "#2a5a3a"

    mesh_file = In("FILE")

    command = Out("QC_COMMAND")

    def execute(self, mesh_file: str, **kwargs):
        return (f'removemesh "{mesh_file}"',)
