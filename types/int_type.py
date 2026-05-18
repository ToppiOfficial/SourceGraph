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
        int(text)
        return None
    except ValueError:
        return f"'{text}' is not a valid int"

from core.registry import register_port_type, PortTypeSpec
register_port_type(PortTypeSpec(
    key="int",
    color="#569cd6",
    editable=True,
    inspector_editable=True,
    canvas_widget_factory=_nw.make_number_canvas_widget,
    inspector_widget_factory=_nw.make_number_inspector_widget,
    coerce_text=int,
    validate_text=_validate,
    coerce_value=int,
    values_equal=lambda cur, txt: int(cur or 0) == int(txt or 0),
))
