from __future__ import annotations
import os

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from core.node import BaseNode, In, OptIn, Out, port_uses_graph_variables
from gui.widgets.node_widgets import make_file_picker


class VariableOutNode(BaseNode):
    """Outputs graph.variables[var_name]."""
    title = "Get Variable"
    CATEGORY = "General"
    color = "#b4629d"
    locked_title = True

    var_name = In("ENUM", default="", allow_connection=False, graph_enum="variables", label="variable")
    value    = Out("ANY")

    def get_reads(self) -> set[str]:
        p = self.inputs.get("var_name")
        return {f"var:{p.value}"} if p and p.value else set()

    def on_property_changed(self):
        port = self.inputs.get("var_name")
        var_name = str(port.value) if port and port.value else "..."
        self.title = f"GET {var_name}"

    def execute(self, var_name: str, **kwargs):
        val = None
        if self.graph and var_name:
            val = self.graph.variables.get(var_name)
        if val is None or (isinstance(val, str) and not val.strip()):
            self.fail(f"Variable '{var_name}' is empty or unset")
        return (val,)


class VariableInNode(BaseNode):
    """Writes new_value into graph.variables[var_name] during execution."""
    title = "Set Variable"
    CATEGORY = "General"
    color = "#b4629d"
    locked_title = True

    var_name  = In("ENUM", default="", allow_connection=False, graph_enum="variables", label="variable")
    new_value = OptIn("ANY", editable=False)

    def get_writes(self) -> set[str]:
        p = self.inputs.get("var_name")
        return {f"var:{p.value}"} if p and p.value else set()

    def on_property_changed(self):
        port = self.inputs.get("var_name")
        var_name = str(port.value) if port and port.value else "..."
        self.title = f"SET {var_name}"

    def execute(self, var_name: str, **kwargs):
        new_value = kwargs.get("new_value")
        if self.graph and var_name and var_name in self.graph.variables:
            if new_value is not None and (not isinstance(new_value, str) or new_value.strip()):
                self.graph.variables[var_name] = new_value
        return {}


class SessionNode(BaseNode):
    """Outputs the name of a selected execution session."""
    title = "Session"
    CATEGORY = "General"
    color = "#6272a4"
    locked_title = True

    session_item = In("ENUM", default="", allow_connection=False, full_row=True, graph_enum="session_items")
    session      = Out("STRING")

    def __init__(self):
        super().__init__()
        self.custom_name = None

    def _get_clean_name(self, val: str) -> str:
        """Resolve the clean name (custom or title) from session_name|node_id."""
        if not val or "|" not in val:
            return ""
        
        parts = val.split("|", 1)
        if len(parts) < 2:
            return ""
        s_name, node_id = parts

        if not self.graph:
            return ""

        exec_data = getattr(self.graph, "execution_sessions", None)
        if not exec_data:
            return ""

        sessions_list = []
        if isinstance(exec_data, dict):
            sessions_list = exec_data.get("sessions", [])
        elif isinstance(exec_data, list):
            sessions_list = exec_data

        for s_data in sessions_list:
            if s_data.get("name") == s_name:
                custom = s_data.get("node_names", {}).get(node_id)
                if custom:
                    return custom
                break
        
        # Fallback to node title in graph
        node = self.graph.nodes.get(node_id)
        if node:
            return node.title

        return ""

    def on_property_changed(self):
        self.custom_name = None

        port = self.inputs.get("session_item")
        val = port.value if port and port.value else ""

        if not self.graph:
            # During loading, we might not have the graph yet.
            # We should keep the value so it's not lost.
            #
            # I feel like the source of the problem is due to poor 
            # implementation but this is fine for now.
            self.title = "Session"
            if hasattr(self, "_session_label"):
                try:
                    self._session_label.setText("Select session…")
                except RuntimeError:
                    pass
            return

        name = self._get_clean_name(val)
        
        if val and not name:
            port.value = ""
            val = ""

        self.title = name if name else "Session"

        if hasattr(self, '_session_label'):
            try:
                text = name if name else "Select session…"
                self._session_label.setText(text)
                
                # If the widget is part of a proxy, it might need a repaint
                if self._session_label.parentWidget():
                    self._session_label.parentWidget().update()
            except RuntimeError:
                pass

    def create_widget_for_port(self, port):
        if port.name != "session_item":
            return None
        val = port.value if port and port.value else ""
        name = self._get_clean_name(val)
        label_text = name if name else "Select session…"
        container, self._session_label = make_file_picker(label_text, self._show_session_dialog)
        return container

    def _show_session_dialog(self):
        from gui.menu.file_search_dialog import SessionSearchDialog
        from gui.main_window import MainWindow
        main_window = next(
            (w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow)), None
        )
        dialog = SessionSearchDialog(parent=main_window)
        if dialog.exec() == SessionSearchDialog.Accepted and dialog.selected_session:
            self._set_session(dialog.selected_session)

    def _set_session(self, val: str) -> None:
        port = self.inputs.get("session_item")
        if port:
            port.value = val
        
        self.on_property_changed()
        if self.graph:
            self.graph.commit_change("Change Session")
            scene = getattr(self.graph, '_scene_ref', lambda: None)()
            if scene:
                item = getattr(scene, '_node_items', {}).get(self.id)
                if item:
                    # Trigger a deep refresh to ensure widgets are correctly synced
                    item.refresh_ports()
                    item.update()

    def execute(self, session_item: str, **kwargs):
        return (self._get_clean_name(session_item),)


def _handle_variable_drop(scene, pos, value, modifiers) -> bool:
    from core.registry import NODE_CLASS_MAPPINGS
    cls_name = "VariableInNode" if (modifiers & Qt.AltModifier) else "VariableOutNode"
    cls = NODE_CLASS_MAPPINGS.get(cls_name)
    if not cls:
        return False
    node = cls()
    node.graph = scene.graph
    for pname, port in node.inputs.items():
        if port_uses_graph_variables(port):
            port.value = value
            break
    if hasattr(node, "on_property_changed"):
        node.on_property_changed()
    scene.add_node(node, pos)
    item = scene._node_items.get(node.id)
    if item:
        item.setSelected(True)
    return True


from core.drop_registry import register_drop_handler
register_drop_handler("variable", _handle_variable_drop)
