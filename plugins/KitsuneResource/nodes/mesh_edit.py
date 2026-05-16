import sys
from pathlib import Path

_LIBS = str(Path(__file__).parent.parent / "libs")
if _LIBS not in sys.path:
    sys.path.insert(0, _LIBS)

import mesh_edit as _mesh_edit_lib
from core.node import BaseNode, In, OptIn, DynIn, Out


class MeshEditNode(BaseNode):
    title    = "Mesh Edit"
    CATEGORY = "KitsuneResource"
    color    = "#e06c75"

    dmx_file = In("FILE", label="DMX File")
    mode     = In("ENUM", enum_options=["removemesh", "keeponlymesh"], default="removemesh", label="Mode", allow_connection=False,full_row=True)
    mesh     = DynIn("STRING", prefix="mesh")

    file = Out("FILE")

    def execute(self, dmx_file="", mode="removemesh", **kwargs):
        if not dmx_file:
            self.fail("No DMX file provided")

        dmx_path = Path(dmx_file)
        if not dmx_path.exists():
            self.fail(f"DMX file not found: {dmx_file}")

        mesh_names = [m for m in self.collect_dynamic("mesh", kwargs) if m and str(m).strip()]

        if not mesh_names:
            self.fail("No mesh names specified")

        try:
            if mode == "keeponlymesh":
                out_path = _mesh_edit_lib.make_edited_dmx(dmx_path, del_names=[], keep_names=mesh_names)
            else:
                out_path = _mesh_edit_lib.make_edited_dmx(dmx_path, del_names=mesh_names)
        except Exception as e:
            self.fail(str(e))

        return (str(out_path.resolve()),)
