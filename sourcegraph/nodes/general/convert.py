from __future__ import annotations
import json
import os
import re
from sourcegraph.sys.node import BaseNode, In, Out, OptIn, DynIn

class ConverterNode:
    CATEGORY = "Converters"
    color = "#44475a"

class ToStringNode(ConverterNode, BaseNode):
    """Converts any value to a string representation."""
    title = "To String"

    value = OptIn("ANY")
    string = Out("STRING")

    def execute(self, value, **kwargs):
        if value is None:
            return ("",)
        return (str(value),)


class ToIntNode(ConverterNode, BaseNode):
    """Converts a value to an integer. Handles float strings and rounding."""
    title = "To Integer"

    value = OptIn("ANY")
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

    value = OptIn("ANY")
    float_out = Out("FLOAT")

    def execute(self, value, **kwargs):
        try:
            return (float(value),)
        except (ValueError, TypeError):
            return (0.0,)


class ToBoolNode(ConverterNode, BaseNode):
    """Converts a value to a boolean using Python's default truthiness logic."""
    title = "To Boolean"

    value = OptIn("ANY")
    bool_out = Out("BOOL")

    def execute(self, value, **kwargs):
        # Python's bool() handles None as False, 0 as False, empty containers as False
        return (bool(value),)


class ToDictNode(ConverterNode, BaseNode):
    """Parses a JSON string into a dictionary object."""
    title = "To Dictionary"

    json_string = In("STRING", default="{}")
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

    value = OptIn("ANY")
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

    value = OptIn("ANY")
    len_out = Out("INT")

    def execute(self, value, **kwargs):
        try:
            return (len(value),)
        except (TypeError, ValueError):
            return (0,)


class RoundNode(ConverterNode, BaseNode):
    """Rounds a number to the specified decimal places."""
    title = "Round"

    value = In("FLOAT", default=0.0)
    decimals = In("INT", default=0)
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

    value = In("FLOAT", default=0.0)
    abs_out = Out("FLOAT")

    def execute(self, value: float, **kwargs):
        try:
            return (abs(float(value)),)
        except (ValueError, TypeError):
            return (0.0,)


class PathNormalizeNode(ConverterNode, BaseNode):
    """Normalizes a file path, ensuring consistent separators."""
    title = "Normalize Path"

    path = In("STRING", default="")
    normalized = Out("STRING")

    def execute(self, path: str, **kwargs):
        if not path:
            return ("",)
        return (os.path.normpath(str(path)).replace("\\", "/"),)


class StringSplitNode(ConverterNode, BaseNode):
    """Splits a string into a list using a specified separator."""
    title = "String Split"

    text = In("STRING", default="")
    separator = In("STRING", default=",")
    list_out = Out("ARRAY")

    def execute(self, text: str, separator: str, **kwargs):
        if not text:
            return ([],)
        if not separator:
            return (text.split(),)
        return (text.split(separator),)


class RegexMatchNode(ConverterNode, BaseNode):
    """Finds all occurrences of a regex pattern in a string."""
    title = "Regex Match"

    text = In("STRING", default="")
    pattern = In("STRING", default="")
    matches = Out("ARRAY")

    def execute(self, text: str, pattern: str, **kwargs):
        if not pattern or not text:
            return ([],)
        try:
            res = re.findall(pattern, text)
            return (res,)
        except re.error:
            return ([],)


class RegexReplaceNode(ConverterNode, BaseNode):
    """Replaces occurrences of a regex pattern with a replacement string."""
    title = "Regex Replace"

    text = In("STRING", default="")
    pattern = In("STRING", default="")
    replacement = In("STRING", default="")
    text_out = Out("STRING")

    def execute(self, text: str, pattern: str, replacement: str, **kwargs):
        if not pattern:
            return (text,)
        try:
            res = re.sub(pattern, replacement, text)
            return (res,)
        except re.error:
            return (text,)


class ConcatenateStrings(BaseNode):
    title = "Concatenate String"
    CATEGORY = "Primitives"
    color = "#4ec9b0"

    separator = OptIn("STRING", default="")
    items = DynIn(prefix="item", editable=False)
    output = Out("STRING")

    def execute(self, separator: str, **kwargs):
        items = []
        items.extend(self.collect_dynamic("item", kwargs))
        sep = separator.replace("\\n", "\n")
        return (sep.join(str(i) for i in items),)