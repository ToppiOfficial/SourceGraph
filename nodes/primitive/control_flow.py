from __future__ import annotations
from typing import Any
from core.node import BaseNode, In, any_in, bool_in, string_in, DynIn, Out


class IfElseNode(BaseNode):
    """Returns one of two values based on a boolean condition."""
    title = "If/Else"
    CATEGORY = "Conditional"
    color = "#ffb86c"

    if_true = any_in(editable=False)
    if_false = any_in(editable=False)
    condition = bool_in(default=False)
    output = Out("*")

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

    formula = string_in(default='input_1 == "value"')
    input = DynIn(prefix="input")
    result = Out("BOOL")

    def execute(self, formula: str, **kwargs):
        if not formula:
            return (False,)

        formula = formula.replace("||", " or ").replace("&&", " and ")
        inputs = self.collect_dynamic("input", kwargs)
        context = {f"input_{i+1}": v for i, v in enumerate(inputs)}

        try:
            res = eval(formula, {"__builtins__": {}}, context)
            return (bool(res),)
        except Exception as e:
            self.fail(f"Formula Error: {e}")


class CaseNode(BaseNode):
    """
    Selects a value from an input array based on which dynamic case input matches the selector.
    Case 1 matches array index 0, Case 2 matches index 1, etc.
    """
    title = "Switch Case"
    CATEGORY = "Conditional"
    color = "#ffb86c"

    values = In("ARRAY")
    selector = any_in()
    default = any_in()
    case = DynIn("*", prefix="case", editable=False)
    result = Out("*")

    def execute(self, values: list, selector: Any, default: Any = None, **kwargs):
        if not isinstance(values, (list, tuple)):
            return (default,)

        i = 1
        while True:
            case_key = f"case{i}"
            if case_key not in kwargs:
                break
            
            if kwargs[case_key] == selector:
                idx = i - 1
                if 0 <= idx < len(values):
                    return (values[idx],)
                break
            
            i += 1
            
        return (default,)


class NOTNode(BaseNode):
    """Logical NOT: returns the negation of the input. Accepts any type, truthy/falsy conversion."""
    title = "NOT"
    CATEGORY = "Logic"
    color = "#8be9fd"

    input = any_in(editable=False)
    output = Out("BOOL")

    def execute(self, input, **kwargs):
        return (not bool(input),)


class ANDNode(BaseNode):
    """Logical AND: returns True if all inputs are truthy. Accepts any type."""
    title = "AND"
    CATEGORY = "Logic"
    color = "#8be9fd"

    input = DynIn("*", prefix="input", editable=False)
    output = Out("BOOL")

    def execute(self, **kwargs):
        values = list(self.collect_dynamic("input", kwargs))
        if not values:
            return (True,)
        return (all(bool(v) for v in values),)


class ORNode(BaseNode):
    """Logical OR: returns True if any input is truthy. Accepts any type."""
    title = "OR"
    CATEGORY = "Logic"
    color = "#8be9fd"

    input = DynIn("*", prefix="input", editable=False)
    output = Out("BOOL")

    def execute(self, **kwargs):
        values = list(self.collect_dynamic("input", kwargs))
        if not values:
            return (False,)
        return (any(bool(v) for v in values),)


class XORNode(BaseNode):
    """Logical XOR: returns True if exactly one input is truthy. Accepts any type."""
    title = "XOR"
    CATEGORY = "Logic"
    color = "#8be9fd"

    input_a = any_in(editable=False)
    input_b = any_in(editable=False)
    output = Out("BOOL")

    def execute(self, input_a, input_b, **kwargs):
        a = bool(input_a) if input_a is not None else False
        b = bool(input_b) if input_b is not None else False
        return (a != b,)


class XNORNode(BaseNode):
    """Logical XNOR: returns True if inputs have the same truthiness. Accepts any type."""
    title = "XNOR"
    CATEGORY = "Logic"
    color = "#8be9fd"

    input_a = any_in(editable=False)
    input_b = any_in(editable=False)
    output = Out("BOOL")

    def execute(self, input_a, input_b, **kwargs):
        a = bool(input_a) if input_a is not None else False
        b = bool(input_b) if input_b is not None else False
        return (a == b,)


class NANDNode(BaseNode):
    """Logical NAND: returns False if all inputs are truthy. Accepts any type."""
    title = "NAND"
    CATEGORY = "Logic"
    color = "#8be9fd"

    input = DynIn("*", prefix="input", editable=False)
    output = Out("BOOL")

    def execute(self, **kwargs):
        values = list(self.collect_dynamic("input", kwargs))
        if not values:
            return (True,)
        return (not all(bool(v) for v in values),)


class NORNode(BaseNode):
    """Logical NOR: returns True if all inputs are falsy. Accepts any type."""
    title = "NOR"
    CATEGORY = "Logic"
    color = "#8be9fd"

    input = DynIn("*", prefix="input", editable=False)
    output = Out("BOOL")

    def execute(self, **kwargs):
        values = list(self.collect_dynamic("input", kwargs))
        if not values:
            return (True,)
        return (not any(bool(v) for v in values),)