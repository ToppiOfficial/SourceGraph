from sourcegraph.sys.registry import register_port_type, PortTypeSpec

def _coerce_value(value):
    return value if isinstance(value, list) else [value]

register_port_type(PortTypeSpec(
    key="array",
    color="#bd93f9",
    editable=False,
    inspector_editable=False,
    aliases=["list"],
    coerce_value=_coerce_value,
))
