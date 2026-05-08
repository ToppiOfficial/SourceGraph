from __future__ import annotations
from core.node import BaseNode
from pathlib import Path


class PrimitiveNode:
    CATEGORY = "Primitives"
    def execute(self, value, **kwargs):
        self._value = value
        return (value,)
    
    def get_value(self): return None


class StringNode(PrimitiveNode, BaseNode):
    title = "String"
    color = "#4ec9b0"
    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("out",)
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "optional": {
                "value": ("STRING", {"default": "", "allow_connection": False}),
            }
        }
    
    def __init__(self):
        super().__init__()
        self._value = ""
    
    def get_value(self):
        return self._value
    
    def on_property_changed(self):
        value = self.inputs["value"].value if "value" in self.inputs else self._value
        self.outputs["out"].label = str(value or "...")
    

class IntNode(PrimitiveNode, BaseNode):
    title = "Integer"
    color = "#569cd6"
    RETURN_TYPES = ("INT",)
    RETURN_NAMES = ("out",)
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "value": ("INT", {"default": 0, "allow_connection": False}),
            }
        }
    
    def __init__(self):
        super().__init__()
        self._value = 0
    
    def get_value(self):
        return self._value
    
    def on_property_changed(self):
        value = self.inputs["value"].value if "value" in self.inputs else self._value
        self.outputs["out"].label = str(value)
    
    
class FloatNode(PrimitiveNode, BaseNode):
    title = "Float"
    color = "#9cdcfe"
    RETURN_TYPES = ("FLOAT",)
    RETURN_NAMES = ("out",)
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "value": ("FLOAT", {"default": 0.0, "allow_connection": False}),
            }
        }
    
    def __init__(self):
        super().__init__()
        self._value = 0.0
    
    def get_value(self):
        return self._value
    
    def on_property_changed(self):
        value = self.inputs["value"].value if "value" in self.inputs else self._value
        try:
            self.outputs["out"].label = f"{float(value):.2f}"
        except (ValueError, TypeError):
            self.outputs["out"].label = str(value)
    
    
class BoolNode(PrimitiveNode, BaseNode):
    title = "Boolean"
    color = "#ff8c00"
    RETURN_TYPES = ("BOOL",)
    RETURN_NAMES = ("out",)
    
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "value": ("BOOL", {"default": False, "allow_connection": False}),
            }
        }
    
    def __init__(self):
        super().__init__()
        self._value = False
    
    def get_value(self):
        return self._value
    
    def on_property_changed(self):
        value = self.inputs["value"].value if "value" in self.inputs else self._value
        self.outputs["out"].label = str(value).upper()


class JoinToArrayNode(BaseNode):
    title = "Create List"
    CATEGORY = "Primitives"
    color = "#44475a"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "optional": {
                "item{n}": ("*", {"dynamic": True}),
            }
        }

    RETURN_TYPES = ("ARRAY",)
    RETURN_NAMES = ("array",)

    def execute(self, **kwargs):
        items = []
        for k, v in kwargs.items():
            if k.startswith("item") and k[4:].isdigit():
                items.append(v)
        return (items,)


class PrintNode(BaseNode):
    title = "Print"
    CATEGORY = "Primitives"
    color = "#6272a4"

    def __init__(self):
        super().__init__()
        self._output_buffer = []
        self._max_lines = 10
        self._display_widget = None
        
        self.configure_custom_widget(height=30, below_ports=True, full_width=True)
        self.width = 200

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "optional": {
                "value": ("*", {"visible": True, "allow_connection": True}),
            },
        }

    @property
    def output_text(self):
        """Get the current output text for display."""
        return "\n".join(self._output_buffer[-self._max_lines:])

    def execute(self, value=None, **kwargs):
        text = str(value) if value is not None else ""
        print(text)
        self._output_buffer.clear()
        self._output_buffer.append(text)
        return text
    
    def sync_presentation(self) -> None:
        """Override to trigger GUI updates when output text changes."""
        if self._display_widget: self._display_widget.setPlainText(self.output_text)
    
    def _register_gui_builders(self) -> None:
        """Register GUI builders for this node using the self-registration system."""
        super()._register_gui_builders()
        
        def create_print_display(port, parent=None):
            from PySide6.QtWidgets import QTextEdit
            
            display = QTextEdit()
            display.setReadOnly(True)
            display.setStyleSheet(f"""
                QTextEdit {{
                    background-color: #111111;
                    color: #f0f0f0;
                    border: 1px solid #444444;
                    border-radius: 3px;
                    padding: 4px;
                    font-family: 'Consolas', 'Monaco', monospace;
                    font-size: 10px;
                }}
                QTextEdit:focus {{
                    border: 1px solid #63c2df;
                }}
            """)
            
            self._display_widget = display
            if hasattr(self, 'output_text'):
                display.setPlainText(self.output_text)
            return display
        
        self.register_gui_builder("value", create_print_display)


class GetItemNode(BaseNode):
    title = "Get Item"
    CATEGORY = "Primitives"
    color = "#44475a"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "array": ("ARRAY", {}),
                "index": ("INT", {"default": 0}),
            }
        }

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("item",)

    def execute(self, array: list, index: int = 0, **kwargs):
        if isinstance(array, list) and 0 <= index < len(array):
            return (array[index],)
        return (None,)


class OutputToFileNode(BaseNode):
    title = "Save To File"
    CATEGORY = "QC"
    color = "#7a2d2d"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "content": ("*", {}),
                "out_path": ("STRING", {"default": "output.qc"}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)

    def execute(self, content, out_path: str, **kwargs):
        try:
            Path(out_path).write_text(str(content), encoding="utf-8")
            return (f"Written → {out_path}",)
        except Exception as exc:
            return (f"Error: {exc}",)