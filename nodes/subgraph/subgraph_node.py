from __future__ import annotations
import json
import os
from pathlib import Path

from core.node import BaseNode, Port, PortType, parse_type
from core.execution import ExecutionContext, ExecutionMode, ExecutionTarget
from nodes import NODE_CLASS_MAPPINGS


class SubgraphNode(BaseNode):
    """Loads and executes a subgraph file."""
    title = "Subgraph"
    CATEGORY = "Subgraph"
    color = "#28a1e7"
    body_color = "#142933"
    locked_title = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "graph_path": ("FILE", {"default": "", "visible": False, "enum_filter": [".srcsubgraph"]}),
            }
        }

    RETURN_TYPES = ()  # Dynamic outputs based on subgraph

    def on_property_changed(self):
        path = self.inputs.get("graph_path", {}).value if "graph_path" in self.inputs else ""
        if not path:
            return

        full_path = path
        if not os.path.isabs(path) and self.graph and self.graph.project_dir:
            full_path = os.path.normpath(os.path.join(self.graph.project_dir, path))

        if not os.path.exists(full_path):
            return

        try:
            self.title = Path(full_path).stem

            data = json.loads(Path(full_path).read_text(encoding="utf-8"))
            new_in_names = {"graph_path"}
            new_out_names = set()
            
            in_name_counts = {}
            out_name_counts = {}
            resolved_in_names = {}
            resolved_out_names = {}

            for nd in data.get("nodes", []):
                pname = nd.get("values", {}).get("port_name", "")
                if not pname:
                    continue
                    
                if nd["type"] == "SubgraphInputNode":
                    # Track input name conflicts
                    if pname not in in_name_counts:
                        in_name_counts[pname] = 0
                    in_name_counts[pname] += 1
                    
                    # Generate resolved name
                    if in_name_counts[pname] == 1:
                        resolved_name = pname
                    else:
                        resolved_name = f"{pname}_{in_name_counts[pname]}"
                    
                    resolved_in_names[nd["id"]] = resolved_name
                    new_in_names.add(resolved_name)
                    if resolved_name not in self.inputs:
                        p = Port(name=resolved_name, is_input=True, port_type=PortType.ANY, node_id=self.id)
                        self.inputs[resolved_name] = p
                        
                elif nd["type"] == "SubgraphOutputNode":
                    # Track output name conflicts
                    if pname not in out_name_counts:
                        out_name_counts[pname] = 0
                    out_name_counts[pname] += 1
                    
                    # Generate resolved name
                    if out_name_counts[pname] == 1:
                        resolved_name = pname
                    else:
                        resolved_name = f"{pname}_{out_name_counts[pname]}"
                    
                    resolved_out_names[nd["id"]] = resolved_name
                    new_out_names.add(resolved_name)
                    if resolved_name not in self.outputs:
                        # Detect the actual type from the connection to this SubgraphOutputNode
                        detected_type = self._detect_output_type(data, nd["id"])
                        p = Port(name=resolved_name, is_input=False, port_type=detected_type, node_id=self.id)
                        self.outputs[resolved_name] = p
                    else:
                        # Update type for existing port if it changed in the subgraph file
                        self.outputs[resolved_name].port_type = self._detect_output_type(data, nd["id"])

            # Remove obsolete ports
            for p in list(self.inputs.keys()):
                if p not in new_in_names:
                    del self.inputs[p]
            for p in list(self.outputs.keys()):
                if p not in new_out_names:
                    del self.outputs[p]

        except Exception as e:
            print(f"[SubgraphNode] sync error: {e}")

    def _detect_output_type(self, data: dict, output_node_id: str) -> PortType:
        """Detect the actual output type by analyzing connections to the SubgraphOutputNode."""
        
        # Find connections to this SubgraphOutputNode's "value" input
        for conn in data.get("connections", []):
            if conn["dst_node"] == output_node_id and conn["dst_port"] == "value":
                src_node_id = conn["src_node"]
                src_port = conn["src_port"]
                
                # Find the source node
                for nd in data.get("nodes", []):
                    if nd["id"] == src_node_id:
                        # Get the source node's class to determine its output types
                        node_class = NODE_CLASS_MAPPINGS.get(nd["type"])
                        if node_class:
                            # Check if the node has RETURN_TYPES defined
                            if hasattr(node_class, 'RETURN_TYPES') and node_class.RETURN_TYPES:
                                # Find the index of the source port
                                if hasattr(node_class, 'RETURN_NAMES'):
                                    return_names = list(node_class.RETURN_NAMES)
                                    if src_port in return_names:
                                        idx = return_names.index(src_port)
                                        if idx < len(node_class.RETURN_TYPES):
                                            type_spec = node_class.RETURN_TYPES[idx]
                                            return parse_type(type_spec)
                                else:
                                    # If no RETURN_NAMES, assume first output
                                    if node_class.RETURN_TYPES:
                                        type_spec = node_class.RETURN_TYPES[0]
                                        return parse_type(type_spec)
                        break
        
        # Default to ANY if we can't determine the type
        return PortType.ANY

    def execute(self, graph_path: str, **kwargs):
        path = graph_path
        if path and not os.path.isabs(path) and self.graph and self.graph.project_dir:
            path = os.path.normpath(os.path.join(self.graph.project_dir, path))

        if not path or not os.path.exists(path):
            return {}

        try:
            from core.graph import Graph
            sub = Graph()
            sub.load(path, NODE_CLASS_MAPPINGS)

            # Inject values into SubgraphInputNodes
            for node in sub.nodes.values():
                if isinstance(node, SubgraphInputNode):
                    pname = node.inputs["port_name"].value
                    node._injected = kwargs.get(pname)

            context = ExecutionContext(mode=ExecutionMode.PREVIEW, target=ExecutionTarget.JSON)
            results = sub.execute_with_context(context)

            # Collect outputs from SubgraphOutputNodes
            outputs = {}
            for node in sub.nodes.values():
                if isinstance(node, SubgraphOutputNode):
                    original_pname = node.inputs["port_name"].value
                    # Find the resolved name in our outputs
                    resolved_name = None
                    for out_name in self.outputs.keys():
                        if out_name == original_pname or out_name.startswith(f"{original_pname}_"):
                            resolved_name = out_name
                            break
                    if resolved_name:
                        outputs[resolved_name] = node._captured_value
                    else:
                        outputs[original_pname] = node._captured_value
            return outputs
        except Exception as e:
            print(f"[SubgraphNode] execute error: {e}")
            return {}


class SubgraphInputNode(BaseNode):
    """Defines an input port for a subgraph."""
    title = "Subgraph Input"
    CATEGORY = "Subgraph"
    color = "#28a1e7"
    body_color = "#142933"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "port_name": ("STRING", {"default": "input", "visible": False}),
            }
        }

    RETURN_TYPES = ("*",)
    RETURN_NAMES = ("value",)

    def __init__(self):
        super().__init__()
        self._injected = None

    def execute(self, port_name: str, **kwargs):
        return (self._injected,)


class SubgraphOutputNode(BaseNode):
    """Defines an output port for a subgraph."""
    title = "Subgraph Output"
    CATEGORY = "Subgraph"
    color = "#28a1e7"
    body_color = "#142933"

    def __init__(self):
        super().__init__()
        self._captured_value = None

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "port_name": ("STRING", {"default": "output", "visible": False}),
                "value": ("*", {}),
            }
        }

    def execute(self, port_name: str, value, **kwargs):
        # SubgraphOutputNode captures the value for SubgraphNode to read
        self._captured_value = value