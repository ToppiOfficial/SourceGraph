from __future__ import annotations
from core.node import BaseNode, In, OptIn, Out, DynIn


class StringNode(BaseNode):
    title = "String"
    CATEGORY = "Primitives"
    color = "#4ec9b0"

    value = OptIn("STRING", default="", allow_connection=False, editable=True, full_row=True)
    out   = Out("STRING")

    def execute(self, value="", **kwargs):
        return (value,)

    def on_property_changed(self):
        self.outputs["out"].label = str(self.inputs["value"].value or "...")


class IntNode(BaseNode):
    title = "Integer"
    CATEGORY = "Primitives"
    color = "#569cd6"

    value = In("INT", default=0, allow_connection=False)
    out   = Out("INT")

    def execute(self, value=0, **kwargs):
        return (value,)

    def on_property_changed(self):
        self.outputs["out"].label = str(self.inputs["value"].value)


class FloatNode(BaseNode):
    title = "Float"
    CATEGORY = "Primitives"
    color = "#9cdcfe"

    value = In("FLOAT", default=0.0, allow_connection=False)
    out   = Out("FLOAT")

    def execute(self, value=0.0, **kwargs):
        return (value,)

    def on_property_changed(self):
        raw = self.inputs["value"].value
        try:
            self.outputs["out"].label = f"{float(raw):.2f}"
        except (ValueError, TypeError):
            self.outputs["out"].label = str(raw)


class BoolNode(BaseNode):
    title = "Boolean"
    CATEGORY = "Primitives"
    color = "#ff8c00"

    value = In("BOOL", default=False, allow_connection=False)
    out   = Out("BOOL")

    def execute(self, value=False, **kwargs):
        return (value,)

    def on_property_changed(self):
        self.outputs["out"].label = str(self.inputs["value"].value).upper()


class JoinToArrayNode(BaseNode):
    title = "Create List"
    CATEGORY = "Primitives"
    color = "#44475a"

    items = DynIn(prefix="item")
    array = Out("ARRAY")

    def execute(self, **kwargs):
        return (self.collect_dynamic("item", kwargs),)


class GetItemNode(BaseNode):
    title = "Get Item"
    CATEGORY = "Primitives"
    color = "#44475a"

    array = In("ARRAY")
    index = In("INT", default=0)
    item  = Out("ANY")

    def execute(self, array: list, index: int = 0, **kwargs):
        if isinstance(array, list) and 0 <= index < len(array):
            return (array[index],)
        return (None,)


class PrintNode(BaseNode):
    title = "Print"
    CATEGORY = "General"
    color = "#6272a4"
    default_width = 200

    value       = OptIn("ANY", full_row=True, row_height=100, row_stretch=True, below_ports=True)
    passthrough = Out("ANY")

    def __init__(self):
        super().__init__()
        self._output_buffer: list[str] = []
        self._max_lines = 512
        self._display_widgets: list = []  # track all live widgets, not just one

    @property
    def output_text(self) -> str:
        return "\n".join(self._output_buffer[-self._max_lines:])

    def execute(self, value=None, **kwargs):
        self._output_buffer.clear()
        self._output_buffer.append(f"{value}")
        self.sync_presentation()
        return (value,)

    def sync_presentation(self) -> None:
        live = []
        for w in self._display_widgets:
            try:
                w.setPlainText(self.output_text)
                live.append(w)
            except RuntimeError:
                pass
        self._display_widgets = live

    def _register_gui_builders(self) -> None:
        super()._register_gui_builders()

        def create_print_display(port):
            from gui.widgets.node_widgets import make_text_display
            display = make_text_display()
            self._display_widgets.append(display)
            display.setPlainText(self.output_text)
            return display

        self.register_gui_builder("value", create_print_display)