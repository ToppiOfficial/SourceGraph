from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QFileDialog,
    QFrame,
    QApplication,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QCursor, QPainter

from core.node import port_uses_graph_variables
from core.registry import (
    get_color as _get_port_color,
    is_inspector_editable as _type_inspector_editable,
    get_port_type_spec as _get_type_spec,
    make_port_notify_proxy,
    get_file_picker,
)
from gui.theme import *
from gui.items.node import NodeItem
from gui.panels.base_panel import BasePanel
from gui.logger import log
from gui.commands import PropertyCommand
from gui.menu.file_search_dialog import GenericSelectionDialog

if TYPE_CHECKING:
    from gui.main_window import MainWindow


def _port_is_editable(port_type) -> bool:
    return _type_inspector_editable(port_type)


def _validate_port_text(port_type: str, text: str) -> str | None:
    if not text:
        return None
    spec = _get_type_spec(port_type)
    return spec.validate_text(text) if spec and spec.validate_text else None


_TITLE_EDIT_STYLE = f"""
QLineEdit {{
    background: transparent;
    border: none;
    border-bottom: 1px solid transparent;
    color: {FG_BRIGHT};
    font-size: 12px;
    font-weight: bold;
    font-family: "Roboto", "Segoe UI";
    padding: 0px 0px 1px 0px;
}}
QLineEdit:focus {{
    border-bottom: 1px solid {ACCENT};
}}
"""

_SECTION_LABEL_STYLE = (
    f"color: {FG_DIMMER}; font-size: 10px; font-weight: bold; "
    f"padding: 6px 10px 2px 10px; letter-spacing: 1px; background: transparent;"
)
_PORT_LABEL_STYLE  = f"color: {FG_DEFAULT}; font-size: 12px; background: transparent;"
_CONN_HINT_STYLE   = f"color: {FG_DIMMER}; font-size: 11px; font-style: italic; background: transparent;"
_MAX_WIDGET_W      = 140  # mirrors ~120-140 px widget width in a DEFAULT_W=180 node


class PortDot(QWidget):
    """Colored circle matching the port dot drawn on nodes in the graph editor."""

    def __init__(self, color: str, parent=None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setFixedSize(12, 12)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self._color)
        p.setPen(self._color.darker(150))
        p.drawEllipse(1, 1, 10, 10)


def _make_separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(
        f"background: {BORDER_DARK}; border: none; max-height: 1px; margin: 2px 0px;"
    )
    return sep


def _position_near_cursor(dialog) -> None:
    """Move a dialog to appear near the cursor, clamped to the current screen."""
    pos = QCursor.pos()
    screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
    avail = screen.availableGeometry()

    dialog.adjustSize()
    dw = dialog.sizeHint().width()
    dh = dialog.sizeHint().height()

    x = pos.x() + 14
    y = pos.y() - dh // 2

    x = max(avail.left(), min(x, avail.right() - dw))
    y = max(avail.top(), min(y, avail.bottom() - dh))

    dialog.move(x, y)


class SelectedNodePanel(QWidget):
    """Mirrors the selected node's visual structure for inline property editing."""

    def __init__(self, main_window: MainWindow, parent=None) -> None:
        super().__init__(parent)
        self.main_window = main_window
        self._item: NodeItem | None = None
        self._title_edit: QLineEdit | None = None
        self._suppress_refresh = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Placeholder when 0 or 2+ nodes are selected
        self._placeholder = QLabel("Select a single node to edit its properties here.")
        self._placeholder.setStyleSheet(f"color:{FG_DIM}; font-size:13px; padding:16px;")
        self._placeholder.setWordWrap(True)
        self._placeholder.setAlignment(Qt.AlignCenter)
        outer.addWidget(self._placeholder)

        # Node mirror container
        self._mirror = QWidget()
        self._mirror.setObjectName("NodeMirror")
        self._mirror.setVisible(False)
        ml = QVBoxLayout(self._mirror)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        # Title frame
        self._title_frame = QWidget()
        self._title_frame.setObjectName("NodeMirrorTitle")
        self._title_frame.setStyleSheet(
            "QWidget#NodeMirrorTitle { background: #181818; border-radius: 6px 6px 0px 0px; }"
        )
        tf = QVBoxLayout(self._title_frame)
        tf.setContentsMargins(10, 8, 10, 6)
        tf.setSpacing(1)

        self._title_edit = QLineEdit()
        self._title_edit.setStyleSheet(_TITLE_EDIT_STYLE)
        self._title_edit.editingFinished.connect(self._on_title_finished)
        tf.addWidget(self._title_edit)

        self._class_label = QLabel()
        self._class_label.setStyleSheet(
            f"color:{FG_DIM}; font-size:10px; background:transparent;"
        )
        tf.addWidget(self._class_label)

        ml.addWidget(self._title_frame)

        # Scrollable port body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        self._body = QWidget()
        self._body.setStyleSheet("background: transparent;")
        self._rows = QVBoxLayout(self._body)
        self._rows.setContentsMargins(0, 4, 0, 8)
        self._rows.setSpacing(0)
        self._rows.addStretch()

        scroll.setWidget(self._body)
        ml.addWidget(scroll, 1)

        outer.addWidget(self._mirror, 1)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        if self._suppress_refresh:
            return
        scene = self.main_window.scene
        try:
            selected = [i for i in scene.selectedItems() if isinstance(i, NodeItem)]
        except RuntimeError:
            return

        if len(selected) != 1:
            self._build_empty(len(selected))
            return
        self._build_for_node(selected[0])

    # ------------------------------------------------------------------
    # Build helpers
    # ------------------------------------------------------------------

    def _build_empty(self, n_selected: int) -> None:
        self._item = None
        self._mirror.setVisible(False)
        self._placeholder.setVisible(True)
        if n_selected == 0:
            self._placeholder.setText("Select a single node to edit its properties here.")
        else:
            self._placeholder.setText("Select only one node to use the inspector.")

    def _clear_rows(self) -> None:
        while self._rows.count() > 1:
            item = self._rows.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _insert(self, widget: QWidget, at: int) -> None:
        self._rows.insertWidget(at, widget)

    def _build_for_node(self, item: NodeItem) -> None:
        self._item = item
        node = item.node
        self._clear_rows()

        # Update title frame
        self._title_edit.setText(node.display_name)
        self._title_edit.setReadOnly(getattr(node, "locked_title", False))
        self._class_label.setText(f"{node.__class__.__name__}  ·  {node.id[:8]}…")

        self._placeholder.setVisible(False)
        self._mirror.setVisible(True)

        scene = self.main_window.scene
        graph = scene.graph
        at = 0

        # Outputs section
        visible_out = [
            (pname, port) for pname, port in node.outputs.items()
            if port.display_in_inspector
        ]
        if visible_out:
            sec = QLabel("OUTPUTS")
            sec.setStyleSheet(_SECTION_LABEL_STYLE)
            self._insert(sec, at); at += 1
            for pname, port in visible_out:
                self._insert(self._make_output_row(pname, port), at); at += 1
            self._insert(_make_separator(), at); at += 1

        # Inputs section
        visible_in = [
            (pname, port) for pname, port in node.inputs.items()
            if port.display_in_inspector and (port.editable or _port_is_editable(port.port_type))
        ]
        if visible_in:
            sec = QLabel("INPUTS")
            sec.setStyleSheet(_SECTION_LABEL_STYLE)
            self._insert(sec, at); at += 1
            for pname, port in visible_in:
                conn = graph.get_input_connection(node.id, pname)
                row = self._make_input_row(pname, port, conn, graph, node)
                if row is not None:
                    self._insert(row, at); at += 1

    # ------------------------------------------------------------------
    # Row factories
    # ------------------------------------------------------------------

    def _make_output_row(self, pname: str, port) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 3, 10, 3)
        rl.setSpacing(6)
        lbl = QLabel(port.label or pname)
        lbl.setStyleSheet(_PORT_LABEL_STYLE)
        lbl.setWordWrap(True)
        rl.addWidget(lbl, 1)
        dot = PortDot(_get_port_color(port.port_type))
        rl.addWidget(dot, 0, Qt.AlignVCenter)
        return row

    def _make_input_row(self, pname: str, port, conn, graph, node) -> QWidget | None:
        # Check for a custom widget from the node first
        custom_w = None
        if not conn and hasattr(node, "create_widget_for_port"):
            custom_w = node.create_widget_for_port(port)

        if custom_w is not None:
            row = QWidget()
            row.setStyleSheet("background: transparent;")
            if port.full_row:
                rl = QVBoxLayout(row)
                rl.setContentsMargins(8, 2, 8, 2)
                rl.setSpacing(0)
                rl.addWidget(custom_w)
            else:
                rl = QHBoxLayout(row)
                rl.setContentsMargins(10, 3, 10, 3)
                rl.setSpacing(6)
                rl.addWidget(PortDot(_get_port_color(port.port_type)), 0, Qt.AlignVCenter)
                lbl = QLabel(port.label or pname)
                lbl.setStyleSheet(_PORT_LABEL_STYLE)
                rl.addWidget(lbl)
                rl.addWidget(custom_w, 1)
            return row

        # Default row: dot + label + widget
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 3, 10, 3)
        rl.setSpacing(6)

        dot = PortDot(_get_port_color(port.port_type))
        rl.addWidget(dot, 0, Qt.AlignVCenter)

        lbl = QLabel(port.label or pname)
        lbl.setStyleSheet(_PORT_LABEL_STYLE)
        lbl.setWordWrap(True)
        rl.addWidget(lbl)

        if conn:
            src = graph.nodes.get(conn.src_node)
            hint = f"← {src.title if src else conn.src_node}:{conn.src_port}"
            le = QLabel(hint)
            le.setStyleSheet(_CONN_HINT_STYLE)
            le.setWordWrap(True)
            rl.addWidget(le, 1)
        elif not port.editable:
            le = QLabel("(Connection Required)")
            le.setStyleSheet(_CONN_HINT_STYLE)
            rl.addWidget(le, 1)
        else:
            spec = _get_type_spec(port.port_type)
            if spec and spec.inspector_widget_factory is not None:

                def _notify(item=self._item, mw=self.main_window):
                    if item and mw and mw.scene:
                        mw.scene._after_node_mutation(item.node.id)
                        mw.scene._emit_graph_changed()

                def _commit(new_val, p=pname, pt=port):
                    old_val = pt.value
                    if old_val == new_val:
                        return
                    self._suppress_refresh = True
                    try:
                        self.main_window.scene.undo_stack.push(
                            PropertyCommand(self._item, p, old_val, new_val)
                        )
                    finally:
                        self._suppress_refresh = False

                try:
                    w = spec.inspector_widget_factory(
                        make_port_notify_proxy(port, _notify), on_commit=_commit
                    )
                except TypeError:
                    w = spec.inspector_widget_factory(make_port_notify_proxy(port, _notify))
                if w is not None:
                    w.setMaximumWidth(_MAX_WIDGET_W)
                    rl.addWidget(w, 1)
                    return row

            if port.port_type == "enum":
                v = port.value
                display = str(v) if v is not None else "Select..."
                text = display[:24] + "…" if len(display) > 25 else display
                btn = QPushButton(text)
                btn.setFixedHeight(22)
                btn.setMaximumWidth(_MAX_WIDGET_W)
                btn.setStyleSheet(NODE_ENUM_BTN_STYLE)
                btn.setProperty("widget_type", "enum")
                btn.clicked.connect(lambda _=False, p=pname, b=btn: self._on_enum_clicked(p, b))
                rl.addWidget(btn, 1)
            else:
                le = QLabel("(Connection Required)")
                le.setStyleSheet(_CONN_HINT_STYLE)
                rl.addWidget(le, 1)

        return row

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_title_finished(self) -> None:
        if not self._item or not self._title_edit:
            return
        new_t = self._title_edit.text().strip()
        current_display = self._item.node.display_name
        if new_t == current_display:
            return
        if not new_t:
            self._item.node.custom_name = None
        else:
            self._item.node.custom_name = new_t
        self._suppress_refresh = True
        try:
            self._item.update()
            if self.main_window.scene:
                self.main_window.scene.graph_changed.emit()
        finally:
            self._suppress_refresh = False

    def _on_lineedit_finished(self, edit: QLineEdit) -> None:
        pname = edit.property("port_name")
        if not pname or not self._item:
            return
        port = self._item.node.inputs.get(pname)
        if not port:
            return
        new_val = edit.text()
        old_val = edit.property("original_val")
        try:
            spec = _get_type_spec(port.port_type)
            is_same = (spec.values_equal(port.value, new_val) if spec and spec.values_equal
                       else str(port.value) == new_val)
        except (ValueError, TypeError):
            is_same = str(port.value) == new_val
        if is_same:
            return
        err = _validate_port_text(port.port_type, new_val)
        self._item.node.error_msg = err
        if err:
            log.error(f"[{self._item.node.title}] {err}")
            return
        self._suppress_refresh = True
        try:
            self.main_window.scene.undo_stack.push(PropertyCommand(self._item, pname, old_val, new_val))
        finally:
            self._suppress_refresh = False
        edit.setProperty("original_val", new_val)

    def _on_bool_clicked(self, pname: str, btn: QPushButton) -> None:
        if not self._item:
            return
        port = self._item.node.inputs.get(pname)
        if not port:
            return
        old_val = port.value
        new_val = not bool(old_val)
        self._suppress_refresh = True
        try:
            self.main_window.scene.undo_stack.push(PropertyCommand(self._item, pname, old_val, new_val))
            btn.setText("True" if new_val else "False")
        finally:
            self._suppress_refresh = False

    def _on_enum_clicked(self, pname: str, btn: QPushButton) -> None:
        if not self._item:
            return
        port = self._item.node.inputs.get(pname)
        if not port:
            return
        graph = self.main_window.scene.graph
        mw = self.main_window

        def _commit(new_val) -> None:
            old_val = port.value
            if old_val == new_val:
                return
            display = str(new_val) if new_val is not None else "Select..."
            btn.setText(display[:24] + "…" if len(display) > 25 else display)
            self._suppress_refresh = True
            try:
                self.main_window.scene.undo_stack.push(PropertyCommand(self._item, pname, old_val, new_val))
            finally:
                self._suppress_refresh = False

        if port.enum_filter and not port.enum_options:
            picker = get_file_picker("asset")
            if picker is not None:
                path = picker(mw, port.enum_filter, port.label or pname)
            else:
                ext_str = " ".join(f"*{e}" for e in port.enum_filter) if port.enum_filter else "*.*"
                path, _ = QFileDialog.getOpenFileName(mw, port.label or pname, "", f"Files ({ext_str})")
            if path:
                _commit(path)
        else:
            if port.enum_options is not None:
                options = port.enum_options
            elif port_uses_graph_variables(port):
                options = list((getattr(graph, "variables", {}) or {}).keys())
            else:
                assets = getattr(graph, "assets", []) or []
                ext = port.enum_filter or []
                options = [a for a in assets if not ext or os.path.splitext(a)[1].lower() in ext]
            dialog = GenericSelectionDialog(options, parent=mw, title=port.label or pname)
            _position_near_cursor(dialog)
            if dialog.exec() == GenericSelectionDialog.Accepted and dialog.selected_item:
                _commit(dialog.selected_item)

    def _browse_file(self, pname: str, edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select File", "", "All Files (*)")
        if path and self._item:
            port = self._item.node.inputs.get(pname)
            edit.setProperty("original_val", port.value if port else None)
            edit.setText(path)
            self._on_lineedit_finished(edit)


class NodeInspectorModularPanel(BasePanel):
    ID = "NodeInspectorDock"
    TITLE = "Node Inspector"
    DEFAULT_AREA = Qt.RightDockWidgetArea

    def __init__(self, main_window: MainWindow) -> None:
        super().__init__(main_window)
        self._widget = SelectedNodePanel(main_window)
        self.setWidget(self._widget)

    def setup(self) -> None:
        scene = self.main_window.scene
        if scene:
            scene.selectionChanged.connect(self._widget.refresh)
            scene.graph_changed.connect(self._widget.refresh)
        self._widget.refresh()

    def update_context(self, graph, scene) -> None:
        if self._active_scene:
            try:
                self._active_scene.selectionChanged.disconnect(self._widget.refresh)
                self._active_scene.graph_changed.disconnect(self._widget.refresh)
            except (TypeError, RuntimeError):
                pass

        self._active_scene = scene
        scene.selectionChanged.connect(self._widget.refresh)
        scene.graph_changed.connect(self._widget.refresh)
        self._widget.refresh()
