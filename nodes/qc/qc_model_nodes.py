from __future__ import annotations
from core.node import (
    BaseNode, In, OptIn, DynIn, Out,
    string_in, int_in, float_in, opt_float_in, command_out, dyn_in, enum_in,
)
from nodes.qc.shared_categories import QC_CATEGORY, MODEL_PARAMETER_CATEGORY


class ModelNode(BaseNode):
    """Generates $model QC command."""
    title = "Model"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    name      = string_in(default="studio")
    mesh_file = In("FILE", enum_filter=[".dmx", ".smd"], editable=False)
    params    = DynIn("COMMAND", prefix="param")
    command   = Out("COMMAND")

    def execute(self, name: str, mesh_file: str, **kwargs):
        mesh = self.validate_file_input(mesh_file, must_exist=False)
        parts = [f'$model "{name}" "{mesh}"', "{"]
        for p in self.collect_dynamic("param", kwargs):
            parts.append(f"    {p}")
        parts.append("}")
        return ("\n".join(parts),)


class EyeballNode(BaseNode):
    """Generates eyeball parameter for $model."""
    title = "Eyeball"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    name          = string_in(default="eye")
    bone          = string_in(default="head")
    x             = float_in(default=0.0)
    y             = float_in(default=0.0)
    z             = float_in(default=0.0)
    material      = string_in(default="models/survivors/survivor_eyes")
    diameter      = float_in(default=1.0)
    angle         = float_in(default=0.0)
    iris_material = string_in(default="models/survivors/survivor_iris")
    pupil_scale   = float_in(default=1.0)
    param         = Out("COMMAND")

    def execute(self, name, bone, x, y, z, material, diameter, angle, iris_material, pupil_scale, **kwargs):
        return (f'eyeball "{name}" "{bone}" {x} {y} {z} "{material}" {diameter} {angle} "{iris_material}" {pupil_scale}',)


class EyelidNode(BaseNode):
    """Generates eyelid parameter for $model (VTA/SMD style)."""
    title = "Eyelid"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    name           = string_in(default="upper_right")
    vta_file       = In("FILE", enum_filter=[".vta"],  editable=False)
    lowerer_frame  = int_in(default=0)
    lowerer_height = float_in(default=-0.1)
    neutral_frame  = int_in(default=0)
    neutral_height = float_in(default=0.00)
    raiser_frame   = int_in(default=0)
    raiser_height  = float_in(default=0.1)
    split          = float_in(default=0.0)
    eyeball        = string_in(default="")
    param          = Out("COMMAND")

    def execute(self, name, vta_file, lowerer_frame, lowerer_height,
                neutral_frame, neutral_height, raiser_frame, raiser_height, split, eyeball, **kwargs):
        vta = self.validate_file_input(vta_file, must_exist=False)
        return (f'eyelid "{name}" "{vta}"\n'
                f'  lowerer {lowerer_frame} {lowerer_height}\n'
                f'  neutral {neutral_frame} {neutral_height}\n'
                f'  raiser {raiser_frame} {raiser_height}\n'
                f'  split {split}\n'
                f'  eyeball {eyeball}',)


class DMXEyelidNode(BaseNode):
    """Generates dmxeyelid parameter for $model (DMX style)."""
    title = "DMX Eyelid"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    lid           = enum_in(["upper", "lower"])
    dmx_file      = In("FILE", enum_filter=[".dmx"], editable=False)
    lowerer_delta = float_in(default=0.0)
    lowerer_pos   = float_in(default=-0.25)
    neutral_delta = float_in(default=0.0)
    neutral_pos   = float_in(default=0.0)
    raiser_delta  = float_in(default=0.0)
    raiser_pos    = float_in(default=0.25)
    righteyeball  = string_in(default="right_eye")
    lefteyeball   = string_in(default="left_eye")
    param         = Out("COMMAND")

    def execute(self, lid, dmx_file, lowerer_delta, lowerer_pos,
                neutral_delta, neutral_pos, raiser_delta, raiser_pos,
                righteyeball, lefteyeball, **kwargs):
        dmx = self.validate_file_input(dmx_file, must_exist=False)
        return (f'dmxeyelid {lid} "{dmx}"\n'
                f'  lowerer {lowerer_delta} {lowerer_pos}\n'
                f'  neutral {neutral_delta} {neutral_pos}\n'
                f'  raiser {raiser_delta} {raiser_pos}\n'
                f'  righteyeball "{righteyeball}"\n'
                f'  lefteyeball "{lefteyeball}"',)


class MouthNode(BaseNode):
    """Generates mouth parameter for $model."""
    title = "Mouth"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    name       = string_in(default="mouth")
    attachment = string_in(default="mouth")
    bone       = string_in(default="head")
    x          = float_in(default=0.0)
    y          = float_in(default=0.0)
    z          = float_in(default=0.0)
    param      = Out("COMMAND")

    def execute(self, name, attachment, bone, x, y, z, **kwargs):
        return (f'mouth "{name}" "{attachment}" "{bone}" {x} {y} {z}',)


class FlexControllerNode(BaseNode):
    """Generates flexcontroller parameter for $model."""
    title = "Flex Controller"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    name      = string_in(default="flex")
    flex_name = string_in(default="flex_target")
    min       = opt_float_in(default=0.0)
    max       = opt_float_in(default=1.0)
    param     = Out("COMMAND")

    def execute(self, name, flex_name, min=0.0, max=1.0, **kwargs):
        return (f'flexcontroller "{name}" range {min} {max} "{flex_name}"',)


class FlexRuleNode(BaseNode):
    """Generates flexrule block for $model."""
    title = "Flex Rule"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    name       = string_in(default="rule_name")
    expression = string_in(default="flex_a * flex_b")
    param      = Out("COMMAND")

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
    param    = Out("COMMAND")

    def execute(self, vta_file, **kwargs):
        vta = self.validate_file_input(vta_file, must_exist=False)
        parts = [f'flexfile "{vta}"', "{"]
        for p in self.collect_dynamic("param", kwargs):
            parts.append(f"    {p}")
        parts.append("}")
        return ("\n".join(parts),)


class DefaultFlexNode(BaseNode):
    """Sets a default value for a flex controller."""
    title = "Default Flex"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    name  = string_in(default="flex_name")
    value = float_in(default=1.0)
    param = Out("COMMAND")

    def execute(self, name, value, **kwargs):
        return (f'defaultflex "{name}" {value}',)


class LocalVarNode(BaseNode):
    """Defines local variables for flex rules."""
    title = "Local Var"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    names = string_in(default="var1 var2")
    param = Out("COMMAND")

    def execute(self, names, **kwargs):
        return (f'localvar {names}',)


class FlagNode(BaseNode):
    """Generates simple flags for $model."""
    title = "Model Flag"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    flag  = enum_in(["blank", "noninteract", "hidden", "no_flex_values", "noautodmxrules"],
                    allow_connection=False, full_row=True)
    param = Out("COMMAND")

    def execute(self, flag, **kwargs):
        return (flag,)


class SphereNode(BaseNode):
    """Generates sphere parameter for $model."""
    title = "Sphere"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    x      = float_in(default=0.0)
    y      = float_in(default=0.0)
    z      = float_in(default=0.0)
    radius = float_in(default=1.0)
    param  = Out("COMMAND")

    def execute(self, x, y, z, radius, **kwargs):
        return (f'sphere {x} {y} {z} {radius}',)
