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

_fw = _w("file_widget")

from sourcegraph.sys.registry import register_port_type, PortTypeSpec
register_port_type(PortTypeSpec(
    key="file",
    color="#ce9178",
    editable=True,
    inspector_editable=True,
    canvas_widget_factory=_fw.make_file_canvas_widget,
    inspector_widget_factory=_fw.make_file_inspector_widget,
    aliases=["path"],
))
