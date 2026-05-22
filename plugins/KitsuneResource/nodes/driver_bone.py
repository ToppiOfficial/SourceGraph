import re
import sys
from pathlib import Path

_LIBS = str(Path(__file__).parent.parent / "libs")
if _LIBS not in sys.path:
    sys.path.insert(0, _LIBS)

import vrd as _vrd_lib
from sourcegraph.sys import BaseNode, In, OptIn, DynIn, Out


class DriverBoneNode(BaseNode):
    title    = "Driver Bone"
    CATEGORY = "KitsuneResource"
    color    = "#61afef"
    default_width = 265

    driver_bone    = In("STRING", label="Driver Bone")
    pose_file      = In("FILE",   label="Pose File", allow_connection=True)
    restpose_file  = OptIn("FILE",   default="", label="Restpose File")
    restpose_frame = OptIn("INT",    default=0,   label="Restpose Frame")
    scale          = OptIn("FLOAT",  default=1.0, label="Scale")
    trigger        = DynIn("VECTOR2", prefix="trigger", default="90 0")
    helper         = DynIn("STRING",  prefix="helper")

    file     = Out("FILE")
    qc_param = Out("QC_COMMAND")

    def execute(self, driver_bone="", pose_file="",
                scale=1.0, restpose_file="", restpose_frame=0, **kwargs):
        if not driver_bone:
            self.fail("No driver bone specified")
        if not pose_file:
            self.fail("No pose file provided")

        pose_path = Path(pose_file)
        if not pose_path.exists():
            self.fail(f"Pose file not found: {pose_file}")

        pose_dir = pose_path.parent

        triggers = []
        for raw in self.collect_dynamic("trigger", kwargs):
            if not raw or not str(raw).strip():
                continue
            parts = str(raw).split()
            if len(parts) < 2:
                self.fail(f"Trigger must be 'angle frame', got: {raw!r}")
            try:
                triggers.append((float(parts[0]), int(parts[1])))
            except ValueError:
                self.fail(f"Could not parse trigger '{raw}' - expected 'angle frame' e.g. '45.0 3'")

        target_bones = [t for t in self.collect_dynamic("helper", kwargs) if t and str(t).strip()]

        if not target_bones:
            self.fail("No target bones specified")

        vrd_name = re.sub(r'[^\w]', '_', f"{pose_path.stem.lower()}_{driver_bone.lower()}")

        rp_path  = restpose_file if restpose_file else None
        rp_frame = int(restpose_frame) if restpose_frame else 0

        try:
            vrd_path = _vrd_lib.generate_vrd(
                driver_bone, pose_file, triggers, target_bones,
                pose_dir, pose_dir, vrd_name, float(scale),
                restpose_path=rp_path, restpose_frame=rp_frame,
            )
        except Exception as e:
            self.fail(str(e))

        lines = [f'$bonemerge "{b}"' for b in target_bones]
        lines.append(f"// VRD Scale: {scale}")
        abs_vrd = str(vrd_path.resolve())
        base_dir = self._graph_base_dir()
        rel_vrd = self._try_make_relative(abs_vrd, base_dir) if base_dir else abs_vrd
        lines.append(f'$proceduralbones "{rel_vrd}"')
        qc_param = "\n".join(lines)

        return (str(vrd_path.resolve()), qc_param)
