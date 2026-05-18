from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.node.port import Port


def parse_dynamic_port_number(port_name: str, prefix: str) -> int | None:
    """Extract the trailing integer from a dynamic port name, or None if absent."""
    if not port_name.startswith(prefix):
        return None
    suffix = port_name[len(prefix):]
    return int(suffix) if suffix.isdigit() else None


def copy_port_attributes(src: "Port", dst: "Port") -> None:
    """Copy presentation and config attributes from src port to dst port."""
    dst.editable             = src.editable
    dst.display_in_inspector = src.display_in_inspector
    dst.allow_connection     = src.allow_connection
    dst.label                = src.label
    dst.default              = src.default
    dst.value                = src.default
    dst.full_row             = src.full_row
    dst.below_ports          = src.below_ports
    dst.row_height           = src.row_height
    dst.row_stretch          = src.row_stretch
    dst.enum_options         = src.enum_options
    dst.enum_filter          = src.enum_filter
    dst.graph_enum           = src.graph_enum
    dst.linked_prefix        = src.linked_prefix


def sync_dynamic_ports(node: Any, allow_value_extra_slot: bool = False) -> bool:
    """Recompute how many dynamic-port slots this node needs and create/remove them.

    Returns True if any port was added, removed, or had its connection renumbered.
    Must only be called while node.graph is set.
    """
    if not node.graph:
        return False

    from core.node.port import Port
    changed = False

    # Collect prefix -> type for each dynamic port group (inputs and outputs)
    groups: dict[tuple[str, bool], str] = {}
    for p in node.inputs.values():
        if p.is_dynamic:
            groups[(p.name.rstrip("0123456789"), True)] = p.port_type
    for p in node.outputs.values():
        if p.is_dynamic:
            groups[(p.name.rstrip("0123456789"), False)] = p.port_type

    target_counts: dict[tuple[str, bool], int] = {}

    for (prefix, is_input), ptype in groups.items():
        connected_ports: dict[int, str] = {}
        for c in node.graph.connections:
            if is_input:
                if c.dst_node == node.id and c.dst_port.startswith(prefix):
                    n = parse_dynamic_port_number(c.dst_port, prefix)
                    if n is not None:
                        connected_ports[n] = c.dst_port
            else:
                if c.src_node == node.id and c.src_port.startswith(prefix):
                    n = parse_dynamic_port_number(c.src_port, prefix)
                    if n is not None:
                        connected_ports[n] = c.src_port

        port_dict = node.inputs if is_input else node.outputs

        # Value compaction: pack non-default/non-empty values forward among
        # unconnected ports so empty trailing slots collapse cleanly.
        if is_input:
            connected_port_names = set(connected_ports.values())
            unconnected = sorted(
                (parse_dynamic_port_number(n, prefix), n)
                for n in port_dict
                if n.startswith(prefix) and parse_dynamic_port_number(n, prefix) is not None
                and n not in connected_port_names
            )
            if unconnected:
                default_val = port_dict[unconnected[0][1]].default

                def _occupied(v: Any, _dflt=default_val) -> bool:
                    if v is None:
                        return False
                    if isinstance(v, str) and not str(v).strip():
                        return False
                    return v != _dflt

                vals = [port_dict[n].value for _, n in unconnected]
                packed = [v for v in vals if _occupied(v)] + [v for v in vals if not _occupied(v)]
                for (_, name), old_v, new_v in zip(unconnected, vals, packed):
                    if old_v != new_v:
                        port_dict[name].value = new_v
                        changed = True

        sorted_indices = sorted(connected_ports.keys())

        def _val_occupied(idx: int) -> bool:
            if idx in connected_ports:
                return False
            p = port_dict.get(f"{prefix}{idx}")
            if p is None or p.value is None:
                return False
            if isinstance(p.value, str) and not str(p.value).strip():
                return False
            return p.value != p.default

        renumber_map: dict[int, int] = {}
        new_idx = 1
        for old_idx in sorted_indices:
            while _val_occupied(new_idx):
                new_idx += 1
            if old_idx != new_idx:
                renumber_map[old_idx] = new_idx
                changed = True
            new_idx += 1

        if renumber_map:
            new_connections = []
            for c in node.graph.connections:
                if is_input:
                    if c.dst_node == node.id and c.dst_port.startswith(prefix):
                        n = parse_dynamic_port_number(c.dst_port, prefix)
                        if n is not None and n in renumber_map:
                            new_port = f"{prefix}{renumber_map[n]}"
                            new_connections.append(
                                type(c)(c.src_node, c.src_port, c.dst_node, new_port)
                            )
                            continue
                else:
                    if c.src_node == node.id and c.src_port.startswith(prefix):
                        n = parse_dynamic_port_number(c.src_port, prefix)
                        if n is not None and n in renumber_map:
                            new_port = f"{prefix}{renumber_map[n]}"
                            new_connections.append(
                                type(c)(c.src_node, new_port, c.dst_node, c.dst_port)
                            )
                            continue
                new_connections.append(c)
            node.graph.connections = new_connections

        max_conn_idx = 0
        for c in node.graph.connections:
            if is_input:
                if c.dst_node == node.id and c.dst_port.startswith(prefix):
                    n = parse_dynamic_port_number(c.dst_port, prefix)
                    if n is not None:
                        max_conn_idx = max(max_conn_idx, n)
            else:
                if c.src_node == node.id and c.src_port.startswith(prefix):
                    n = parse_dynamic_port_number(c.src_port, prefix)
                    if n is not None:
                        max_conn_idx = max(max_conn_idx, n)

        max_val_idx = 0
        if is_input:
            for p in port_dict.values():
                n = parse_dynamic_port_number(p.name, prefix)
                if (p.is_dynamic and n is not None
                        and p.value != p.default
                        and str(p.value if p.value is not None else "").strip() != ""):
                    max_val_idx = max(max_val_idx, n)

        if allow_value_extra_slot:
            target_count = max(1, max(max_conn_idx, max_val_idx) + 1)
        else:
            target_count = max(1, max_conn_idx + 1, max_val_idx)

        target_counts[(prefix, is_input)] = target_count

    # Honour linked_prefix grouping: linked groups track the size of the source group
    for (prefix, is_input) in list(target_counts):
        if not is_input:
            continue
        port_dict = node.inputs
        tmpl = next(
            (p for p in port_dict.values()
             if p.is_dynamic and p.name.startswith(prefix)
             and parse_dynamic_port_number(p.name, prefix) is not None and p.linked_prefix),
            None,
        )
        if tmpl and tmpl.linked_prefix:
            src_key = (tmpl.linked_prefix, True)
            if src_key in target_counts:
                target_counts[(prefix, is_input)] = max(
                    target_counts[(prefix, is_input)],
                    target_counts[src_key],
                )

    # Create / remove ports to match target counts
    for (prefix, is_input), ptype in groups.items():
        target_count = target_counts[(prefix, is_input)]
        port_dict = node.inputs if is_input else node.outputs

        template_port = next(
            (p for p in port_dict.values() if p.is_dynamic and p.name.startswith(prefix)),
            None,
        )

        for i in range(1, target_count + 1):
            name = f"{prefix}{i}"
            if name not in port_dict:
                p = Port(name=name, is_input=is_input, port_type=ptype, node_id=node.id)
                p.is_dynamic = True
                p.allow_connection = True
                if template_port:
                    copy_port_attributes(template_port, p)

                # Insert after the last sibling of the same prefix to preserve order
                all_keys = list(port_dict.keys())
                last_pos = max(
                    (j for j, k in enumerate(all_keys)
                     if k.startswith(prefix) and parse_dynamic_port_number(k, prefix) is not None),
                    default=-1,
                )
                if last_pos >= 0:
                    insert_after = all_keys[last_pos]
                    new_dict: dict = {}
                    for k in all_keys:
                        new_dict[k] = port_dict[k]
                        if k == insert_after:
                            new_dict[name] = p
                    port_dict.clear()
                    port_dict.update(new_dict)
                else:
                    port_dict[name] = p

                changed = True

        ports_to_remove = [
            name for name in list(port_dict)
            if name.startswith(prefix)
            and parse_dynamic_port_number(name, prefix) is not None
            and parse_dynamic_port_number(name, prefix) > target_count
        ]
        for name in ports_to_remove:
            del port_dict[name]
            changed = True

    return changed
