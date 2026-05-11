from __future__ import annotations
from core.node import (
    BaseNode, In, DynIn, Out,
)
from nodes.qc.shared_categories import QC_CATEGORY, MODEL_PARAMETER_CATEGORY


class ModelNode(BaseNode):
    """Generates $model QC command."""
    title = "Model"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    name      = In("STRING", default="studio")
    mesh_file = In("FILE", enum_filter=[".dmx", ".smd"], editable=False)
    params    = DynIn("COMMAND", prefix="param")
    command   = Out("QC_COMMAND")

    def execute(self, name: str, mesh_file: str, **kwargs):
        parts = [f'$model "{name}" "{mesh_file}"', "{"]
        for p in self.collect_dynamic("param", kwargs):
            parts.append(f"    {p}")
        parts.append("}")
        return ("\n".join(parts),)


class EyeballNode(BaseNode):
    """Generates eyeball parameter for $model."""
    title = "Eyeball"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    name          = In("STRING", default="eye")
    bone          = In("STRING", default="head")
    x             = In("FLOAT", default=0.0)
    y             = In("FLOAT", default=0.0)
    z             = In("FLOAT", default=0.0)
    material      = In("STRING", default="models/survivors/survivor_eyes")
    diameter      = In("FLOAT", default=1.0)
    angle         = In("FLOAT", default=0.0)
    iris_material = In("STRING", default="models/survivors/survivor_iris")
    pupil_scale   = In("FLOAT", default=1.0)
    param         = Out("QC_COMMAND")

    def execute(self, name, bone, x, y, z, material, diameter, angle, iris_material, pupil_scale, **kwargs):
        return (f'eyeball "{name}" "{bone}" {x} {y} {z} "{material}" {diameter} {angle} "{iris_material}" {pupil_scale}',)


class EyelidNode(BaseNode):
    """Generates eyelid parameter for $model (VTA/SMD style)."""
    title = "Eyelid"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    name           = In("STRING", default="upper_right")
    vta_file       = In("FILE", enum_filter=[".vta"],  editable=False)
    lowerer_frame  = In("INT", default=0)
    lowerer_height = In("FLOAT", default=-0.1)
    neutral_frame  = In("INT", default=0)
    neutral_height = In("FLOAT", default=0.00)
    raiser_frame   = In("INT", default=0)
    raiser_height  = In("FLOAT", default=0.1)
    split          = In("FLOAT", default=0.0)
    eyeball        = In("STRING", default="")
    param          = Out("QC_COMMAND")

    def execute(self, name, vta_file, lowerer_frame, lowerer_height,
                neutral_frame, neutral_height, raiser_frame, raiser_height, split, eyeball, **kwargs):
        return (f'eyelid "{name}" "{vta_file}"\n'
                f'  lowerer {lowerer_frame} {lowerer_height}\n'
                f'  neutral {neutral_frame} {neutral_height}\n'
                f'  raiser {raiser_frame} {raiser_height}\n'
                f'  split {split}\n'
                f'  eyeball {eyeball}',)


class DMXEyelidNode(BaseNode):
    """Generates dmxeyelid parameter for $model (DMX style)."""
    title = "DMX Eyelid"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    lid           = In("ENUM", enum_options=["upper", "lower"])
    dmx_file      = In("FILE", enum_filter=[".dmx"], editable=False)
    lowerer_delta = In("FLOAT", default=0.0)
    lowerer_pos   = In("FLOAT", default=-0.25)
    neutral_delta = In("FLOAT", default=0.0)
    neutral_pos   = In("FLOAT", default=0.0)
    raiser_delta  = In("FLOAT", default=0.0)
    raiser_pos    = In("FLOAT", default=0.25)
    righteyeball  = In("STRING", default="right_eye")
    lefteyeball   = In("STRING", default="left_eye")
    param         = Out("QC_COMMAND")

    def execute(self, lid, dmx_file, lowerer_delta, lowerer_pos,
                neutral_delta, neutral_pos, raiser_delta, raiser_pos,
                righteyeball, lefteyeball, **kwargs):
        return (f'dmxeyelid {lid} "{dmx_file}"\n'
                f'  lowerer {lowerer_delta} {lowerer_pos}\n'
                f'  neutral {neutral_delta} {neutral_pos}\n'
                f'  raiser {raiser_delta} {raiser_pos}\n'
                f'  righteyeball "{righteyeball}"\n'
                f'  lefteyeball "{lefteyeball}"',)


class MouthNode(BaseNode):
    """Generates mouth parameter for $model."""
    title = "Mouth"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    name       = In("STRING", default="mouth")
    attachment = In("STRING", default="mouth")
    bone       = In("STRING", default="head")
    x          = In("FLOAT", default=0.0)
    y          = In("FLOAT", default=0.0)
    z          = In("FLOAT", default=0.0)
    param      = Out("QC_COMMAND")

    def execute(self, name, attachment, bone, x, y, z, **kwargs):
        return (f'mouth "{name}" "{attachment}" "{bone}" {x} {y} {z}',)


class FlexControllerNode(BaseNode):
    """Generates flexcontroller parameter for $model."""
    title = "Flex Controller"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    name      = In("STRING", default="flex")
    flex_name = In("STRING", default="flex_target")
    min       = In("FLOAT", default=0.0)
    max       = In("FLOAT", default=1.0)
    param     = Out("QC_COMMAND")

    def execute(self, name, flex_name, min=0.0, max=1.0, **kwargs):
        return (f'flexcontroller "{name}" range {min} {max} "{flex_name}"',)


class FlexRuleNode(BaseNode):
    """Generates flexrule block for $model."""
    title = "Flex Rule"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    name       = In("STRING", default="rule_name")
    expression = In("STRING", default="flex_a * flex_b")
    param      = Out("QC_COMMAND")

    def execute(self, name, expression, **kwargs):
        return (f'flexrule "{name}"\n'
                f'{{\n'
                f'  {expression}\n'
                f'}}',)


class FlexFileNode(BaseNode):
    """Generates flexfile parameter for $model (VTA morph targets)."""
    title = "Flex File"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    vta_file = In("FILE", enum_filter=[".vta"])
    params   = DynIn("COMMAND", prefix="param")
    param    = Out("QC_COMMAND")

    def execute(self, vta_file, **kwargs):
        parts = [f'flexfile "{vta_file}"', "{"]
        for p in self.collect_dynamic("param", kwargs):
            parts.append(f"    {p}")
        parts.append("}")
        return ("\n".join(parts),)


class DefaultFlexNode(BaseNode):
    """Sets a default value for a flex controller."""
    title = "Default Flex"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    name  = In("STRING", default="flex_name")
    value = In("FLOAT", default=1.0)
    param = Out("QC_COMMAND")

    def execute(self, name, value, **kwargs):
        return (f'defaultflex "{name}" {value}',)


class LocalVarNode(BaseNode):
    """Defines local variables for flex rules."""
    title = "Local Var"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    names = In("STRING", default="var1 var2")
    param = Out("QC_COMMAND")

    def execute(self, names, **kwargs):
        return (f'localvar {names}',)


class FlagNode(BaseNode):
    """Generates simple flags for $model."""
    title = "Model Flag"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    flag  = In("ENUM", enum_options=["blank", "noninteract", "hidden", "no_flex_values", "noautodmxrules"],
                    allow_connection=False, full_row=True)
    param = Out("QC_COMMAND")

    def execute(self, flag, **kwargs):
        return (flag,)


class SphereNode(BaseNode):
    """Generates sphere parameter for $model."""
    title = "Sphere"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    x      = In("FLOAT", default=0.0)
    y      = In("FLOAT", default=0.0)
    z      = In("FLOAT", default=0.0)
    radius = In("FLOAT", default=1.0)
    param  = Out("QC_COMMAND")

    def execute(self, x, y, z, radius, **kwargs):
        return (f'sphere {x} {y} {z} {radius}',)
