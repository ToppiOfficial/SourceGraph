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

_nw = _w("number_widget")

def _validate(text):
    try:
        float(text)
        return None
    except ValueError:
        return f"'{text}' is not a valid float"

from core.port_type_registry import register_port_type, PortTypeSpec
register_port_type(PortTypeSpec(
    key="float",
    color="#9cdcfe",
    editable=True,
    inspector_editable=True,
    canvas_widget_factory=_nw.make_number_canvas_widget,
    inspector_widget_factory=_nw.make_number_inspector_widget,
    aliases=["number"],
    coerce_text=float,
    validate_text=_validate,
    coerce_value=float,
    values_equal=lambda cur, txt: abs(float(cur or 0) - float(txt or 0)) < 1e-7,
))
