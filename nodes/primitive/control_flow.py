from __future__ import annotations
from core.node import BaseNode


class IfElseNode(BaseNode):
    """Returns one of two values based on a boolean condition."""
    title = "If/Else"
    CATEGORY = "Conditional"
    color = "#ffb86c"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "if_true": ("*", {}),
                "if_false": ("*", {}),
                "condition": ("BOOL", {"default": False}),
            }
        }

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("output",)

    def execute(self, if_true, if_false, condition: bool, **kwargs):
        return (if_true if condition else if_false,)


class FormulaIfNode(BaseNode):
    """
    Evaluates a custom formula against dynamic inputs.
    Example: (input_1 == 'bill' || input_1 == 'francis')
    """
    title = "Formula Check"
    CATEGORY = "Conditional"
    color = "#ffb86c"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "formula": ("STRING", {"default": 'input_1 == "value"'}),
            },
            "optional": {
                "input_{n}": ("*", {"dynamic": True}),
            }
        }

    RETURN_TYPES = ("BOOL",)
    RETURN_NAMES = ("result",)

    def execute(self, formula: str, **kwargs):
        if not formula:
            return (False,)

        formula = formula.replace("||", " or ").replace("&&", " and ")
        
        context = {}
        for k, v in kwargs.items():
            if k.startswith("input_") and k[6:].isdigit():
                context[k] = v

        try:
            res = eval(formula, {"__builtins__": {}}, context)
            return (bool(res),)
        except Exception as e:
            self.fail(f"Formula Error: {e}")


class CaseNode(BaseNode):
    """Selects an output based on an index or selector value."""
    title = "Switch Case"
    CATEGORY = "Conditional"
    color = "#ffb86c"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "selector": ("*", {}),
            },
            "optional": {
                "default": ("*", {}),
                "option{n}": ("*", {"dynamic": True}),
            }
        }

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("result",)

    def execute(self, selector, default=None, **kwargs):
        # Try to match by index
        target_key = f"option{selector}"
        if target_key in kwargs:
            return (kwargs[target_key],)
        return (default,)