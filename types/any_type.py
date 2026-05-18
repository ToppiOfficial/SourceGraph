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

_sw = _w("string_widget")

from core.registry import register_port_type, PortTypeSpec
register_port_type(PortTypeSpec(
    key="any",
    color="#aaaaaa",
    editable=True,
    inspector_editable=False,
    canvas_widget_factory=_sw.make_string_canvas_widget,
    aliases=["*"],
))
