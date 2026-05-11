from core.node import BaseNode, In, Out
from nodes.studiomdl.shared import RENDER_SETTING_CATEGORY

class MaxVerts(BaseNode):
    """Generates $maxverts QC command."""
    title = "Max Verts"
    CATEGORY = RENDER_SETTING_CATEGORY
    color = "#415a2a"

    limit = In("INT", default=65536)
    clamp = In("INT", default=65536)

    command = Out("QC_COMMAND")

    def execute(self, limit: int, clamp: int, **kwargs):
        return (f'$maxverts {limit} {clamp}',)


class MostlyOpaque(BaseNode):
    """Generates $mostlyopaque QC command."""
    title = "Mostly Opaque"
    CATEGORY = RENDER_SETTING_CATEGORY
    color = "#415a2a"

    command = Out("QC_COMMAND")

    def execute(self, **kwargs):
        return ('$mostlyopaque',)


class Opaque(BaseNode):
    """Generates $opaque QC command."""
    title = "Opaque"
    CATEGORY = RENDER_SETTING_CATEGORY
    color = "#415a2a"

    command = Out("QC_COMMAND")

    def execute(self, **kwargs):
        return ('$opaque',)


class AmbientBoost(BaseNode):
    """Generates $ambientboost QC command."""
    title = "Ambient Boost"
    CATEGORY = RENDER_SETTING_CATEGORY
    color = "#415a2a"

    command = Out("QC_COMMAND")

    def execute(self, **kwargs):
        return ('$ambientboost',)


class StaticProp(BaseNode):
    """Generates $staticprop QC command."""
    title = "Static Prop"
    CATEGORY = RENDER_SETTING_CATEGORY
    color = "#415a2a"

    command = Out("QC_COMMAND")

    def execute(self, **kwargs):
        return ('$staticprop',)
