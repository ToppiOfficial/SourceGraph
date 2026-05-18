from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton, QFileDialog
from PySide6.QtCore import Qt
from gui.theme import NUMBER_INPUT_STYLE, NODE_NUMBER_BTN_STYLE, EDIT_STYLE


def make_file_canvas_widget(port, parent=None) -> QWidget:
    container = QWidget(parent)
    container.setFixedHeight(22)
    container.setObjectName("NumberInputContainer")
    container.setStyleSheet(NUMBER_INPUT_STYLE)

    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    edit = QLineEdit(container)
    edit.setFixedHeight(20)
    edit.setStyleSheet(
        "QLineEdit { background: transparent; border: none; font-size: 11px; padding: 0px 4px; }"
    )
    v = port.value
    edit.setText(str(v) if v is not None else "")
    edit.setProperty("original_val", port.value)

    btn = QPushButton("...", container)
    btn.setFixedSize(24, 20)
    btn.setStyleSheet(NODE_NUMBER_BTN_STYLE)
    btn.setFocusPolicy(Qt.NoFocus)

    layout.addWidget(edit, 1)
    layout.addWidget(btn)

    container.setProperty("widget_type", "file")
    container.file_edit = edit
    container.browse_btn = btn
    container.refresh_value = lambda v, _e=edit: _e.setText(str(v) if v is not None else "")
    return container


def make_file_inspector_widget(port, on_commit=None) -> QWidget:
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(2)

    edit = QLineEdit(str(port.value or ""))
    edit.setStyleSheet(EDIT_STYLE)
    edit.setProperty("original_val", port.value)

    btn = QPushButton("…")
    btn.setFixedWidth(28)

    def _committed(path: str) -> None:
        old = edit.property("original_val")
        if old == path:
            return
        edit.setProperty("original_val", path)
        if on_commit is not None:
            on_commit(path)
        else:
            port.value = path

    def _on_editing_finished():
        _committed(edit.text())

    def _on_browse():
        path, _ = QFileDialog.getOpenFileName(None, "Select File", "", "All Files (*)")
        if path:
            edit.setText(path)
            _committed(path)

    edit.editingFinished.connect(_on_editing_finished)
    btn.clicked.connect(_on_browse)

    layout.addWidget(edit, 1)
    layout.addWidget(btn)
    return container
