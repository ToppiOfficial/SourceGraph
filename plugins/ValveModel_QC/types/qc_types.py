from core.port_type_registry import register_port_type, PortTypeSpec

register_port_type(PortTypeSpec(
    key="qc_command",
    color="#dcdcaa",
    editable=False,
    aliases=["command"],
))
