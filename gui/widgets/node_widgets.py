from __future__ import annotations
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton, QLineEdit, QTextEdit
from gui.theme import *



def make_file_picker(label_text: str, on_browse) -> tuple[QWidget, QLabel]:
    """Return a (container, label) pair: a label showing the current file name + a '...' browse button."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)

    lbl = QLabel(label_text)
    lbl.setStyleSheet(NODE_FILE_LABEL_STYLE)
    layout.addWidget(lbl, 1)

    btn = QPushButton("...")
    btn.setFixedWidth(24)
    btn.setStyleSheet(BTN_STYLE)
    btn.clicked.connect(on_browse)
    layout.addWidget(btn)

    return container, lbl


def make_path_editor(value: str, on_change, on_browse) -> tuple[QWidget, QLineEdit]:
    """Return a (container, line_edit) pair: an editable path field + a '...' browse button."""
    container = QWidget()
    layout = QHBoxLayout(container)
    layout.setContentsMargins(2, 0, 2, 0)
    layout.setSpacing(2)

    edit = QLineEdit(value or "")
    edit.setStyleSheet(NODE_WIDGET_STYLE)
    edit.editingFinished.connect(on_change)
    layout.addWidget(edit, 1)

    btn = QPushButton("...")
    btn.setFixedWidth(24)
    btn.setStyleSheet(BTN_STYLE)
    btn.clicked.connect(on_browse)
    layout.addWidget(btn)

    return container, edit


def make_text_display() -> QTextEdit:
    """Return a read-only QTextEdit styled for node output display."""
    display = QTextEdit()
    display.setReadOnly(True)
    display.setTabStopDistance(20)
    display.setStyleSheet(NODE_TEXT_DISPLAY_STYLE)
    return display
