from __future__ import annotations
from core.node import BaseNode, string_in, int_in, file_in, DynIn, Out
from nodes.qc.shared_categories import RENDERMESH_PARAMETER_CATEGORY, QC_CATEGORY


class BodyNode(BaseNode):
    """Generates $body QC command."""
    title = "Body"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    name = string_in(default="studio")
    mesh_file = file_in()

    command = Out("QC_COMMAND")

    def execute(self, name: str, mesh_file: str, _preview: bool = False, **kwargs):
        mesh = self.validate_file_input(mesh_file, must_exist=not _preview)
        return (f'$body "{name}" "{mesh}"',)


class BodygroupNode(BaseNode):
    """Generates $bodygroup QC block."""
    title = "Bodygroup"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    name = string_in(default="bodygroup")
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

    mesh_file = file_in()

    command = Out("QC_COMMAND")

    def execute(self, mesh_file: str, **kwargs):
        path = self.validate_file_input(mesh_file, must_exist=False)
        return (f'studio "{path}"',)


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

    threshold = int_in(default=10)
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

    source_mesh = file_in()
    target_mesh = file_in()

    command = Out("QC_COMMAND")

    def execute(self, source_mesh: str, target_mesh: str, **kwargs):
        src = self.validate_file_input(source_mesh, must_exist=False)
        tgt = self.validate_file_input(target_mesh, must_exist=False)
        return (f'replacemodel "{src}" "{tgt}"',)


class ReplaceBoneNode(BaseNode):
    """Generates 'replacebone' sub-command for LOD blocks."""
    title = "Replace Bone"
    CATEGORY = RENDERMESH_PARAMETER_CATEGORY
    color = "#2a5a3a"

    source_bone = string_in(default="bone_src")
    target_bone = string_in(default="bone_tgt")

    command = Out("QC_COMMAND")

    def execute(self, source_bone: str, target_bone: str, **kwargs):
        return (f'replacebone "{source_bone}" "{target_bone}"',)


class RemoveMeshNode(BaseNode):
    """Generates 'removemesh' sub-command for LOD blocks."""
    title = "Remove Mesh"
    CATEGORY = RENDERMESH_PARAMETER_CATEGORY
    color = "#2a5a3a"

    mesh_file = file_in()

    command = Out("QC_COMMAND")

    def execute(self, mesh_file: str, **kwargs):
        path = self.validate_file_input(mesh_file, must_exist=False)
        return (f'removemesh "{path}"',)
