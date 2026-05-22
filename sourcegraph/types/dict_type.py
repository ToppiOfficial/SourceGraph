import json as _json
from sourcegraph.sys.registry import register_port_type, PortTypeSpec

def _coerce_value(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return _json.loads(value)
    return dict(value)

register_port_type(PortTypeSpec(
    key="dict",
    color="#ef8ed8",
    editable=False,
    inspector_editable=False,
    aliases=["object"],
    coerce_value=_coerce_value,
))
