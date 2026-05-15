from core.port_type_registry import register_port_type, PortTypeSpec

# Matches EDIT_STYLE from gui/theme.py
_SPINBOX_STYLE = """
QDoubleSpinBox {
    background-color: #1F1F1F;
    color: #ffffff;
    border: 1px solid #444444;
    border-radius: 3px;
    padding: 2px 4px;
    font-size: 11px;
}
QDoubleSpinBox:focus {
    border: 1px solid #63c2df;
}
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 0px;
    border: none;
}
"""

# Matches NODE_WIDGET_STYLE from gui/theme.py
_CANVAS_EDIT_STYLE = """
QLineEdit {
    background-color: #131313;
    color: #ffffff;
    border: none;
    border-radius: 3px;
    padding: 2px 4px;
    font-size: 11px;
}
"""


def _parse_vec3(s):
    try:
        parts = str(s or "0 0 0").split()
        vals = [float(x) for x in parts[:3]]
        while len(vals) < 3:
            vals.append(0.0)
        return vals
    except (ValueError, IndexError):
        return [0.0, 0.0, 0.0]


def _make_vector3_canvas_widget(port, parent=None):
    from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit

    vals = _parse_vec3(port.value)

    container = QWidget(parent)
    hl = QHBoxLayout(container)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(2)

    edits = []
    for val in vals:
        edit = QLineEdit(container)
        edit.setFixedHeight(20)
        edit.setText(f"{val:g}")
        edit.setStyleSheet(_CANVAS_EDIT_STYLE)
        edits.append(edit)
        hl.addWidget(edit)

    def _sync():
        components = []
        for e in edits:
            try:
                components.append(float(e.text()))
            except ValueError:
                components.append(0.0)
        port.value = " ".join(f"{v:g}" for v in components)

    for edit in edits:
        edit.editingFinished.connect(_sync)

    return container


def _make_vector3_inspector_widget(port):
    from PySide6.QtWidgets import QWidget, QHBoxLayout, QDoubleSpinBox

    vals = _parse_vec3(port.value)

    container = QWidget()
    hl = QHBoxLayout(container)
    hl.setContentsMargins(0, 0, 0, 0)
    hl.setSpacing(3)

    hl.addStretch()

    spinboxes = []
    for val in vals:
        sb = QDoubleSpinBox()
        sb.setDecimals(4)
        sb.setRange(-99999.0, 99999.0)
        sb.setValue(val)
        sb.setFixedWidth(60)
        sb.setFixedHeight(20)
        sb.setStyleSheet(_SPINBOX_STYLE)
        spinboxes.append(sb)
        hl.addWidget(sb)

    def _on_changed():
        new_val = " ".join(f"{sb.value():g}" for sb in spinboxes)
        if new_val != str(port.value or ""):
            port.value = new_val

    for sb in spinboxes:
        sb.editingFinished.connect(_on_changed)

    return container


register_port_type(PortTypeSpec(
    key="vector3",
    color="#98c379",
    editable=True,
    inspector_editable=True,
    canvas_widget_factory=_make_vector3_canvas_widget,
    inspector_widget_factory=_make_vector3_inspector_widget,
    aliases=["vec3"],
))
