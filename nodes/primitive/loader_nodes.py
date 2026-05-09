from __future__ import annotations
import os
from core.node import BaseNode


class ModelFileNode(BaseNode):
    """Picks a project asset (.dmx / .smd)."""
    title = "Model File"
    CATEGORY = "Primitives"
    color = "#ce9178"
    locked_title = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "asset": ("ENUM", {
                    "default": "",
                    "visible": False,
                    "enum_filter": [".dmx", ".smd"],
                    "graph_enum": "assets",
                }),
            }
        }

    RETURN_TYPES = ("FILE",)
    RETURN_NAMES = ("file",)

    def on_property_changed(self):
        input_port = self.inputs.get("asset")
        raw_path = input_port.value if input_port else ""

        self.error_msg = None
        if raw_path:
            resolved_path = self.resolve_path(raw_path)
            if not os.path.exists(resolved_path):
                self.error_msg = f"File missing: {os.path.basename(raw_path)}"
            
            # Use relative path for display if it resides within the project
            display_path = raw_path
            if self.graph and self.graph.file_path:
                try:
                    rel = os.path.relpath(resolved_path, self.graph.file_path.parent).replace("\\", "/")
                    if not rel.startswith(".."):
                        display_path = rel
                except (ValueError, TypeError):
                    pass
            
            self.title = os.path.basename(display_path)
            self.outputs["file"].label = display_path
        else:
            self.title = "Model File"
            self.outputs["file"].label = ""

    def execute(self, asset: str, **kwargs):
        path = self.validate_file_input(asset, must_exist=True)
        return (path,)


class VariableOutNode(BaseNode):
    """Outputs graph.variables[var_name]."""
    title = "Get Variable"
    CATEGORY = "General"
    color = "#b4629d"
    locked_title = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "var_name": ("ENUM", {
                    "default": "",
                    "visible": False,
                    "graph_enum": "variables",
                    "label": "variable",
                }),
            }
        }

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("value",)

    def get_reads(self) -> set[str]:
        p = self.inputs.get("var_name")
        return {f"var:{p.value}"} if p and p.value else set()

    def on_property_changed(self):
        port = self.inputs.get("var_name")
        # Update title to clearly indicate it's a GET node
        var_name = str(port.value) if port and port.value else "..."
        self.title = f"GET {var_name}"

    def execute(self, var_name: str, **kwargs):
        val = None
        if self.graph and var_name:
            val = self.graph.variables.get(var_name)
        if val is None or (isinstance(val, str) and not val.strip()):
            self.fail(f"Variable '{var_name}' is empty or unset")
        return (val,)


class VariableInNode(BaseNode):
    """Writes new_value into graph.variables[var_name] during execution."""
    title = "Set Variable"
    CATEGORY = "General"
    color = "#b4629d"
    locked_title = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "var_name": ("ENUM", {
                    "default": "",
                    "visible": False,
                    "graph_enum": "variables",
                    "label": "variable",
                }),
            },
            "optional": {
                "new_value": ("*", {}),
            }
        }

    RETURN_TYPES = ()

    def get_writes(self) -> set[str]:
        p = self.inputs.get("var_name")
        return {f"var:{p.value}"} if p and p.value else set()

    def on_property_changed(self):
        port = self.inputs.get("var_name")
        var_name = str(port.value) if port and port.value else "..."
        self.title = f"SET {var_name}"

    def execute(self, var_name: str, **kwargs):
        new_value = kwargs.get("new_value")
        if self.graph and var_name and var_name in self.graph.variables:
            # Only update if a non-empty value was actually provided via connection or widget
            if new_value is not None and (not isinstance(new_value, str) or new_value.strip()):
                self.graph.variables[var_name] = new_value
        return {}