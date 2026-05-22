import re
import sys
from pathlib import Path

_LIBS = str(Path(__file__).parent.parent / "libs")
if _LIBS not in sys.path:
    sys.path.insert(0, _LIBS)

import vrd as _vrd_lib
from sourcegraph.sys import BaseNode, In, OptIn, DynIn, Out


def _parse_vec3(s: str, default=(0.0, 0.0, 0.0)) -> tuple[float, float, float]:
    try:
        parts = str(s).split()
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except (IndexError, ValueError):
        return default


class DriverLookAtBoneNode(BaseNode):
    title    = "Driver Look At Bone"
    CATEGORY = "KitsuneResource"
    color    = "#c678dd"
    default_width = 265

    target_bone  = In("STRING",  label="Target Bone")
    attachment   = OptIn("STRING",  default="",        label="Attachment Name")
    pose_file    = In("FILE",    label="Pose File", allow_connection=True)
    frame_index  = OptIn("INT",     default=0,         label="Frame Index")
    aim_vector   = OptIn("VECTOR3", default="0 0 1",   label="Aim Vector")
    up_vector    = OptIn("VECTOR3", default="0 1 0",   label="Up Vector")
    location     = OptIn("VECTOR3", default="0 0 0",   label="Location Offset")
    rotation     = OptIn("VECTOR3", default="0 0 0",   label="Rotation Offset")
    scale        = OptIn("FLOAT",   default=1.0,       label="Scale")
    helper       = DynIn("STRING",  prefix="helper", editable=False)

    file     = Out("FILE")
    qc_param = Out("QC_COMMAND")

    def execute(self, target_bone="", attachment="", pose_file="",
                frame_index=0, aim_vector="0 0 1", up_vector="0 1 0",
                location="0 0 0", rotation="0 0 0",
                scale=1.0, **kwargs):
        if not target_bone:
            self.fail("No target bone specified")
        if not pose_file:
            self.fail("No pose file provided")

        pose_path = Path(pose_file)
        if not pose_path.exists():
            self.fail(f"Pose file not found: {pose_file}")

        pose_dir = pose_path.parent

        helper_bones = [h for h in self.collect_dynamic("helper", kwargs) if h and str(h).strip()]
        if not helper_bones:
            self.fail("No helper bones specified")

        aim_vec = _parse_vec3(aim_vector, (0.0, 0.0, 1.0))
        up_vec  = _parse_vec3(up_vector,  (0.0, 1.0, 0.0))
        loc_vec = _parse_vec3(location,   (0.0, 0.0, 0.0))
        rot_vec = _parse_vec3(rotation,   (0.0, 0.0, 0.0))

        stripped_target = target_bone.split(".")[-1]
        auto_attachment = not bool(attachment and attachment.strip())
        if auto_attachment:
            attachment_name = f"{stripped_target}_lookattarget"
        else:
            attachment_name = attachment.strip()

        vrd_name = re.sub(r'[^\w]', '_', f"lookat_{pose_path.stem.lower()}_{target_bone.lower()}")

        try:
            vrd_path = _vrd_lib.generate_lookat_vrd(
                target_bone, attachment_name, int(frame_index),
                aim_vec, up_vec, helper_bones,
                pose_file, pose_dir, pose_dir, vrd_name, float(scale),
            )
        except Exception as e:
            self.fail(str(e))

        lines = []
        if auto_attachment:
            pos_str = " ".join(f"{v:g}" for v in loc_vec)
            rot_str = " ".join(f"{v:g}" for v in rot_vec)
            lines.append(f'$attachment "{attachment_name}" "{target_bone}" {pos_str} rotate {rot_str}')
        for bone in helper_bones:
            lines.append(f'$bonemerge "{bone}"')
        lines.append(f"// VRD Scale: {scale}")
        abs_vrd = str(vrd_path.resolve())
        base_dir = self._graph_base_dir()
        rel_vrd = self._try_make_relative(abs_vrd, base_dir) if base_dir else abs_vrd
        lines.append(f'$proceduralbones "{rel_vrd}"')
        qc_param = "\n".join(lines)

        return (str(vrd_path.resolve()), qc_param)
