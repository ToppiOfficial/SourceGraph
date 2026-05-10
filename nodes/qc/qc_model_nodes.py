from __future__ import annotations
from core.node import BaseNode
from nodes.qc.shared_categories import QC_CATEGORY, MODEL_PARAMETER_CATEGORY

class ModelNode(BaseNode):
    """Generates $model QC command."""
    title = "Model"
    CATEGORY = QC_CATEGORY
    color = "#2a5a3a"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "studio"}),
                "mesh_file": ("FILE", {"enum_filter": [".dmx", ".smd"]}),
            },
            "optional": {
                "param{n}": ("COMMAND", {"dynamic": True}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, name: str, mesh_file: str, **kwargs):
        mesh = self.validate_file_input(mesh_file, must_exist=False)
        parts = [f'$model "{name}" "{mesh}"', "{"]
        
        # Add dynamic parameters
        for k, v in kwargs.items():
            if k.startswith("param") and k[5:].isdigit() and v:
                parts.append(f"    {v}")
            
        parts.append("}")
        return ("\n".join(parts),)

class EyeballNode(BaseNode):
    """
    Generates eyeball parameter for $model.
    Syntax: eyeball <name> <bone> <X> <Y> <Z> <material> <diameter> <angle> <iris_material> <pupil_scale>
    """
    title = "Eyeball"
    CATEGORY = MODEL_PARAMETER_CATEGORY
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "eye"}),
                "bone": ("STRING", {"default": "head"}),
                "x": ("FLOAT", {"default": 0.0}),
                "y": ("FLOAT", {"default": 0.0}),
                "z": ("FLOAT", {"default": 0.0}),
                "material": ("STRING", {"default": "models/survivors/survivor_eyes"}),
                "diameter": ("FLOAT", {"default": 1.0}),
                "angle": ("FLOAT", {"default": 0.0}),
                "iris_material": ("STRING", {"default": "models/survivors/survivor_iris"}),
                "pupil_scale": ("FLOAT", {"default": 1.0}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("param",)

    def execute(self, name, bone, x, y, z, material, diameter, angle, iris_material, pupil_scale, **kwargs):
        return (f'eyeball "{name}" "{bone}" {x} {y} {z} "{material}" {diameter} {angle} "{iris_material}" {pupil_scale}',)

class EyelidNode(BaseNode):
    """
    Generates eyelid parameter for $model (VTA/SMD style).
    """
    title = "Eyelid"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "upper_right"}),
                "vta_file": ("FILE", {"enum_filter": [".vta", ".smd"]}),
                "lowerer_frame": ("INT", {"default": 0}),
                "lowerer_height": ("FLOAT", {"default": -0.1}),
                "neutral_frame": ("INT", {"default": 0}),
                "neutral_height": ("FLOAT", {"default": 0.00}),
                "raiser_frame": ("INT", {"default": 0}),
                "raiser_height": ("FLOAT", {"default": 0.1}),
                "split": ("FLOAT", {"default": 0.0}),
                "eyeball": ("STRING", {"default": ""}),
            },
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("param",)

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
    """
    Generates dmxeyelid parameter for $model (DMX style).
    Syntax: dmxeyelid <upper|lower> <DMX File>
              lowerer <delta> <pos>
              neutral <delta> <pos>
              raiser <delta> <pos>
              righteyeball <righteye>
              lefteyeball <lefteye>
    """
    title = "DMX Eyelid"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "lid": ("ENUM", {"enum_options": ["upper", "lower"]}),
                "dmx_file": ("FILE", {"enum_filter": [".dmx"]}),
                "lowerer_delta": ("FLOAT", {"default": 0.0}),
                "lowerer_pos": ("FLOAT", {"default": -0.25}),
                "neutral_delta": ("FLOAT", {"default": 0.0}),
                "neutral_pos": ("FLOAT", {"default": 0.0}),
                "raiser_delta": ("FLOAT", {"default": 0.0}),
                "raiser_pos": ("FLOAT", {"default": 0.25}),
                "righteyeball": ("STRING", {"default": "right_eye"}),
                "lefteyeball": ("STRING", {"default": "left_eye"}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("param",)

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
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "mouth"}),
                "attachment": ("STRING", {"default": "mouth"}),
                "bone": ("STRING", {"default": "head"}),
                "x": ("FLOAT", {"default": 0.0}),
                "y": ("FLOAT", {"default": 0.0}),
                "z": ("FLOAT", {"default": 0.0}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("param",)

    def execute(self, name, attachment, bone, x, y, z, **kwargs):
        return (f'mouth "{name}" "{attachment}" "{bone}" {x} {y} {z}',)

class FlexControllerNode(BaseNode):
    """Generates flexcontroller parameter for $model."""
    title = "Flex Controller"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "flex"}),
                "flex_name": ("STRING", {"default": "flex_target"}),
            },
            "optional": {
                "min": ("FLOAT", {"default": 0.0}),
                "max": ("FLOAT", {"default": 1.0}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("param",)

    def execute(self, name, flex_name, min=0.0, max=1.0, **kwargs):
        return (f'flexcontroller "{name}" range {min} {max} "{flex_name}"',)

class FlexRuleNode(BaseNode):
    """Generates flexrule block for $model."""
    title = "Flex Rule"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "rule_name"}),
                "expression": ("STRING", {"default": "flex_a * flex_b"}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("param",)

    def execute(self, name, expression, **kwargs):
        return (f'flexrule "{name}"\n'
                f'{{\n'
                f'  {expression}\n'
                f'}}',)

class FlexFileNode(BaseNode):
    """Generates flexfile parameter for $model (VTA morph targets)."""
    title = "Flex File"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "vta_file": ("FILE", {"enum_filter": [".vta"]}),
            },
            "optional": {
                "param{n}": ("COMMAND", {"dynamic": True}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("param",)

    def execute(self, vta_file, **kwargs):
        vta = self.validate_file_input(vta_file, must_exist=False)
        parts = [f'flexfile "{vta}"', "{"]

        for k, v in kwargs.items():
            if k.startswith("param") and k[5:].isdigit() and v:
                parts.append(f"    {v}")

        parts.append("}")
        return ("\n".join(parts),)

class DefaultFlexNode(BaseNode):
    """Sets a default value for a flex controller."""
    title = "Default Flex"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "name": ("STRING", {"default": "flex_name"}),
                "value": ("FLOAT", {"default": 1.0}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("param",)

    def execute(self, name, value, **kwargs):
        return (f'defaultflex "{name}" {value}',)

class LocalVarNode(BaseNode):
    """Defines local variables for flex rules."""
    title = "Local Var"
    CATEGORY = MODEL_PARAMETER_CATEGORY

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "names": ("STRING", {"default": "var1 var2"}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("param",)

    def execute(self, names, **kwargs):
        return (f'localvar {names}',)

class FlagNode(BaseNode):
    """Generates simple flags for $model."""
    title = "Model Flag"
    CATEGORY = MODEL_PARAMETER_CATEGORY
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "flag": ("ENUM",{"enum_options": ["blank", "noninteract", "hidden", "no_flex_values", "noautodmxrules"],
                                 "allow_connection": False,"full_row": True}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("param",)

    def execute(self, flag, **kwargs):
        return (flag,)

class SphereNode(BaseNode):
    """Generates sphere parameter for $model."""
    title = "Sphere"
    CATEGORY = MODEL_PARAMETER_CATEGORY
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "x": ("FLOAT", {"default": 0.0}),
                "y": ("FLOAT", {"default": 0.0}),
                "z": ("FLOAT", {"default": 0.0}),
                "radius": ("FLOAT", {"default": 1.0}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("param",)

    def execute(self, x, y, z, radius, **kwargs):
        return (f'sphere {x} {y} {z} {radius}',)
