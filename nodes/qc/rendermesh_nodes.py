from __future__ import annotations
from core.node import BaseNode
from nodes.qc.shared_categories import RENDERMESH_PARAMETER_CATEGORY, QC_CATEGORY


class BodyNode(BaseNode):
    """Generates $body QC command."""
    title = "Body"
    CATEGORY = QC_CATEGORY
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


class BodygroupNode(BaseNode):
    """Generates $bodygroup QC block."""
    title = "Bodygroup"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "bodygroup"}),
            },
            "optional": {
                "item{n}": ("COMMAND", {"dynamic": True}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

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

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mesh_file": ("FILE", {}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, mesh_file: str, **kwargs):
        path = self.validate_file_input(mesh_file, must_exist=False)
        return (f'studio "{path}"',)


class BlankNode(BaseNode):
    """Generates 'blank' sub-command for Bodygroup blocks."""
    title = "Blank Mesh"
    CATEGORY = RENDERMESH_PARAMETER_CATEGORY
    color = "#2a5a3a"

    @classmethod
    def INPUT_TYPES(cls):
        return {}

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, **kwargs):
        return ("blank",)


class LODNode(BaseNode):
    """Generates $lod QC block."""
    title = "LOD"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "threshold": ("INT", {"default": 10}),
            },
            "optional": {
                "item{n}": ("COMMAND", {"dynamic": True}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

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

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_mesh": ("FILE", {}),
                "target_mesh": ("FILE", {}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, source_mesh: str, target_mesh: str, **kwargs):
        src = self.validate_file_input(source_mesh, must_exist=False)
        tgt = self.validate_file_input(target_mesh, must_exist=False)
        return (f'replacemodel "{src}" "{tgt}"',)


class ReplaceBoneNode(BaseNode):
    """Generates 'replacebone' sub-command for LOD blocks."""
    title = "Replace Bone"
    CATEGORY = RENDERMESH_PARAMETER_CATEGORY
    color = "#2a5a3a"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "source_bone": ("STRING", {"default": "bone_src"}),
                "target_bone": ("STRING", {"default": "bone_tgt"}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, source_bone: str, target_bone: str, **kwargs):
        return (f'replacebone "{source_bone}" "{target_bone}"',)


class RemoveMeshNode(BaseNode):
    """Generates 'removemesh' sub-command for LOD blocks."""
    title = "Remove Mesh"
    CATEGORY = RENDERMESH_PARAMETER_CATEGORY
    color = "#2a5a3a"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mesh_file": ("FILE", {}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, mesh_file: str, **kwargs):
        path = self.validate_file_input(mesh_file, must_exist=False)
        return (f'removemesh "{path}"',)
