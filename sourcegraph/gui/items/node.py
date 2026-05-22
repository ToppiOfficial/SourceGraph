from __future__ import annotations
import os
from typing import Any
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsProxyWidget, QLineEdit, QWidget,
                                QHBoxLayout, QFileDialog, QComboBox, QGraphicsEllipseItem,
                                QPushButton, QApplication)
from PySide6.QtGui     import (QColor, QPen, QBrush, QFont, QPainter, QPainterPath, QFontMetrics)
from PySide6.QtCore    import Qt, QRectF, QPointF, QTimer

from sourcegraph.sys.node import BaseNode, Port, port_uses_graph_variables, _coerce
from sourcegraph.sys.registry import (
    get_color as _get_port_color,
    get_port_type_spec as _get_type_spec,
    get_default_registry as _get_registry,
    get_file_picker,
)
from sourcegraph.gui.theme import *
from sourcegraph.gui.widgets.basic_shapes import ShapeDrawer
from sourcegraph.gui.widgets.port_utils import port_is_node_editable as _port_is_editable
from sourcegraph.gui.logger import log
from sourcegraph.gui.commands import PropertyCommand, FoldCommand, ResizeNodeCommand
from sourcegraph.gui.constants import (
    DEFAULT_W, TITLE_H, ROW_H, PR, PAD, MIN_W,
    LABEL_MAXSPACE_GAP, PLUGIN_LABEL_H,
    NODE_ARC_R as _ARC_R, NODE_ARC_STEP as _ARC_STEP,
)
import math as _math


def _elide(s: str, n: int = 25) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


# -- Folded node arc geometry --------------------------------------------------

def _folded_height(n: int) -> float:
    """Minimum height for a folded node to distribute n ports along the border."""
    if n <= 1:
        return float(TITLE_H)
    r          = _ARC_R
    step       = r * _math.radians(_ARC_STEP)   # arc-length spacing ≈ 8.38 px
    corner_arc = _math.pi * r / 2.0             # quarter-circle arc length
    straight   = max(0.0, (n - 1) * step - 2.0 * corner_arc)
    return max(float(TITLE_H), 2.0 * r + straight)


def _folded_border_pos(idx: int, count: int, side: str, h: float, w: float):
    r          = _ARC_R
    corner_arc = _math.pi * r / 2.0
    straight   = max(0.0, h - 2.0 * r)
    total      = 2.0 * corner_arc + straight

    t_center = total / 2.0

    if count <= 1:
        x = 0.0
        y = h / 2.0
        if side == 'right':
            x = w - x
        return x, y

    # Evenly distribute ports across the full border length
    # Add padding so ports don't sit right on the corners
    padding = corner_arc * 0.5
    usable  = total - 2.0 * padding
    step    = usable / (count - 1)
    t       = padding + idx * step

    if t <= corner_arc:
        alpha = (t / corner_arc) * (_math.pi / 2.0)
        x = r - r * _math.sin(alpha)
        y = r - r * _math.cos(alpha)
    elif t <= corner_arc + straight:
        x = 0.0
        y = r + (t - corner_arc)
    else:
        alpha = ((t - corner_arc - straight) / corner_arc) * (_math.pi / 2.0)
        x = r - r * _math.cos(alpha)
        y = (h - r) + r * _math.sin(alpha)

    if side == 'right':
        x = w - x
    return x, y


class PortItem(QGraphicsEllipseItem):
    def __init__(self, port: Port, parent: QGraphicsItem) -> None:
        r = PR
        super().__init__(-r, -r, 2 * r, 2 * r, parent=parent)
        self.port = port
        self._base_color = QColor(_get_port_color(port.port_type))
        self._apply_color(self._base_color)
        self.setZValue(2)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CrossCursor)
        type_name = port.port_type.upper()
        self.setToolTip(f"{port.name} <{type_name}>")

    def set_highlight(self, enabled: bool, is_valid: bool = True) -> None:
        """Visual feedback when a wire is dragged over this port."""
        if enabled:
            color = QColor(COLOR_VALID) if is_valid else QColor(COLOR_INVALID)
            self.setPen(QPen(color, 2.5))
            self.setScale(1.3)
        else:
            self._apply_color(self._base_color)
            self.setScale(1.0)

    def _apply_color(self, c: QColor) -> None:
        self.setBrush(QBrush(c))
        border_color = c.darker(150)
        self.setPen(QPen(border_color, 1.0))

    def shape(self) -> QPainterPath:
        """Expands the clickable area for easier connection dragging."""
        path = QPainterPath()
        hit_r = PR * 2
        path.addEllipse(-hit_r, -hit_r, 2 * hit_r, 2 * hit_r)
        return path

    def scene_center(self) -> QPointF:
        """Scene-space centre of this port circle."""
        return self.scenePos()

    def hoverEnterEvent(self, event):
        self._apply_color(self._base_color.lighter(150))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._apply_color(self._base_color)
        super().hoverLeaveEvent(event)

    def set_connected_color(self, source_port_type: str | None) -> None:
        """Update port color to match the connected source port type.

        When connected, ANY type ports take on the color of the source port.
        When disconnected, they revert to their original base color.
        """
        if source_port_type is not None and self.port.port_type == "any":
            color = QColor(_get_port_color(source_port_type))
            self._base_color = color
            self._apply_color(color)
        else:
            self._base_color = QColor(_get_port_color(self.port.port_type))
            self._apply_color(self._base_color)


class ResizeHandle(QGraphicsItem):
    """Small triangle in the bottom-right corner for horizontal resizing."""
    def __init__(self, parent: NodeItem):
        super().__init__(parent)
        self.setCursor(Qt.SizeHorCursor)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setZValue(10)
        self._start_w = DEFAULT_W
        self._disabled_items = []

    def boundingRect(self):
        return QRectF(-20, -20, 20, 20)

    def shape(self):
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(-10, 0)
        path.lineTo(0, -10)
        path.closeSubpath()
        return path

    def paint(self, painter, option, widget=None):
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(FG_DIM))
        path = QPainterPath()
        path.moveTo(0, 0)
        path.lineTo(-10, 0)
        path.lineTo(0, -10)
        path.closeSubpath()
        painter.drawPath(path)

    def mousePressEvent(self, event):
        p = self.parentItem()
        if p:
            self._start_w = p._w
            self._start_h = p._h
            self._disabled_items = []
            sc = self.scene()
            if sc:
                for item in sc.selectedItems():
                    if item.flags() & QGraphicsItem.ItemIsMovable:
                        item.setFlag(QGraphicsItem.ItemIsMovable, False)
                        self._disabled_items.append(item)
            p.setFlag(QGraphicsItem.ItemIsMovable, False)
            if p not in self._disabled_items:
                self._disabled_items.append(p)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        for item in self._disabled_items:
            item.setFlag(QGraphicsItem.ItemIsMovable, True)
        self._disabled_items = []

        p = self.parentItem()
        if p and (abs(p._w - self._start_w) > 1.0 or abs(p._h - self._start_h) > 1.0):
            sc = p.scene()
            if sc:
                sc.undo_stack.push(ResizeNodeCommand(p, self._start_w, self._start_h, p._w, p._h))
        super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self.parentItem():
            p = self.parentItem()
            if getattr(p, "_is_resizing", False):
                return super().itemChange(change, value)
            x = max(DEFAULT_W, value.x())
            y = max(p._calculate_height(), value.y())
            p.on_handle_moved(QPointF(x, y))
            return QPointF(x, y)
        return super().itemChange(change, value)


class NodeItem(QGraphicsItem):
    def __init__(self, node: BaseNode) -> None:
        super().__init__()
        self.node = node
        self._port_items: dict[str, PortItem]              = {}
        self._output_port_names: list[str]                 = []
        self._proxies:    dict[str, QGraphicsProxyWidget]  = {}
        self._port_widgets: dict[str, QWidget]             = {}
        # Maps input port name -> source Port object when connected, else None.
        # Populated by _sync_connection_states; avoids graph queries inside paint().
        self._conn_cache: dict[str, Any | None]            = {}

        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptDrops(True)

        self._is_resizing = False
        self._is_running  = False
        self._fold_press_pos = None  # Track press position in fold indicator area
        node_default_w = getattr(node, 'default_width', None) or DEFAULT_W
        self._w = node.width if node.width is not None else node_default_w

        _src = _get_registry().get_source(node.__class__.__name__)
        self._plugin_source: str | None = _src[7:] if (_src and _src.startswith("plugin:")) else None

        # For folded nodes, always calculate appropriate folded height
        # Ignore saved height as it might be from unfolded state
        if self.node.folded:
            self._h = self._calculate_height()
        else:
            calc_h = self._calculate_height()
            self._h = max(calc_h, node.height) if node.height is not None else calc_h

        # Height saved before folding so unfolding restores user-resized dimensions.
        self._unfolded_height: float | None = None

        # Resets any nodes that have a big of space through either external factor or old versions.
        if self.node.label_width is not None and self.node.label_width > LABEL_MAXSPACE_GAP:
            self.node.label_width = None

        self._build()
        self._update_ports()
        self._layout_rows = self.layout_row_signature()
        self.setPos(node.x, node.y)

        self.handle = ResizeHandle(self)
        self.handle.setPos(self._w, self._h)
        
        if self.node.folded or not getattr(self.node, 'allow_folding', True):
            self.handle.setVisible(False)

    def on_handle_moved(self, pos: QPointF) -> None:
        self.resize_to(pos.x(), pos.y())

    def set_running(self, v: bool) -> None:
        self._is_running = v
        self.update()

    def _get_fold_indicator_rect(self) -> QRectF:
        """Get the clickable area for the fold indicator."""
        text_height = self._h if self.node.folded else TITLE_H
        # Position indicator on the left side of title
        return QRectF(PAD, 0, 20, text_height)

    def resize_to(self, w: float, h: float = None, lbl_w: float = None) -> None:
        if self.node.folded:
            self._w = max(DEFAULT_W, w)
            self.node.width = self._w
            self._unfolded_height = h
            self.node.height = h
            self.prepareGeometryChange()
            self._update_ports()
            sc = self.scene()
            if sc:
                sc.refresh_connections(self)
            self.update()
            return
        self._is_resizing = True
        self.prepareGeometryChange()
        self._w = max(DEFAULT_W, w)
        self.node.width = self._w
        if h is not None:
            self._h = max(self._calculate_height(), h)
            self.node.height = self._h
        if lbl_w is not None:
            # Only set if it's a manual override (significantly different from ideal)
            ideal = self._calculate_ideal_label_width()
            if abs(lbl_w - ideal) > 2.0:
                self.node.label_width = max(20, lbl_w)
            
        self._update_ports()
        self.handle.setPos(self._w, self._h)
        sc = self.scene()
        if sc:
            sc.refresh_connections(self)
        self.update()
        self._is_resizing = False

    # -- construction ----------------------------------------------------------

    def _calculate_height(self) -> float:
        if self.node.folded:
            # Calculate dynamic height based on arc spacing for folded nodes
            visible_outputs = sum(1 for p in self.node.outputs.values() if p.allow_connection)
            visible_inputs = sum(1 for p in self.node.inputs.values()
                               if p.allow_connection)
            return _folded_height(max(visible_outputs, visible_inputs))
        h = TITLE_H
        for p in self.node.outputs.values():
            if p.allow_connection or getattr(p, "label", None):
                h += ROW_H
        below_extra = 0
        for p in self.node.inputs.values():
            is_editable = _port_is_editable(p.port_type) and p.editable
            has_custom = self.node.has_gui_builder(p.name)
            full_row = getattr(p, 'full_row', False)
            below_flag = getattr(p, 'below_ports', False)
            port_rh = getattr(p, 'row_height', None) or ROW_H
            if not (is_editable or has_custom or full_row or p.allow_connection):
                continue
            if full_row and not p.allow_connection:
                h += port_rh
            elif full_row and p.allow_connection:
                h += port_rh if (is_editable or has_custom) else ROW_H
            elif below_flag:
                h += ROW_H
                if is_editable or has_custom:
                    below_extra += port_rh
            else:
                h += ROW_H
        h += below_extra
        base = max(h, TITLE_H + ROW_H) + PAD
        if getattr(self, '_plugin_source', None):
            base += PLUGIN_LABEL_H
        return base

    def _calculate_ideal_label_width(self) -> float:
        """Calculate the width needed for the longest visible input label."""
        if hasattr(self, "_cached_ideal_lbl_w"):
            return self._cached_ideal_lbl_w
            
        metrics = QFontMetrics(QFont("Segoe UI", 8))
        max_w = 0
        for name, port in self.node.inputs.items():
            is_editable = _port_is_editable(port.port_type) and port.editable
            has_custom = self.node.has_gui_builder(name)
            full_row = getattr(port, 'full_row', False)
            if not (is_editable or has_custom or full_row or port.allow_connection):
                continue
            if full_row:
                continue
            
            display = port.label or name
            w = metrics.horizontalAdvance(display)
            if w > max_w:
                max_w = w
        
        self._cached_ideal_lbl_w = max(LABEL_MAXSPACE_GAP, max_w)
        return self._cached_ideal_lbl_w

    def layout_row_signature(self) -> tuple[tuple[str, str], ...]:
        """Rows that participate in layout; used to detect port/widget structure drift."""
        rows: list[tuple[str, str]] = []
        for name, p in self.node.outputs.items():
            if p.allow_connection:
                rows.append(("o", name))
        for name, p in self.node.inputs.items():
            if (_port_is_editable(p.port_type) and p.editable) or self.node.has_gui_builder(name) or getattr(p, 'full_row', False) or p.allow_connection:
                rows.append(("i", name))
        return tuple(rows)

    def _row_cy(self, i: int) -> float:
        return TITLE_H + i * ROW_H + ROW_H / 2

    def _build(self) -> None:
        row_idx = 0
        self._port_items.clear()
        self._output_port_names.clear()

        if self.node.folded:
            # Use arc positioning for folded node ports
            visible_outputs = [(n, p) for n, p in self.node.outputs.items() if p.allow_connection]
            visible_inputs  = [(n, p) for n, p in self.node.inputs.items()
                               if p.allow_connection]

            # Calculate arc-based height for positioning but keep node at TITLE_H
            arc_h = _folded_height(max(len(visible_outputs), len(visible_inputs)))

            for i, (name, port) in enumerate(visible_outputs):
                pi = PortItem(port, self)
                x, y = _folded_border_pos(i, len(visible_outputs), "right", arc_h, self._w)
                pi.setPos(x, y)
                self._port_items[name] = pi
            # _output_port_names must include ALL output names (visible or not) for _update_ports
            for name in self.node.outputs:
                self._output_port_names.append(name)

            for i, (name, port) in enumerate(visible_inputs):
                pi = PortItem(port, self)
                x, y = _folded_border_pos(i, len(visible_inputs), "left", arc_h, self._w)
                pi.setPos(x, y)
                self._port_items[name] = pi
            return  # no proxy widgets when folded

        # Outputs first (top rows)
        for name, port in self.node.outputs.items():
            if port.allow_connection:
                pi = PortItem(port, self)
                pi.setPos(self._w, self._row_cy(row_idx))
                self._port_items[name] = pi
                row_idx += 1
            self._output_port_names.append(name)

        # Normal rows and full_row ports
        below_ports_queue: list[tuple[str, "Port"]] = []
        current_y = TITLE_H + row_idx * ROW_H
        for name, port in self.node.inputs.items():
            is_editable = _port_is_editable(port.port_type) and port.editable
            has_custom = self.node.has_gui_builder(name)
            full_row = getattr(port, 'full_row', False)
            below_flag = getattr(port, 'below_ports', False)
            port_rh = getattr(port, 'row_height', None) or ROW_H

            if not (is_editable or has_custom or full_row or port.allow_connection):
                continue

            if below_flag:
                if port.allow_connection:
                    pi = PortItem(port, self)
                    pi.setPos(0, current_y + ROW_H / 2)
                    self._port_items[name] = pi
                if is_editable or has_custom:
                    below_ports_queue.append((name, port))
                current_y += ROW_H
            elif full_row and not port.allow_connection:
                # No port circle; widget spans full width (only if not connectable)
                proxy = self._build_input_widget(name, port, current_y)
                if proxy:
                    self._proxies[name] = proxy
                current_y += port_rh
            elif full_row and port.allow_connection:
                pi = PortItem(port, self)
                pi.setPos(0, current_y + port_rh / 2)
                self._port_items[name] = pi
                if is_editable or has_custom:
                    proxy = self._build_input_widget(name, port, current_y)
                    if proxy:
                        self._proxies[name] = proxy
                    current_y += port_rh
                else:
                    current_y += ROW_H
            else:
                if port.allow_connection:
                    pi = PortItem(port, self)
                    pi.setPos(0, current_y + ROW_H / 2)
                    self._port_items[name] = pi
                if is_editable or has_custom:
                    proxy = self._build_input_widget(name, port, current_y)
                    if proxy:
                        self._proxies[name] = proxy
                current_y += ROW_H

        for name, port in below_ports_queue:
            port_rh = getattr(port, 'row_height', None) or ROW_H
            proxy = self._build_input_widget(name, port, current_y)
            if proxy:
                self._proxies[name] = proxy
            current_y += port_rh

    def _build_input_widget(self, name: str, port, current_y: float):
        """Create and return the proxy widget for an editable input port, or None."""
        full_row = getattr(port, 'full_row', False)
        below_flag = getattr(port, 'below_ports', False)
        span_full = full_row or below_flag

        # Ask the node for a custom widget first (registered builder or override).
        widget = self.node.create_widget_for_port(port)
        if widget is not None:
            self._port_widgets[name] = widget
            self._connect_widget_events(name, widget)
            if span_full:
                proxy = QGraphicsProxyWidget(self)
                proxy.setWidget(widget)
                proxy.setPos(PAD / 2, current_y + 2)
                return proxy
            return self._create_proxy(widget, current_y)

        # Fall back to a standard widget based on port type.
        container = QWidget()
        container.setAttribute(Qt.WA_StyledBackground)
        container.setObjectName("InputContainer")
        container.setStyleSheet(
            f"#InputContainer {{ background-color: transparent; border: 0px solid {BORDER_LIGHT}; }}"
        )
        widget = self._create_basic_widget(port, container)
        if widget is None:
            return None
        layout = QHBoxLayout(container)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(2)
        layout.addWidget(widget)
        self._port_widgets[name] = widget
        self._connect_widget_events(name, widget)
        if span_full:
            proxy = QGraphicsProxyWidget(self)
            proxy.setWidget(container)
            proxy.setPos(PAD / 2, current_y + 2)
            return proxy
        return self._create_proxy(container, current_y)
    
    def _create_basic_widget(self, port, parent=None):
        """Create basic widgets based on port type using theme styles."""
        from sourcegraph.sys.registry import make_port_notify_proxy
        node_id = self.node.id
        def _notify(nid=node_id):
            sc = self.scene()
            if sc:
                sc._after_node_mutation(nid)
                sc._emit_graph_changed()

        # Non-bool ports with an explicit options list use the enum canvas widget.
        if port.enum_options is not None and port.port_type != "bool":
            enum_spec = _get_type_spec("enum")
            if enum_spec and enum_spec.canvas_widget_factory:
                return enum_spec.canvas_widget_factory(make_port_notify_proxy(port, _notify), parent)

        spec = _get_type_spec(port.port_type)
        if spec and spec.canvas_widget_factory is not None:
            return spec.canvas_widget_factory(make_port_notify_proxy(port, _notify), parent)
        return None

    def _create_proxy(self, container: QWidget, current_y: float) -> QGraphicsProxyWidget:
        """Helper to finalize proxy placement."""
        lbl_w = self.node.label_width or self._calculate_ideal_label_width()
        x_pos = PR + PAD + lbl_w + 2
        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(container)
        proxy.setPos(x_pos, current_y + 3)
        return proxy

    def _populate_asset_combo(self, combo: QComboBox, port) -> None:
        """Fill combo with graph assets, optionally filtered by port.enum_filter."""
        assets = getattr(self.node.graph, "assets", [])
        ext_filter = port.enum_filter  # e.g. [".srcsubgraph"] or [".dmx", ".smd"]
        for asset_path in assets:
            if ext_filter:
                if os.path.splitext(asset_path)[1].lower() not in ext_filter:
                    continue
            combo.addItem(os.path.basename(asset_path), asset_path)

        if port.value:
            norm_val = os.path.normpath(str(port.value))
            for i in range(combo.count()):
                if os.path.normpath(str(combo.itemData(i))) == norm_val:
                    combo.setCurrentIndex(i)
                    break

    def _populate_variable_combo(self, combo: QComboBox, port) -> None:
        """Fill combo with graph variables."""
        vars_dict = getattr(self.node.graph, "variables", {})
        for var_name in vars_dict.keys():
            combo.addItem(var_name, var_name)

        if port.value:
            val_str = str(port.value)
            idx = combo.findData(val_str)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    # -- event handlers --------------------------------------------------------

    def _on_edit_finished(self, port_name: str, edit: QLineEdit) -> None:
        sc = self.scene()
        if sc and getattr(sc, "_execution_locked", False):
            return
        new_val = edit.text()
        port = self.node.inputs.get(port_name)
        if not port:
            return

        old_val = edit.property("original_val")

        # Skip if unchanged - compare against value when editing started (old_val), not current
        # port.value, which textChanged may have already updated to new_val
        try:
            spec = _get_type_spec(port.port_type)
            is_same = (spec.values_equal(old_val, new_val) if spec and spec.values_equal
                       else str(old_val if old_val is not None else "") == new_val)
        except (ValueError, TypeError):
            is_same = str(old_val if old_val is not None else "") == new_val

        if is_same:
            return

        # Validate and route error to the application console
        error = self._validate_value(port.port_type, new_val)
        self.node.error_msg = error
        self.setToolTip(error or "")
        if error:
            log.error(f"[{self.node.title}] {error}")
        self.update()

        sc = self.scene()
        if sc:
            # Update the cache for the next edit cycle
            edit.setProperty("original_val", new_val)
            sc.undo_stack.push(PropertyCommand(self, port_name, old_val, new_val))

    def _on_combo_changed(self, port_name: str, combo: QComboBox) -> None:
        sc = self.scene()
        if sc and getattr(sc, "_execution_locked", False):
            return
        new_val = combo.itemData(combo.currentIndex())
        port = self.node.inputs.get(port_name)
        if not port or port.value == new_val:
            return
        if sc:
            sc.undo_stack.push(PropertyCommand(self, port_name, port.value, new_val))

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasText():
            event.accept()

    def dropEvent(self, event) -> None:
        path = event.mimeData().text()
        for name, port in self.node.inputs.items():
            if port.port_type == "enum" and port.enum_options is None:
                proxy = self._proxies.get(name)
                if proxy:
                    combo = proxy.widget().findChild(QComboBox)
                    if combo:
                        norm = os.path.normpath(path)
                        for i in range(combo.count()):
                            if os.path.normpath(str(combo.itemData(i))) == norm:
                                combo.setCurrentIndex(i)
                                event.accept()
                                return
        event.ignore()

    # -- validation ------------------------------------------------------------

    def _validate_value(self, port_type: str, text: str) -> str | None:
        if not text:
            return None
        spec = _get_type_spec(port_type)
        return spec.validate_text(text) if spec and spec.validate_text else None

    def _browse_file(self, port_name: str, edit: QLineEdit) -> None:
        path, _ = QFileDialog.getOpenFileName(None, "Select File", "", "All Files (*)")
        if path:
            edit.setText(path)
            QTimer.singleShot(0, lambda: self._on_edit_finished(port_name, edit))

    # -- public interface ------------------------------------------------------

    def _sync_enum_port_to_combo(self, combo: QComboBox, port) -> None:
        """Select the combo row for port.value (paths normalized for asset entries)."""
        pv = "" if port.value is None else str(port.value)
        idx = combo.findData(pv)
        if idx < 0 and pv and combo.count() > 0:
            norm_val = os.path.normpath(pv).replace("\\", "/")
            for i in range(combo.count()):
                data = combo.itemData(i)
                if data is None:
                    continue
                if os.path.normpath(str(data)).replace("\\", "/") == norm_val:
                    idx = i
                    break
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setCurrentIndex(-1)

    def refresh(self) -> None:
        """Repopulate dynamic enums, reconcile port values, then refresh derived title/labels."""
        self.node.reconcile_graph_bound_inputs()
        
        # Update widgets using the widget factory system
        for pname, widget in self._port_widgets.items():
            port = self.node.inputs.get(pname)
            if not port:
                continue
            
            # Let the widget factory handle updates
            self._update_widget_value(widget, port)

        if hasattr(self.node, "on_property_changed"):
            self.node.on_property_changed()

        self._sync_connection_states()
        for proxy in self._proxies.values():
            if proxy.widget() is not None:
                proxy.widget().update()
            proxy.update()
        self.update()

    def _update_widget_value(self, widget: QWidget, port: Port):
        """Update widget value based on port type and widget type."""
        if callable(getattr(widget, 'refresh_value', None)):
            widget.refresh_value(port.value)
            return
        if isinstance(widget, QLineEdit):
            v = port.value
            val_str = f"{v:g}" if isinstance(v, float) else str(v) if v is not None else ""
            if widget.text() != val_str:
                widget.setText(val_str)
                widget.setProperty("original_val", port.value)
        
        elif widget.property("widget_type") == "number":
            edit = widget.number_edit
            v = port.value
            val_str = f"{v:g}" if isinstance(v, float) else str(v) if v is not None else ""
            if edit.text() != val_str:
                edit.setText(val_str)
                edit.setProperty("original_val", port.value)

        elif widget.property("widget_type") == "file":
            edit = widget.file_edit
            v = port.value
            val_str = str(v) if v is not None else ""
            if edit.text() != val_str:
                edit.setText(val_str)
                edit.setProperty("original_val", port.value)

        elif isinstance(widget, QComboBox):
            # Handle combo box updates
            widget.blockSignals(True)
            if port.enum_options is None:
                widget.clear()
                if port_uses_graph_variables(port):
                    self._populate_variable_combo(widget, port)
                else:
                    self._populate_asset_combo(widget, port)
            self._sync_enum_port_to_combo(widget, port)
            widget.blockSignals(False)
        
        elif isinstance(widget, QPushButton):
            # Handle boolean toggle and enum button updates
            raw = port.value
            if widget.property("widget_type") == "enum":
                widget.setText(_elide(str(raw) if raw is not None else "Select...", 25))
            else:
                is_true = str(raw).lower() in ("true", "1", "yes")
                widget.setText(f"{'True' if is_true else 'False'}")

    def _connect_widget_events(self, name: str, widget: QWidget):
        """Connect widget events to handle value changes."""
        if isinstance(widget, QLineEdit):
            # Real-time feedback (non-undoable)
            widget.textChanged.connect(
                lambda text: self._on_widget_changed(name, text)
            )
            # Finalized state (undoable)
            widget.editingFinished.connect(
                lambda: self._on_edit_finished(name, widget)
            )
        elif widget.property("widget_type") == "number":
            edit = widget.number_edit
            # Real-time feedback (non-undoable)
            edit.textChanged.connect(
                lambda text: self._on_widget_changed(name, text)
            )
            # Finalized state (undoable)
            edit.editingFinished.connect(
                lambda: self._on_edit_finished(name, edit)
            )
            # Buttons
            widget.btn_minus.clicked.connect(
                lambda: self._on_number_increment(name, -1)
            )
            widget.btn_plus.clicked.connect(
                lambda: self._on_number_increment(name, 1)
            )
        elif widget.property("widget_type") == "enum":
            widget.clicked.connect(
                lambda: self._on_enum_clicked(name)
            )
        elif widget.property("widget_type") == "file":
            edit = widget.file_edit
            edit.textChanged.connect(
                lambda text: self._on_widget_changed(name, text)
            )
            edit.editingFinished.connect(
                lambda: self._on_edit_finished(name, edit)
            )
            widget.browse_btn.clicked.connect(
                lambda: self._browse_file(name, edit)
            )
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(
                lambda index: self._on_combo_changed(name, widget)
            )
        elif isinstance(widget, QPushButton):
            widget.clicked.connect(
                lambda: self._on_bool_toggle(name)
            )
    
    def _on_enum_clicked(self, port_name: str):
        """Show selection dialog for ENUM ports."""
        port = self.node.inputs.get(port_name)
        if not port:
            return
            
        options = []
        if port.enum_options is not None:
            options = [str(o) for o in port.enum_options]
        elif self.node.graph:
            if port_uses_graph_variables(port):
                options = sorted(list(self.node.graph.variables.keys()))
            else:
                # Assets
                assets = getattr(self.node.graph, "assets", [])
                ext_filter = port.enum_filter
                if ext_filter:
                    options = [f for f in assets if os.path.splitext(f)[1].lower() in ext_filter]
                else:
                    options = assets
        
        # These imports are inline to avoid circular import via file_search_dialog -> main_window
        from sourcegraph.gui.menu.file_search_dialog import GenericSelectionDialog
        from sourcegraph.gui.main_window import MainWindow
        mw = next((w for w in QApplication.topLevelWidgets() if isinstance(w, MainWindow)), None)

        # For asset ports, use specialized file search dialog if filter exists
        if port.enum_filter and not port.enum_options:
            picker = get_file_picker("asset")
            if picker is not None:
                path = picker(mw, port.enum_filter, port.label or port_name)
            else:
                ext_str = " ".join(f"*{e}" for e in port.enum_filter) if port.enum_filter else "*.*"
                path, _ = QFileDialog.getOpenFileName(mw, port.label or port_name, "", f"Files ({ext_str})")
            if path:
                self._update_port_value(port_name, path)
        else:
            dialog = GenericSelectionDialog(options, parent=mw, title=port.label or port_name)
            if dialog.exec() == GenericSelectionDialog.Accepted and dialog.selected_item:
                self._update_port_value(port_name, dialog.selected_item)

    def _update_port_value(self, port_name: str, new_val: Any):
        """Push a property change command for the given port."""
        sc = self.scene()
        if sc and getattr(sc, "_execution_locked", False):
            return
        port = self.node.inputs.get(port_name)
        if not port or port.value == new_val:
            return
        if sc:
            sc.undo_stack.push(PropertyCommand(self, port_name, port.value, new_val))

    def _on_widget_changed(self, port_name: str, new_value: str):
        """Handle widget value changes."""
        port = self.node.inputs.get(port_name)
        if not port:
            return
        
        spec = _get_type_spec(port.port_type)
        try:
            port.value = spec.coerce_text(new_value) if spec and spec.coerce_text else new_value
        except (ValueError, TypeError):
            pass
        
        # Trigger graph update - skip for dynamic ports to avoid refresh mid-type
        scene = self.scene()
        if scene and not (port and port.is_dynamic):
            scene._after_node_mutation(self.node.id)
            scene._emit_graph_changed()
    
    def _on_bool_toggle(self, port_name: str):
        """Handle boolean toggle clicks."""
        sc = self.scene()
        if sc and getattr(sc, "_execution_locked", False):
            return
        port = self.node.inputs.get(port_name)
        if not port:
            return

        old_val = port.value
        current = str(old_val).lower() in ("true", "1", "yes")
        new_val = not current

        if sc:
            sc.undo_stack.push(PropertyCommand(self, port_name, old_val, new_val))

    def _on_number_increment(self, port_name: str, direction: int):
        """Handle numeric increment/decrement buttons."""
        sc = self.scene()
        if sc and getattr(sc, "_execution_locked", False):
            return
        port = self.node.inputs.get(port_name)
        if not port:
            return
        
        old_val = port.value
        try:
            current = float(old_val or 0)
        except (ValueError, TypeError):
            current = 0.0
            
        step = port.number_increment
        if step is None:
            step = 1.0 if port.port_type == "int" else 0.1

        new_val = current + (direction * step)

        if port.port_type == "int":
            new_val = int(round(new_val))
        else:
            # Avoid floating point precision issues for small steps
            new_val = round(new_val, 7)
            
        sc = self.scene()
        if sc:
            sc.undo_stack.push(PropertyCommand(self, port_name, old_val, new_val))

    def refresh_ports(self) -> None:
        """Full rebuild of port items and proxies (used after dynamic port changes)."""
        if hasattr(self, "_cached_ideal_lbl_w"):
            del self._cached_ideal_lbl_w
        self.prepareGeometryChange()

        for pi in self._port_items.values():
            pi.setParentItem(None)
            if pi.scene():
                pi.scene().removeItem(pi)

        for proxy in self._proxies.values():
            proxy.setParentItem(None)
            if proxy.scene():
                proxy.scene().removeItem(proxy)
            if proxy.widget():
                proxy.widget().deleteLater()

        self._port_items.clear()
        self._proxies.clear()
        self._output_port_names.clear()
        self._port_widgets.clear()

        self._h = self._calculate_height()
        self._build()
        self.handle.setPos(self._w, self._h)

        sc = self.scene()
        if sc:
            self._sync_connection_states()

            # Remove visual items whose connection is gone from the graph or whose
            # port no longer exists.  Both cases arise after dynamic port renumbering:
            # the old Connection objects in _conn_items reference stale port names,
            # and even though the port slot may still exist (as an empty placeholder)
            # the backing graph connection has been replaced by a renumbered one.
            graph_conn_keys = {
                (c.src_node, c.src_port, c.dst_node, c.dst_port)
                for c in sc.graph.connections
            }
            dead = []
            for conn, ci in sc._conn_items:
                involves_self = (conn.src_node == self.node.id or
                                 conn.dst_node == self.node.id)
                port_missing = (
                    (conn.src_node == self.node.id and conn.src_port not in self.node.outputs) or
                    (conn.dst_node == self.node.id and conn.dst_port not in self.node.inputs)
                )
                orphaned = involves_self and (
                    conn.src_node, conn.src_port, conn.dst_node, conn.dst_port
                ) not in graph_conn_keys
                if port_missing or orphaned:
                    dead.append(ci)
            for ci in dead:
                for c, item in list(sc._conn_items):
                    if item is ci:
                        dni = sc._node_items.get(c.dst_node)
                        if dni and c.dst_node != self.node.id:
                            dni.set_port_connected(c.dst_port, False)
                        break
                sc._delete_conn(ci, push_undo=False)

            # Re-materialise connections that were renumbered: after the dead-item
            # cleanup above the renumbered connections exist in graph.connections
            # but have no corresponding visual item yet.
            tracked = {
                (c.src_node, c.src_port, c.dst_node, c.dst_port)
                for c, _ in sc._conn_items
            }
            for conn in sc.graph.connections:
                if conn.src_node == self.node.id or conn.dst_node == self.node.id:
                    key = (conn.src_node, conn.src_port, conn.dst_node, conn.dst_port)
                    if key not in tracked:
                        sc._materialise_conn(conn)

            sc.refresh_connections(self)
            sc.graph_changed.emit()

        self._layout_rows = self.layout_row_signature()
        self._update_ports()
        self.update()

    def _sync_connection_states(self) -> None:
        """Syncs port colors, proxy visibility, and connection cache with current graph."""
        sc = self.scene()
        if not (sc and hasattr(sc, "graph")):
            return
        self._conn_cache.clear()
        for pname in self.node.inputs:
            conn = sc.graph.get_input_connection(self.node.id, pname)
            if conn:
                src_node = sc.graph.nodes.get(conn.src_node)
                src_port = src_node.outputs.get(conn.src_port) if src_node else None
                src_type = src_port.port_type if src_port else None
                self._conn_cache[pname] = src_port  # None if src dropped from graph
                self.set_port_connected(pname, True, src_type)
            else:
                self._conn_cache[pname] = None
                self.set_port_connected(pname, False)

    def _update_ports(self) -> None:
        """Keep output ports and proxy widgets aligned after a resize."""
        if self.node.folded:
            # In folded state, recalculate arc positions when width changes
            visible_outputs = [(n, p) for n, p in self.node.outputs.items() if p.allow_connection]
            visible_inputs  = [(n, p) for n, p in self.node.inputs.items()
                               if p.allow_connection]
            
            # Calculate arc-based height for positioning but keep node at TITLE_H
            arc_h = _folded_height(max(len(visible_outputs), len(visible_inputs)))
            
            # Update output ports with new arc positions
            for i, (name, port) in enumerate(visible_outputs):
                pi = self._port_items.get(name)
                if pi:
                    x, y = _folded_border_pos(i, len(visible_outputs), "right", arc_h, self._w)
                    pi.setPos(x, y)

            # Update input ports with new arc positions
            for i, (name, port) in enumerate(visible_inputs):
                pi = self._port_items.get(name)
                if pi:
                    x, y = _folded_border_pos(i, len(visible_inputs), "left", arc_h, self._w)
                    pi.setPos(x, y)
            return
        for name in self._output_port_names:
            pi = self._port_items.get(name)
            if pi:
                pi.setPos(self._w, pi.y())

        lbl_w = self.node.label_width or self._calculate_ideal_label_width()
        stretch_proxies: list[tuple[float, str, QGraphicsProxyWidget]] = []

        for name, proxy in self._proxies.items():
            port = self.node.inputs.get(name)
            span_full = port and (getattr(port, 'full_row', False) or getattr(port, 'below_ports', False))
            if span_full:
                proxy.setPos(PAD / 2, proxy.y())
                if getattr(port, 'row_stretch', False):
                    stretch_proxies.append((proxy.y(), name, proxy))
                else:
                    port_rh = getattr(port, 'row_height', None) or ROW_H
                    proxy.widget().setFixedHeight(max(10, port_rh - 4))
            else:
                proxy.setPos(PR + PAD + lbl_w + 2, proxy.y())

            # Symmetric PAD/2 margins for span-full; normal right gap otherwise
            if span_full:
                proxy.widget().setFixedWidth(max(10, int(self._w - PAD)))
            else:
                right_gap = 4 if not self._output_port_names else (PR + 2)
                proxy.widget().setFixedWidth(max(10, int(self._w - proxy.x() - right_gap)))

        # Distribute available height equally among stretch proxies
        if stretch_proxies:
            stretch_proxies.sort(key=lambda t: t[0])
            first_y = stretch_proxies[0][0]
            n = len(stretch_proxies)
            available = max(n * ROW_H, self._h - first_y - PAD)
            each_h = available / n
            for i, (_, name, proxy) in enumerate(stretch_proxies):
                proxy.setPos(proxy.x(), first_y + i * each_h)
                proxy.widget().setFixedHeight(max(10, int(each_h) - 4))

    def port_item(self, name: str) -> PortItem | None:
        return self._port_items.get(name)

    def set_port_connected(self, port_name: str, connected: bool, source_port_type: str | None = None) -> None:
        proxy = self._proxies.get(port_name)
        if proxy:
            if not self.node.has_gui_builder(port_name):
                proxy.setVisible(not connected)
        port_item = self._port_items.get(port_name)
        if port_item:
            if connected and source_port_type is not None:
                port_item.set_connected_color(source_port_type)
            else:
                port_item.set_connected_color(None)
        self.update()

    # -- QGraphicsItem interface -----------------------------------------------

    def boundingRect(self) -> QRectF:
        # Buffer for stacked outlines (up to ~5px)
        return QRectF(-PR, -20, self._w + 2 * PR, self._h + 25)

    def _has_required_error(self) -> bool:
        """Returns True if any required input is empty and not connected."""
        sc = self.scene()
        for pname, port in self.node.inputs.items():
            if not port.required:
                continue
            if sc and hasattr(sc, "graph"):
                if sc.graph.get_input_connection(self.node.id, pname):
                    continue  # connected - satisfied
            val = port.value
            if val is None or str(val).strip() == "":
                return True
        return False

    def paint(self, painter: QPainter, option, widget=None) -> None:
        # Use proportional roundness for folded nodes based on port count
        if self.node.folded:
            r = min(self._h / 2.0, float(_ARC_R))
        else:
            r = 10
            
        body = QRectF(0, 0, self._w, self._h)
        base_color = QColor(self.node.color)

        painter.save()

        body_path = QPainterPath()
        body_path.addRoundedRect(body, r, r)
        painter.setClipPath(body_path)

        # Body background - always dark neutral
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(NODE_BG))
        painter.drawRect(body)

        # Title bar - use dynamic height for folded nodes to accommodate arc spacing
        header_color = base_color.darker(HEADER_DARKNESS)
        painter.setBrush(header_color)
        if self.node.folded:
            # Use the full height for folded nodes to accommodate the arc
            header_rect = QRectF(0, 0, self._w, self._h)
        else:
            header_rect = QRectF(0, 0, self._w, TITLE_H)
        painter.drawRect(header_rect)

        # This is dumb.
        painter.restore()

        pen_w = 1.0

        painter.setPen(QPen(QColor(Qt.black), pen_w))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(body, r, r)

        current_offset = 0

        if self.isSelected():
            current_offset += pen_w
            painter.setPen(QPen(QColor(ACCENT), pen_w))
            painter.drawRoundedRect(body.adjusted(-current_offset, -current_offset, current_offset, current_offset),
                                     r + current_offset, r + current_offset)

        if self._is_running:
            current_offset += pen_w
            painter.setPen(QPen(QColor("#f1c40f"), pen_w))
            painter.drawRoundedRect(body.adjusted(-current_offset, -current_offset, current_offset, current_offset),
                                     r + current_offset, r + current_offset)

        if self.node.error_msg or self._has_required_error():
            current_offset += pen_w
            painter.setPen(QPen(QColor(COLOR_INVALID), pen_w))
            painter.drawRoundedRect(body.adjusted(-current_offset, -current_offset, current_offset, current_offset),
                                     r + current_offset, r + current_offset)

        # Fold indicator and title text
        text_height = self._h if self.node.folded else TITLE_H
        
        # Draw fold indicator on the left using standardized shapes
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(FG_BRIGHT))
        
        # Calculate position for the fold indicator
        indicator_size = 10
        indicator_x = PAD + (20 - indicator_size) // 2
        indicator_y = (text_height - indicator_size) // 2
        
        if getattr(self.node, 'allow_folding', True):
            if self.node.folded:
                ShapeDrawer.draw_triangle_left(painter, indicator_x, indicator_y, indicator_size)
            else:
                ShapeDrawer.draw_triangle_down(painter, indicator_x, indicator_y, indicator_size)
        
        # Draw title text with drop shadow
        title_text = self.node.display_name.upper()
        
        title_start_x = PAD + 25 
        title_right_pad = 18 if not self.node.locked_title else 2 * PAD
        
        shadow_offset = 1
        painter.setPen(QColor(0, 0, 0, 40))  # Semi-transparent black shadow
        painter.setFont(QFont("Roboto", 9))
        
        painter.drawText(
            QRectF(title_start_x + shadow_offset, shadow_offset, self._w - title_start_x - title_right_pad, text_height),
            Qt.AlignVCenter | Qt.AlignLeft,
            title_text,
        )
        
        painter.setPen(QColor(FG_BRIGHT))
        painter.drawText(
            QRectF(title_start_x, 0, self._w - title_start_x - title_right_pad, text_height),
            Qt.AlignVCenter | Qt.AlignLeft,
            title_text,
        )

        # Draw execution timer if available
        if self.node.last_execution_time is not None:
            unit = "s"
            if self.scene() and hasattr(self.scene(), "graph"):
                unit = self.scene().graph.time_unit
            val = self.node.last_execution_time
            if unit == "ms":
                val *= 1000
            painter.setPen(QColor(FG_DIM))
            painter.setFont(QFont(FONT_MONO, 8))
            painter.drawText(QRectF(0, -18, self._w, 15), Qt.AlignLeft | Qt.AlignVCenter, f"{val:.4f}{unit}")

        if self.node.folded:
            return  # skip all port label drawing

        # Port labels - always drawn in scene (widgets no longer contain labels)
        painter.setFont(QFont("Segoe UI", 8))
        label_col = QColor(FG_DEFAULT)
        value_col = QColor(FG_BRIGHT)

        visible_out_idx = 0
        for name, port in self.node.outputs.items():
            if not port.allow_connection:
                continue
            y = TITLE_H + visible_out_idx * ROW_H
            painter.setPen(label_col)
            display = port.label if port.label else name
            painter.drawText(
                QRectF(0, y, self._w - PR - PAD, ROW_H),
                Qt.AlignVCenter | Qt.AlignRight,
                _elide(display),
            )
            visible_out_idx += 1

        lbl_w = self.node.label_width or self._calculate_ideal_label_width()
        row_offset_y = TITLE_H + visible_out_idx * ROW_H
        for name, port in self.node.inputs.items():
            is_editable = _port_is_editable(port.port_type) and port.editable
            has_custom = self.node.has_gui_builder(name)
            full_row = getattr(port, 'full_row', False)
            below_flag = getattr(port, 'below_ports', False)
            port_rh = getattr(port, 'row_height', None) or ROW_H
            if not is_editable and not has_custom and not full_row and not port.allow_connection:
                continue

            if full_row:
                if port.allow_connection:
                    is_connected = self._conn_cache.get(name) is not None
                    if is_connected:
                        painter.setPen(label_col)
                        painter.drawText(
                            QRectF(PR + PAD, row_offset_y, lbl_w, ROW_H),
                            Qt.AlignVCenter | Qt.AlignLeft,
                            _elide(port.label or name, int(lbl_w / 6)),
                        )
                    row_offset_y += port_rh if (is_editable or has_custom) else ROW_H
                else:
                    row_offset_y += port_rh
                continue

            painter.setPen(label_col)
            painter.drawText(
                QRectF(PR + PAD, row_offset_y, lbl_w, ROW_H),
                Qt.AlignVCenter | Qt.AlignLeft,
                port.label or name,
            )
            # When connected: show the live value text on the right (proxy is hidden)
            if is_editable and not below_flag:
                src_port = self._conn_cache.get(name)
                if src_port:
                    val_text = src_port.label or (
                        str(src_port.value) if src_port.value is not None else ""
                    )
                    if val_text:
                        widget_x = PR + PAD + lbl_w + 2
                        painter.setPen(value_col)
                        painter.drawText(
                            QRectF(widget_x, row_offset_y,
                                   self._w - widget_x - PAD, ROW_H),
                            Qt.AlignVCenter | Qt.AlignLeft,
                            _elide(val_text, 20),
                        )
            row_offset_y += ROW_H

        if self._plugin_source:
            painter.setFont(QFont("Segoe UI", 7))
            painter.setPen(QColor(FG_DIM))
            painter.drawText(
                QRectF(PR + PAD, self._h - PLUGIN_LABEL_H, self._w - 2 * (PR + PAD), PLUGIN_LABEL_H),
                Qt.AlignVCenter | Qt.AlignLeft,
                self._plugin_source,
            )

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.node.x = float(self.x())
            self.node.y = float(self.y())
            sc = self.scene()
            if sc:
                sc.refresh_connections(self)
                if hasattr(sc, '_after_node_mutation'):
                    sc._after_node_mutation(self.node.id)
        return super().itemChange(change, value)
    
    def mousePressEvent(self, event):
        """Track press in fold indicator area; defer fold decision to release."""
        if event.button() == Qt.LeftButton:
            fold_rect = self._get_fold_indicator_rect()
            if fold_rect.contains(event.pos()) and getattr(self.node, 'allow_folding', True):
                self._fold_press_pos = event.pos()
                event.accept()
                return
        self._fold_press_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Clear fold intent if mouse moves beyond click threshold (~5px)."""
        if self._fold_press_pos is not None:
            delta = (event.pos() - self._fold_press_pos).manhattanLength()
            if delta > 5:
                self._fold_press_pos = None
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Toggle fold only if released near press position in fold area."""
        if (event.button() == Qt.LeftButton and self._fold_press_pos is not None):
            fold_rect = self._get_fold_indicator_rect()
            delta = (event.pos() - self._fold_press_pos).manhattanLength()
            if fold_rect.contains(event.pos()) and delta <= 5:
                self._toggle_fold()
                event.accept()
                self._fold_press_pos = None
                return
            self._fold_press_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click no longer toggles fold - use the fold indicator instead."""
        super().mouseDoubleClickEvent(event)

    def _toggle_fold(self) -> None:
        """
        Flip node.folded and rebuild the layout using undo/redo system.
        """
        old_folded = self.node.folded
        new_folded = not old_folded
        
        # Push the fold command to the undo stack
        sc = self.scene()
        if sc:
            sc.undo_stack.push(FoldCommand(self, old_folded, new_folded))
        else:
            # Fallback if no scene (shouldn't happen in normal operation)
            self._direct_toggle_fold(old_folded, new_folded)

    def _direct_toggle_fold(self, old_folded: bool, new_folded: bool) -> None:
        """
        Direct fold toggle without undo/redo (used as fallback).
        """
        if not old_folded:
            # About to fold - save the current (possibly user-resized) height
            self._unfolded_height = self._h
        
        self.node.folded = new_folded
        self.refresh_ports()   # recalculates height, repositions ports, hides proxies

        if not new_folded and self._unfolded_height is not None:
            # Unfolding - restore the saved height instead of the auto-calculated minimum
            self.prepareGeometryChange()
            self._h = self._unfolded_height
            self.node.height = self._h
            self.handle.setPos(self._w, self._h)
            self._unfolded_height = None

        # Resize handle is meaningless when folded; hide it
        self.handle.setVisible(not new_folded)

        sc = self.scene()
        if sc:
            sc.refresh_connections(self)
            sc.graph_changed.emit()


