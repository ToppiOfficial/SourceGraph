from core.node import BaseNode


class MaxVerts(BaseNode):
    """Generates $maxverts QC command."""
    title = "Max Verts"
    CATEGORY = "QC"
    color = "#415a2a"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "limit": ("INT", {"default": 65536}),
                "clamp": ("INT", {"default": 65536}),
            }
        }

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, limit: int, clamp: int, **kwargs):
        return (f'$maxverts {limit} {clamp}',)


class MostlyOpaque(BaseNode):
    """Generates $mostlyopaque QC command."""
    title = "Mostly Opaque"
    CATEGORY = "QC"
    color = "#415a2a"

    @classmethod
    def INPUT_TYPES(cls):
        return {}

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, **kwargs):
        return ('$mostlyopaque',)


class Opaque(BaseNode):
    """Generates $opaque QC command."""
    title = "Opaque"
    CATEGORY = "QC"
    color = "#415a2a"

    @classmethod
    def INPUT_TYPES(cls):
        return {}

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, **kwargs):
        return ('$opaque',)


class AmbientBoost(BaseNode):
    """Generates $ambientboost QC command."""
    title = "Ambient Boost"
    CATEGORY = "QC"
    color = "#415a2a"

    @classmethod
    def INPUT_TYPES(cls):
        return {}

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, **kwargs):
        return ('$ambientboost',)


class StaticProp(BaseNode):
    """Generates $staticprop QC command."""
    title = "Static Prop"
    CATEGORY = "QC"
    color = "#415a2a"

    @classmethod
    def INPUT_TYPES(cls):
        return {}

    RETURN_TYPES = ("COMMAND",)
    RETURN_NAMES = ("command",)

    def execute(self, **kwargs):
        return ('$staticprop',)