from sourcegraph.sys.registry import register_port_type, PortTypeSpec

register_port_type(PortTypeSpec(
    key="signal",
    color="#f1fa8c",
    editable=False,
    inspector_editable=False,
    aliases=["flow"],
))
