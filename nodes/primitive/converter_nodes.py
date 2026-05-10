from __future__ import annotations
import json
import os
from core.node import BaseNode, PortType, any_in, string_in, float_in, int_in, Out

class ConverterNode:
    CATEGORY = "Converters"
    color = "#44475a"

class ToStringNode(ConverterNode, BaseNode):
    """Converts any value to a string representation."""
    title = "To String"

    value = any_in()
    string = Out("STRING")

    def execute(self, value, **kwargs):
        if value is None:
            return ("",)
        return (str(value),)

class ToIntNode(ConverterNode, BaseNode):
    """Converts a value to an integer. Handles float strings and rounding."""
    title = "To Integer"

    value = any_in()
    int_out = Out("INT")

    def execute(self, value, **kwargs):
        try:
            # Handle case where value might be a float string like "1.0"
            return (int(float(value)),)
        except (ValueError, TypeError):
            return (0,)

class ToFloatNode(ConverterNode, BaseNode):
    """Converts a value to a floating point number."""
    title = "To Float"

    value = any_in()
    float_out = Out("FLOAT")

    def execute(self, value, **kwargs):
        try:
            return (float(value),)
        except (ValueError, TypeError):
            return (0.0,)

class ToBoolNode(ConverterNode, BaseNode):
    """Converts a value to a boolean using Python's default truthiness logic."""
    title = "To Boolean"

    value = any_in()
    bool_out = Out("BOOL")

    def execute(self, value, **kwargs):
        # Python's bool() handles None as False, 0 as False, empty containers as False
        return (bool(value),)

class ToDictNode(ConverterNode, BaseNode):
    """Parses a JSON string into a dictionary object."""
    title = "To Dictionary"

    json_string = string_in(default="{}")
    dict_out = Out("DICT")

    def execute(self, json_string: str, **kwargs):
        if not json_string:
            return ({},)
        try:
            res = json.loads(json_string)
            return (res if isinstance(res, dict) else {},)
        except Exception:
            return ({},)

class ToListNode(ConverterNode, BaseNode):
    """Converts a value to a list. Parses JSON strings or wraps single items."""
    title = "To List"

    value = any_in()
    list_out = Out("ARRAY")

    def execute(self, value, **kwargs):
        if isinstance(value, str):
            try:
                res = json.loads(value)
                if isinstance(res, list):
                    return (res,)
                return ([res],)
            except Exception:
                return ([value],)
        elif isinstance(value, (list, tuple)):
            return (list(value),)
        elif value is None:
            return ([],)
        else:
            return ([value],)

class LengthNode(ConverterNode, BaseNode):
    """Returns the count of items in a list or characters in a string."""
    title = "Length"

    value = any_in()
    len_out = Out("INT")

    def execute(self, value, **kwargs):
        try:
            return (len(value),)
        except (TypeError, ValueError):
            return (0,)

class RoundNode(ConverterNode, BaseNode):
    """Rounds a number to the specified decimal places."""
    title = "Round"

    value = float_in(default=0.0)
    decimals = int_in(default=0)
    rounded = Out("FLOAT")

    def execute(self, value: float, decimals: int, **kwargs):
        try:
            res = round(float(value), int(decimals))
            # If decimals is 0, return as int for cleaner output in some contexts
            return (int(res) if decimals <= 0 else float(res),)
        except (ValueError, TypeError):
            return (0,)

class AbsoluteNode(ConverterNode, BaseNode):
    """Returns the absolute (positive) value of a number."""
    title = "Absolute"

    value = float_in(default=0.0)
    abs_out = Out("FLOAT")

    def execute(self, value: float, **kwargs):
        try:
            return (abs(float(value)),)
        except (ValueError, TypeError):
            return (0.0,)

class PathNormalizeNode(ConverterNode, BaseNode):
    """Normalizes a file path, ensuring consistent separators."""
    title = "Normalize Path"

    path = string_in(default="")
    normalized = Out("STRING")

    def execute(self, path: str, **kwargs):
        if not path:
            return ("",)
        return (os.path.normpath(str(path)).replace("\\", "/"),)
