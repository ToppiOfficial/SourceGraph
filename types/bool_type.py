import importlib.util, sys, os as _os

def _w(stem: str):
    key = f"_builtin_widget_{stem}"
    if key in sys.modules:
        return sys.modules[key]
    path = _os.path.join(_os.path.dirname(__file__), "widgets", f"{stem}.py")
    spec = importlib.util.spec_from_file_location(key, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod

_bw = _w("bool_widget")

_TRUE  = frozenset(("true", "1", "yes"))
_FALSE = frozenset(("false", "0", "no"))

def _coerce_text(text):
    if isinstance(text, bool):
        return text
    return str(text).lower().strip() in _TRUE

def _validate(text):
    if text.lower() not in _TRUE | _FALSE:
        return f"'{text}' is not a valid bool"
    return None

def _coerce_value(value):
    if isinstance(value, str):
        v = value.lower()
        if v in _TRUE:
            return True
        if v in _FALSE:
            return False
        raise ValueError(f"Invalid boolean: '{value}'")
    return bool(value)

from core.registry import register_port_type, PortTypeSpec
register_port_type(PortTypeSpec(
    key="bool",
    color="#ff8c00",
    editable=True,
    inspector_editable=True,
    canvas_widget_factory=_bw.make_bool_canvas_widget,
    inspector_widget_factory=_bw.make_bool_inspector_widget,
    aliases=["boolean"],
    coerce_text=_coerce_text,
    validate_text=_validate,
    coerce_value=_coerce_value,
))
