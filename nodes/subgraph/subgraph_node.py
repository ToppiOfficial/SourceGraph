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
                "graph_path": ("FILE", {
                    "default": "",
                    "allow_connection": False,
                    "full_row": True,
                    "enum_filter": [".srcsubgraph"],
                }),
            }
        }

    RETURN_TYPES = ()  # Dynamic outputs based on subgraph

    def on_property_changed(self):
        path = self.inputs.get("graph_path", {}).value if "graph_path" in self.inputs else ""
        if hasattr(self, '_subgraph_label'):
            try:
                self._subgraph_label.setText(os.path.basename(path) if path else "Select subgraph…")
            except RuntimeError:
                pass
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

    def create_widget_for_port(self, port):
        if port.name != "graph_path":
            return None

        from PySide6.QtWidgets import QPushButton, QHBoxLayout, QWidget, QLabel
        from gui.theme import BTN_STYLE

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        from gui.theme import NODE_FILE_LABEL_STYLE
        self._subgraph_label = QLabel(os.path.basename(port.value) if port.value else "Select subgraph…")
        self._subgraph_label.setStyleSheet(NODE_FILE_LABEL_STYLE)
        layout.addWidget(self._subgraph_label, 1)

        browse_btn = QPushButton("...")
        browse_btn.setFixedWidth(24)
        browse_btn.setStyleSheet(BTN_STYLE)
        browse_btn.clicked.connect(self._show_subgraph_dialog)
        layout.addWidget(browse_btn)

        self._graph_path_port = port
        return container
    
    def _show_subgraph_dialog(self):
        from gui.menu.file_search_dialog import SubgraphSearchDialog
        from PySide6.QtWidgets import QApplication
        from gui.main_window import MainWindow
        main_window = next(
            (w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow)), None
        )
        dialog = SubgraphSearchDialog(parent=main_window)
        if dialog.exec() == SubgraphSearchDialog.Accepted and dialog.selected_file:
            self._set_graph_path(dialog.selected_file)

    def _set_graph_path(self, path: str) -> None:
        if hasattr(self, '_graph_path_port'):
            self._graph_path_port.value = path
        if hasattr(self, '_subgraph_label'):
            try:
                self._subgraph_label.setText(os.path.basename(path))
            except RuntimeError:
                pass
        self.on_property_changed()
        if self.graph:
            # Remove connections to ports that no longer exist after the subgraph change
            self.graph.connections = [
                c for c in self.graph.connections
                if not (
                    (c.src_node == self.id and c.src_port not in self.outputs) or
                    (c.dst_node == self.id and c.dst_port not in self.inputs)
                )
            ]
            self.graph.commit_change("Change Subgraph")
            scene = getattr(self.graph, '_scene_ref', lambda: None)()
            if scene:
                item = scene._node_items.get(self.id)
                if item:
                    item.refresh_ports()

    def execute(self, graph_path: str, **kwargs):
        path = graph_path
        if path and not os.path.isabs(path) and self.graph and self.graph.project_dir:
            path = os.path.normpath(os.path.join(self.graph.project_dir, path))

        if not path or not os.path.exists(path):
            return {}

        try:
            self.error_msg = None
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
            from gui.logger import log
            path_port = self.inputs.get("graph_path")
            name = os.path.basename(path_port.value) if path_port and path_port.value else "subgraph"
            self.error_msg = str(e)
            log.error(f"[SubgraphNode '{name}'] {e}")
            raise


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