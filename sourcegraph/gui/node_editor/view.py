"""NodeEditorView, MinimapWidget, and view-level helpers.

Contains the viewport (NodeEditorView), the minimap overlay (MinimapWidget),
the transient notification popup (NotificationPopup), the keyboard shortcut
registry (ShortcutRegistry), and the context-menu factory (ContextMenuFactory).
"""
from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (QGraphicsView, QMenu, QWidget, QLabel,
                                QApplication, QGraphicsOpacityEffect)
from PySide6.QtGui import (QBrush, QColor, QPainter, QPen, QKeyEvent, QWheelEvent,
                             QMouseEvent, QCursor, QTransform, QPainterPath,
                             QDragEnterEvent, QDropEvent, QDragMoveEvent, qGray,
                             QSurfaceFormat)
from PySide6.QtCore import Qt, QPointF, QPoint, QRect, QRectF, Signal, QTimer, QPropertyAnimation
from PySide6.QtOpenGLWidgets import QOpenGLWidget

from sourcegraph.sys.registry import NODE_CLASS_MAPPINGS, NODE_CATEGORIES
from sourcegraph.nodes.subgraph.subgraph import SubgraphNode

from sourcegraph.gui.items.node import NodeItem, PortItem, ResizeHandle
from sourcegraph.gui.items.wire import ConnectionItem
from sourcegraph.gui.commands import FoldCommand, ResizeNodeCommand
from sourcegraph.gui.constants import DEFAULT_W
from sourcegraph.gui.theme import MENU, MINIMAP_VIEW, COLOR_INVALID, COLOR_VALID, NOTIFICATION_STYLE, BG_DARKER, BG_RAISED
from sourcegraph.gui.widgets.safe_graphics_view import SafeGraphicsView
from sourcegraph.gui.background_renderer import (
    BackgroundRenderer, GridBackgroundRenderer, ModernGLBackgroundRenderer,
)
from sourcegraph.gui.node_editor.state import ClipboardManager, RubberBandMode
from sourcegraph.gui.menu.node_search_dialog import NodeSearchDialog

if TYPE_CHECKING:
    from sourcegraph.gui.node_editor.scene import NodeEditorScene


# -- Keyboard shortcut registry -----------------------------------------------

class ShortcutRegistry:
    """Maps (key, modifiers) pairs to callbacks; keyPressEvent delegates here."""

    def __init__(self) -> None:
        self._bindings: list[tuple[int, Qt.KeyboardModifier, object, str]] = []

    def register(
        self,
        key:         int,
        modifiers:   Qt.KeyboardModifier,
        callback,
        description: str = "",
    ) -> None:
        self._bindings.append((key, Qt.KeyboardModifier(modifiers), callback, description))

    def handle(self, event: QKeyEvent) -> bool:
        k = event.key()
        m = Qt.KeyboardModifier(event.modifiers())
        for key, mods, cb, _ in self._bindings:
            if k == key and m == mods:
                cb()
                return True
        return False


# -- Context menu factory -----------------------------------------------------

class ContextMenuFactory:
    """Builds and executes right-click context menus for nodes, ports, and the canvas."""

    @staticmethod
    def exec_node_menu(scene, view, item: NodeItem, global_pos) -> None:
        item.setSelected(True)
        menu = QMenu(view)
        menu.setStyleSheet(MENU)

        rename_act  = menu.addAction("Rename")  if not item.node.locked_title else None
        open_act    = menu.addAction("Open Subgraph") if isinstance(item.node, SubgraphNode) else None
        resize_act  = menu.addAction("Resize")
        convert_act = menu.addAction("Convert to Subgraph")
        fold_act    = menu.addAction("Unfold" if item.node.folded else "Fold")
        menu.addSeparator()
        copy_props_act  = menu.addAction("Copy Properties")
        paste_props_act = menu.addAction("Paste Properties")
        menu.addSeparator()
        delete_act      = menu.addAction("Delete")
        menu.addSeparator()
        add_exec_act    = menu.addAction("Add to Execution")

        action = menu.exec(global_pos)
        if not action:
            return

        if action == open_act:
            path = item.node.inputs.get("graph_path").value
            if path:
                view.subgraph_requested.emit(path)
        elif action == rename_act:
            scene._start_rename(item)
        elif action == resize_act:
            if item.node.folded:
                item.node.folded = False
                default_h = item._calculate_height()
                item.node.folded = True
                old_h = item._unfolded_height
            else:
                default_h = item._calculate_height()
                old_h = item._h
            cmd = ResizeNodeCommand(item, item._w, old_h, DEFAULT_W, default_h)
            scene._undo_manager.undo_stack.push(cmd)
        elif action == convert_act:
            targets = [i for i in scene.selectedItems() if isinstance(i, NodeItem)]
            if not targets:
                targets = [item]
            scene._convert_to_subgraph(targets)
        elif action == fold_act:
            cmd = FoldCommand(item, item.node.folded, not item.node.folded)
            scene._undo_manager.push(cmd)
        elif action == copy_props_act:
            ClipboardManager.copy_properties(item)
        elif action == paste_props_act:
            ClipboardManager.paste_properties(scene, item)
        elif action == delete_act:
            scene.remove_selected()
        elif action == add_exec_act:
            mw = view.window()
            exec_widget = mw.panel_manager.get_widget("ExecutionDock") if hasattr(mw, "panel_manager") else None
            if exec_widget:
                with scene._undo_manager.transaction("Add to Execution"):
                    if not item.isSelected():
                        scene.clearSelection()
                        item.setSelected(True)
                    exec_widget._add_selected_node()
                exec_panel = mw.panel_manager.get_panel("ExecutionDock")
                if exec_panel:
                    exec_panel.show()
                    exec_panel.raise_()

    @staticmethod
    def exec_port_menu(scene, view, item: PortItem, global_pos) -> None:
        conn = scene.graph.get_input_connection(item.port.node_id, item.port.name)
        menu = QMenu(view)
        menu.setStyleSheet(MENU)

        if conn:
            delete_act = menu.addAction("Delete connection")
            action = menu.exec(global_pos)
            if action == delete_act:
                with scene._undo_manager.transaction("Delete Connection"):
                    for pair in list(scene._conn_items):
                        if pair[0] == conn:
                            scene._delete_conn(pair[1], push_undo=False)
                            break
        else:
            create_act = menu.addAction("Create wire")
            action = menu.exec(global_pos)
            if action == create_act:
                scene._wire_drag.drag_port = item
                scene._wire_drag.drag_conn = ConnectionItem(
                    item.scene_center(), src_port_type=item.port.port_type)
                scene.addItem(scene._wire_drag.drag_conn)

    @staticmethod
    def exec_background_menu(scene, view, scene_pos: QPointF, global_pos) -> None:
        menu = QMenu(view)
        menu.setStyleSheet(MENU)
        for cat, classes in NODE_CATEGORIES.items():
            sub = menu.addMenu(cat)
            for cls in classes:
                act = sub.addAction(cls.title)
                def _trigger(checked, c=cls, p=scene_pos):
                    scene.add_node(c(), p)
                act.triggered.connect(_trigger)
        menu.exec(global_pos)


# -- Notification popup --------------------------------------------------------

class NotificationPopup(QLabel):
    """Transient on-screen message that fades out after 3 seconds."""

    def __init__(self, parent: QWidget, message: str, is_error: bool = False) -> None:
        super().__init__(message, parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        bg = COLOR_INVALID if is_error else COLOR_VALID
        self.setStyleSheet(NOTIFICATION_STYLE.replace("{bg_color}", bg))

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)

        self.animation = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.animation.setDuration(800)
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.finished.connect(self.deleteLater)

        QTimer.singleShot(3000, self.animation.start)
        self.adjustSize()

    def position_in_parent(self) -> None:
        if self.parentWidget():
            self.move(20, 20)


# -- Minimap widget ------------------------------------------------------------

class MinimapWidget(QWidget):
    closed = Signal()

    def __init__(self, view: NodeEditorView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.show_node_colors   = True
        self.show_links         = True
        self.render_error_state = True
        self.view               = view
        self.setMouseTracking(True)
        self.setMinimumSize(100, 80)
        # Cache QPainterPath per connection; only rebuilt when endpoints/style change.
        self._conn_path_cache:     dict[tuple, QPainterPath] = {}
        self._conn_endpoint_cache: dict[tuple, tuple]        = {}

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bg = QColor(0, 0, 0, 80)
        painter.setBrush(bg)
        painter.setPen(QPen(bg, 1))
        painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

        scene = self.view.scene()
        if scene is None:
            self._draw_controls(painter)
            painter.end()
            return

        try:
            nodes = [i for i in scene.items() if isinstance(i, NodeItem)]
        except RuntimeError:
            self._draw_controls(painter)
            painter.end()
            return

        if not nodes:
            self._draw_controls(painter)
            painter.end()
            return

        rect = nodes[0].sceneBoundingRect()
        for n in nodes[1:]:
            rect = rect.united(n.sceneBoundingRect())
        margin = max(rect.width(), rect.height()) * 0.15
        rect.adjust(-margin, -margin, margin, margin)

        w_rect = self.rect().adjusted(10, 10, -10, -10)
        if rect.width() == 0 or rect.height() == 0:
            painter.end()
            return

        scale = min(w_rect.width() / rect.width(), w_rect.height() / rect.height())
        painter.save()
        painter.translate(w_rect.center())
        painter.scale(scale, scale)
        painter.translate(-rect.center())

        if self.show_links:
            painter.setPen(QPen(QColor(100, 100, 100, 150), 2.0 / scale))
            wire_style = ConnectionItem.wire_style
            for conn, ci in scene._conn_items:
                if ci.isVisible():
                    src_ni = scene._node_items.get(conn.src_node)
                    dst_ni = scene._node_items.get(conn.dst_node)
                    if src_ni and dst_ni:
                        sp = src_ni.port_item(conn.src_port)
                        dp = dst_ni.port_item(conn.dst_port)
                        if sp and dp:
                            s = sp.scene_center()
                            e = dp.scene_center()
                            cache_key = (conn.src_node, conn.src_port, conn.dst_node, conn.dst_port)
                            endpoints  = (s.x(), s.y(), e.x(), e.y(), wire_style)
                            if self._conn_endpoint_cache.get(cache_key) != endpoints:
                                path = QPainterPath(s)
                                if wire_style == "linear":
                                    path.lineTo(e)
                                elif wire_style == "straight":
                                    mx = s.x() + (e.x() - s.x()) * 0.5
                                    path.lineTo(mx, s.y())
                                    path.lineTo(mx, e.y())
                                    path.lineTo(e)
                                else:
                                    dx = max(abs(e.x() - s.x()) * 0.5, 60.0)
                                    path.cubicTo(s + QPointF(dx, 0), e - QPointF(dx, 0), e)
                                self._conn_path_cache[cache_key]     = path
                                self._conn_endpoint_cache[cache_key] = endpoints
                            painter.drawPath(self._conn_path_cache[cache_key])

        painter.setPen(Qt.NoPen)
        for n in nodes:
            color = QColor(n.node.color).darker(150)
            if not self.show_node_colors:
                g     = qGray(color.rgb())
                color = QColor(g, g, g)
            if self.render_error_state and (n.node.error_msg or n._has_required_error()):
                color = QColor(255, 50, 50, 200)
            painter.setBrush(color)
            painter.drawRect(n.sceneBoundingRect())

        view_rect = self.view.mapToScene(self.view.viewport().rect()).boundingRect()
        painter.setPen(QPen(QColor(MINIMAP_VIEW), 1.5 / scale))
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.drawRect(view_rect)
        painter.restore()

        self._draw_controls(painter)
        painter.end()

    def _draw_controls(self, painter: QPainter) -> None:
        painter.setPen(QColor(200, 200, 200))
        x_rect = QRectF(self.width() - 22, 8, 10, 10)
        painter.drawLine(x_rect.topLeft(), x_rect.bottomRight())
        painter.drawLine(x_rect.topRight(), x_rect.bottomLeft())

    def mousePressEvent(self, event) -> None:
        pos   = event.position()
        scene = self.view.scene()
        if scene is None:
            event.ignore()
            return

        if pos.x() > self.width() - 30 and pos.y() < 30:
            self.hide()
            self.closed.emit()
            return

        nodes = [i for i in scene.items() if isinstance(i, NodeItem)]
        valid = [n for n in nodes if not n.sceneBoundingRect().isEmpty()]
        if not valid:
            return

        rect = valid[0].sceneBoundingRect()
        for n in valid[1:]:
            nr = n.sceneBoundingRect()
            if not nr.isEmpty():
                rect = rect.united(nr)
        margin = max(rect.width(), rect.height()) * 0.15
        rect.adjust(-margin, -margin, margin, margin)
        if rect.width() == 0 or rect.height() == 0:
            return

        w_rect     = self.rect().adjusted(10, 10, -10, -10)
        scale      = min(w_rect.width() / rect.width(), w_rect.height() / rect.height())
        local_pos  = event.position() - w_rect.topLeft()
        self.view.centerOn(QPointF(
            rect.left() + local_pos.x() / scale,
            rect.top()  + local_pos.y() / scale,
        ))
        self.view.view_changed.emit()
        self.update()


# -- View ----------------------------------------------------------------------

class NodeEditorView(SafeGraphicsView):
    compile_requested  = Signal()
    subgraph_requested = Signal(str)
    view_changed       = Signal()

    def __init__(self, scene: NodeEditorScene) -> None:
        super().__init__(scene)

        gl_widget = QOpenGLWidget()
        fmt = QSurfaceFormat.defaultFormat()
        fmt.setSamples(4)
        gl_widget.setFormat(fmt)
        self.setViewport(gl_widget)

        self.setRenderHints(
            QPainter.Antialiasing |
            QPainter.SmoothPixmapTransform |
            QPainter.TextAntialiasing)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setOptimizationFlags(
            QGraphicsView.DontAdjustForAntialiasing |
            QGraphicsView.DontSavePainterState)
        self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(QColor(BG_DARKER)))
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setAcceptDrops(True)

        self._panning    = False
        self._pan_start  = QPoint()
        self._notification: NotificationPopup | None = None

        self.allow_zoom  = True
        self.allow_pan   = True
        self.show_grid   = True
        self._bg_color   = QColor(BG_DARKER)

        self._bg_renderer: BackgroundRenderer = GridBackgroundRenderer()

        self._rb_mode:          RubberBandMode = RubberBandMode.REPLACE
        self._rb_pre_selection: set            = set()
        self._rb_press_pos:     QPoint         = QPoint()

        self._shortcuts = ShortcutRegistry()
        self._register_shortcuts()

    def set_background_renderer(self, renderer: BackgroundRenderer) -> None:
        """Hot-swap the background renderer at runtime."""
        self._bg_renderer.cleanup()
        self._bg_renderer = renderer
        self.viewport().update()

    # -- shortcuts -------------------------------------------------------------

    def _register_shortcuts(self) -> None:
        reg = self._shortcuts
        NO_MOD  = Qt.NoModifier
        SHIFT   = Qt.ShiftModifier
        CTRL    = Qt.ControlModifier
        CTRL_SH = Qt.ControlModifier | Qt.ShiftModifier

        reg.register(Qt.Key_A,      SHIFT,   self._open_node_search,    "Node search")
        reg.register(Qt.Key_Tab,    NO_MOD,  self._open_node_search,    "Node search")
        reg.register(Qt.Key_F,      NO_MOD,  self._frame_selection,     "Frame selection")
        reg.register(Qt.Key_Home,   NO_MOD,  self._frame_all,           "Frame all")
        reg.register(Qt.Key_H,      NO_MOD,  self._toggle_fold,         "Toggle fold")
        reg.register(Qt.Key_G,      CTRL,    self._convert_to_subgraph, "Convert to subgraph")

        reg.register(Qt.Key_C,      CTRL,    lambda: self.scene().copy_selection(),              "Copy")
        reg.register(Qt.Key_X,      CTRL,    lambda: self.scene().cut_selection(),               "Cut")
        reg.register(Qt.Key_V,      CTRL,    lambda: self.scene().paste_from_clipboard(
                                                 self._mouse_scene_pos()),                       "Paste")
        reg.register(Qt.Key_D,      SHIFT,   lambda: self.scene().duplicate_selection(
                                                 self._mouse_scene_pos()),                       "Duplicate")

        reg.register(Qt.Key_C,      CTRL_SH, self._copy_properties,     "Copy properties")
        reg.register(Qt.Key_V,      CTRL_SH, self._paste_properties,    "Paste properties")
        reg.register(Qt.Key_A,      CTRL,    self._select_all,          "Select all")
        reg.register(Qt.Key_F5,     NO_MOD,  self.compile_requested.emit, "Compile")

    def _open_node_search(self) -> None:
        pos = QCursor.pos()
        dlg = NodeSearchDialog(None)
        dlg.setStyleSheet(MENU)
        dlg.move(pos)
        if dlg.exec() and dlg.selected_class:
            new_node = dlg.selected_class()
            self.scene().add_node(new_node, self.mapToScene(self.mapFromGlobal(pos)))
            self.scene().clearSelection()
            item = self.scene()._node_items.get(new_node.id)
            if item:
                item.setSelected(True)

    def _frame_selection(self) -> None:
        selected = [i for i in self.scene().selectedItems() if isinstance(i, NodeItem)]
        if not selected:
            self._frame_all()
            return
        rect = selected[0].sceneBoundingRect()
        for item in selected[1:]:
            rect = rect.united(item.sceneBoundingRect())
        rect = rect.adjusted(-60, -60, 60, 60)
        self.fitInView(rect, Qt.KeepAspectRatio)
        self.view_changed.emit()

    def _frame_all(self) -> None:
        nodes = [i for i in self.scene().items() if isinstance(i, NodeItem)]
        if not nodes:
            return
        rect = nodes[0].sceneBoundingRect()
        for n in nodes[1:]:
            rect = rect.united(n.sceneBoundingRect())
        rect = rect.adjusted(-80, -80, 80, 80)
        self.fitInView(rect, Qt.KeepAspectRatio)
        self.view_changed.emit()

    def _toggle_fold(self) -> None:
        selected = [i for i in self.scene().selectedItems() if isinstance(i, NodeItem)]
        if not selected:
            return
        any_unfolded = any(not n.node.folded for n in selected)
        with self.scene()._undo_manager.transaction("Toggle Fold"):
            for item in selected:
                if item.node.folded != any_unfolded:
                    self.scene()._undo_manager.push(
                        FoldCommand(item, item.node.folded, any_unfolded)
                    )

    def _convert_to_subgraph(self) -> None:
        targets = [i for i in self.scene().selectedItems() if isinstance(i, NodeItem)]
        if targets:
            self.scene()._convert_to_subgraph(targets)

    def _copy_properties(self) -> None:
        selected = [i for i in self.scene().selectedItems() if isinstance(i, NodeItem)]
        if selected:
            ClipboardManager.copy_properties(selected[0])

    def _paste_properties(self) -> None:
        selected = [i for i in self.scene().selectedItems() if isinstance(i, NodeItem)]
        if selected and ClipboardManager._property_data:
            ClipboardManager.paste_properties(self.scene(), selected[0])
        else:
            ClipboardManager.try_paste_from_os_clipboard(
                self.scene(), self._mouse_scene_pos())

    def _select_all(self) -> None:
        for item in self.scene().items():
            if isinstance(item, NodeItem):
                item.setSelected(True)

    def _mouse_scene_pos(self) -> QPointF:
        local = self.viewport().mapFromGlobal(QCursor.pos())
        if self.viewport().rect().contains(local):
            return self.mapToScene(local)
        return self.mapToScene(self.viewport().rect().center())

    # -- background ------------------------------------------------------------

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        if not self.show_grid:
            painter.fillRect(rect, self._bg_color)
            return
        zoom   = self.transform().m11()
        vp     = self.viewport().size()
        origin = self.mapToScene(QPoint(0, 0))
        self._bg_renderer.render(painter, rect, zoom, vp, QPointF(origin))

    # -- notification ----------------------------------------------------------

    def show_notification(self, message: str, is_error: bool = False) -> None:
        try:
            if self._notification:
                self._notification.deleteLater()
        except RuntimeError:
            pass
        self._notification = NotificationPopup(self.viewport(), message, is_error)
        self._notification.position_in_parent()
        self._notification.show()

    def _position_notification(self) -> None:
        try:
            if self._notification and self._notification.isVisible():
                self._notification.position_in_parent()
        except RuntimeError:
            self._notification = None

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._position_notification)

    def scrollContentsBy(self, dx: int, dy: int) -> None:
        super().scrollContentsBy(dx, dy)

    # -- drag-drop -------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        if getattr(self.scene(), "_execution_locked", False):
            event.ignore()
            return
        text      = event.mimeData().text()
        scene_pos = self.mapToScene(event.position().toPoint())
        items_to_process = []

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                if data.get("type") == "assets":
                    for p in data.get("paths", []):
                        items_to_process.append(("asset", p))
                elif data.get("type") == "variables":
                    for n in data.get("names", []):
                        items_to_process.append(("variable", n))
        except (json.JSONDecodeError, TypeError):
            if text.startswith("variable:"):
                items_to_process.append(("variable", text.split(":", 1)[1]))
            else:
                items_to_process.append(("asset", text))

        if not items_to_process:
            return

        with self.scene()._undo_manager.transaction("Drop Items"):
            self.scene().clearSelection()
            current_pos = QPointF(scene_pos)
            for kind, value in items_to_process:
                from sourcegraph.sys.registry import dispatch
                dispatch(kind, self.scene(), current_pos, value, event.modifiers())
                current_pos += QPointF(0, 120)

        event.acceptProposedAction()

    # -- zoom / pan ------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self.allow_zoom:
            return
        f = 1.12 if event.angleDelta().y() > 0 else 1 / 1.12
        self.scale(f, f)
        self.view_changed.emit()

    # -- mouse -----------------------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events():
            event.ignore()
            return

        if event.button() == Qt.MiddleButton and self.allow_pan:
            self._panning   = True
            self._pan_start = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            return

        sc = self.scene()
        if sc and getattr(sc, "_execution_locked", False):
            event.ignore()
            return

        if event.button() == Qt.LeftButton:
            item = self.itemAt(event.pos())
            if item:
                self.setDragMode(QGraphicsView.NoDrag)
                self._rb_mode = RubberBandMode.REPLACE
            else:
                self.setDragMode(QGraphicsView.RubberBandDrag)
                self._rb_press_pos = event.pos()
                mods = event.modifiers()
                if mods & Qt.ShiftModifier:
                    self._rb_mode         = RubberBandMode.ADD
                    self._rb_pre_selection = set(self.scene().selectedItems())
                elif mods & Qt.ControlModifier:
                    self._rb_mode         = RubberBandMode.SUBTRACT
                    self._rb_pre_selection = set(self.scene().selectedItems())
                else:
                    self._rb_mode         = RubberBandMode.REPLACE
                    self._rb_pre_selection = set()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events():
            return
        if self._panning:
            d               = event.pos() - self._pan_start
            self._pan_start = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - d.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - d.y())
        else:
            super().mouseMoveEvent(event)

        if self._rb_mode == RubberBandMode.REPLACE:
            return

        # Correct live selection so the drag preview matches what mouseReleaseEvent will produce.
        # Qt's RubberBandDrag always uses additive semantics, so without this correction
        # unselected items inside the band get highlighted during a Ctrl (SUBTRACT) drag.
        vp_rect    = QRect(self._rb_press_pos, event.pos()).normalized()
        scene_rect = self.mapToScene(vp_rect).boundingRect()
        rb_items   = {
            i for i in self.scene().items(scene_rect, Qt.IntersectsItemShape)
            if isinstance(i, NodeItem)
        }
        if self._rb_mode == RubberBandMode.ADD:
            live = self._rb_pre_selection | rb_items
        else:  # SUBTRACT
            live = self._rb_pre_selection - rb_items

        self.scene().blockSignals(True)
        self.scene().clearSelection()
        for item in live:
            item.setSelected(True)
        self.scene().blockSignals(False)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events():
            return

        if event.button() == Qt.MiddleButton:
            self._panning = False
            self.setCursor(Qt.ArrowCursor)
            return

        if event.button() == Qt.LeftButton and self._rb_mode != RubberBandMode.REPLACE:
            vp_rect    = QRect(self._rb_press_pos, event.pos()).normalized()
            scene_rect = self.mapToScene(vp_rect).boundingRect()
            rb_items   = {
                i for i in self.scene().items(scene_rect, Qt.IntersectsItemShape)
                if isinstance(i, NodeItem)
            }
            super().mouseReleaseEvent(event)
            if self._rb_mode == RubberBandMode.ADD:
                final = self._rb_pre_selection | rb_items
            else:  # SUBTRACT
                final = self._rb_pre_selection - rb_items
            self.scene().clearSelection()
            for item in final:
                item.setSelected(True)
            self._rb_mode          = RubberBandMode.REPLACE
            self._rb_pre_selection = set()
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events():
            event.ignore()
            return
        if getattr(self.scene(), "_execution_locked", False):
            event.ignore()
            return

        item = self.itemAt(event.pos())
        if isinstance(item, NodeItem) and isinstance(item.node, SubgraphNode):
            path = item.node.inputs.get("graph_path").value
            if path:
                if not os.path.isabs(path) and self.scene().graph.project_dir:
                    path = os.path.abspath(
                        os.path.join(self.scene().graph.project_dir, path))
                self.subgraph_requested.emit(path)
                return
        elif item is None:
            self._open_node_search()
            return
        super().mouseDoubleClickEvent(event)

    # -- keyboard --------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self.is_ready_for_events():
            return
        if getattr(self.scene(), "_execution_locked", False):
            return

        focus_widget  = QApplication.focusWidget()
        scene_focused = self.scene().focusItem() is not None
        is_editing    = (focus_widget is not None and focus_widget is not self) or scene_focused

        if is_editing:
            self.scene().clearSelection()
            if event.key() == Qt.Key_F5:
                self.compile_requested.emit()
                return
            super().keyPressEvent(event)
            return

        if self._shortcuts.handle(event):
            return
        super().keyPressEvent(event)

    # -- context menu ----------------------------------------------------------

    def contextMenuEvent(self, event) -> None:
        if getattr(self.scene(), "_execution_locked", False):
            return
        item = self.itemAt(event.pos())
        if isinstance(item, PortItem):
            if item.port.is_input:
                ContextMenuFactory.exec_port_menu(
                    self.scene(), self, item, event.globalPos())
            return
        if isinstance(item, NodeItem):
            ContextMenuFactory.exec_node_menu(
                self.scene(), self, item, event.globalPos())
            return
        ContextMenuFactory.exec_background_menu(
            self.scene(), self,
            self.mapToScene(event.pos()), event.globalPos())

    # -- view state persistence ------------------------------------------------

    def get_view_state(self) -> dict:
        t        = self.transform()
        h_scroll = self.horizontalScrollBar()
        v_scroll = self.verticalScrollBar()
        return {
            "zoom":          t.m11(),
            "scroll_x":      h_scroll.value(),
            "scroll_y":      v_scroll.value(),
            "scroll_max_x":  h_scroll.maximum(),
            "scroll_max_y":  v_scroll.maximum(),
            "transform_m11": t.m11(),
            "transform_m12": t.m12(),
            "transform_m21": t.m21(),
            "transform_m22": t.m22(),
            "transform_dx":  t.dx(),
            "transform_dy":  t.dy(),
        }

    def set_view_state(self, state: dict) -> None:
        if not state:
            return
        if "transform_m11" in state:
            self.setTransform(QTransform(
                state["transform_m11"], state["transform_m12"],
                state["transform_m21"], state["transform_m22"],
                state["transform_dx"],  state["transform_dy"],
            ))
        else:
            zoom = state.get("zoom", 1.0)
            self.resetTransform()
            self.scale(zoom, zoom)

        if "scroll_x" in state and "scroll_y" in state:
            def _restore():
                self.horizontalScrollBar().setValue(state["scroll_x"])
                self.verticalScrollBar().setValue(state["scroll_y"])
            QTimer.singleShot(50, _restore)
