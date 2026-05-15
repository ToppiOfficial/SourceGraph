import re
import zlib
import datamodel
from pathlib import Path


def make_edited_dmx(
    dmx_path: Path,
    del_names: list,
    strip_flex: bool = False,
    keep_names: list = None,
    logger=None,
) -> Path:
    """
    Apply mesh deletions and/or flex-rule stripping to dmx_path in a single
    load-edit-write pass.  Output filename uses a CRC-32 hex suffix so identical
    edits always produce the same file.  Written beside the source DMX.
    """
    key_parts: list[str] = []
    if strip_flex:
        key_parts.append("norules")
    if del_names:
        key_parts.append("del:" + ",".join(del_names))
    if keep_names:
        key_parts.append("keep:" + ",".join(keep_names))
    crc      = zlib.crc32("|".join(key_parts).encode()) & 0xFFFFFFFF
    out_path = dmx_path.parent / f"{dmx_path.stem}_{crc:08x}.dmx"

    # sniff original encoding / version
    orig_enc, orig_ver = "keyvalues2", 1
    try:
        with open(dmx_path, "rb") as fh:
            hdr = b""
            while not hdr.endswith(b">"):
                ch = fh.read(1)
                if not ch:
                    break
                hdr += ch
        hdr_str = hdr.decode("ascii", errors="ignore")
        m = re.findall(datamodel.header_format_regex, hdr_str)
        if m:
            orig_enc, orig_ver = m[0][0], int(m[0][1])
        else:
            m = re.findall(datamodel.header_proto2_regex, hdr_str)
            if m:
                orig_enc, orig_ver = "binary_proto", int(m[0][0])
    except Exception:
        pass

    dm       = datamodel.load(str(dmx_path))
    mesh_map = {e.name: e for e in dm.elements if e.type == "DmeMesh"}

    # inverse deletion (keep only)
    if keep_names is not None:
        if not keep_names:
            raise ValueError(
                f"keeponlymesh block is empty for '{dmx_path.name}'. Operation aborted to avoid empty mesh."
            )
        for m_name in list(mesh_map):
            if m_name not in keep_names and m_name not in del_names:
                del_names = list(del_names) + [m_name]

    # mesh deletions (deep, leak-free)
    if del_names:
        def _iter_refs(elem):
            """Yield all Element objects directly referenced by elem's attrs."""
            for key in elem.keys():
                val = elem[key]
                if isinstance(val, datamodel.Element):
                    yield val
                elif isinstance(val, datamodel._ElementArray):
                    for v in val:
                        if isinstance(v, datamodel.Element):
                            yield v

        all_ids   = {e.id: e for e in dm.elements}
        refcount  = {e.id: 0 for e in dm.elements}
        for elem in dm.elements:
            for ref in _iter_refs(elem):
                if ref.id in refcount:
                    refcount[ref.id] += 1

        condemned: set = set()

        def _condemn(elem):
            if elem in condemned:
                return
            condemned.add(elem)
            for ref in _iter_refs(elem):
                if ref.id not in refcount:
                    continue
                refcount[ref.id] -= 1
                if refcount[ref.id] <= 0:
                    _condemn(all_ids[ref.id])

        for mesh_name in del_names:
            mesh_elem = mesh_map.get(mesh_name)
            if mesh_elem is None:
                if logger:
                    logger.warn(f"removemesh: DmeMesh '{mesh_name}' not found in '{dmx_path.name}'")
                continue

            _condemn(mesh_elem)

            for e in dm.elements:
                if e.type == "DmeDag" and e.get("shape") == mesh_elem:
                    _condemn(e)
                    trfm = e.get("transform")
                    if isinstance(trfm, datamodel.Element):
                        _condemn(trfm)
                elif e.name == mesh_name and e.type in ("DmeDag", "DmeTransform"):
                    _condemn(e)

        for e in condemned:
            if e in dm.elements:
                dm.elements.remove(e)

        for parent in dm.elements:
            for attr_key in list(parent.keys()):
                val = parent[attr_key]
                if isinstance(val, datamodel.Element) and val in condemned:
                    del parent[attr_key]
                elif isinstance(val, datamodel._ElementArray):
                    for e in list(condemned):
                        while e in val:
                            val.remove(e)

    # strip flex rules (noautodmxrules 2)
    if strip_flex:
        REMOVE_TYPES = {"DmeCombinationInputControl", "DmeCombinationDominationRule"}
        flex_delete  = {e for e in dm.elements if e.type in REMOVE_TYPES}
        for e in flex_delete:
            if logger:
                logger.info(f"noautodmxrules 2: Removing {e.type} '{e.name}'")
            dm.elements.remove(e)
        for parent in dm.elements:
            for attr_key in list(parent.keys()):
                val = parent[attr_key]
                if isinstance(val, datamodel.Element) and val in flex_delete:
                    del parent[attr_key]
                elif isinstance(val, datamodel._ElementArray):
                    for e in flex_delete:
                        while e in val:
                            val.remove(e)

    dm.write(str(out_path), orig_enc, orig_ver)
    if logger:
        logger.info(f"dmx edit: wrote '{out_path.name}'")
    return out_path
