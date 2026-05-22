from __future__ import annotations
from PySide6.QtWidgets import QGraphicsPathItem, QMenu
from PySide6.QtGui     import QPainterPath, QPainterPathStroker, QPen, QColor, QPolygonF
from PySide6.QtCore    import QPointF, Qt
from sourcegraph.gui.theme import *
from sourcegraph.sys.registry import get_color as _get_port_color


class ConnectionItem(QGraphicsPathItem):
    """Cubic-bezier or linear wire between two ports."""

    wire_style      = "spline"  # "spline" | "linear" | "straight"
    wire_width      = 3.0       # idle / valid / invalid pen width (px)
    wire_width_sel  = 3.5       # selected pen width (px)
    arrow_spacing   = 300.0     # distance between arrowhead chevrons (px)
    arrow_scale     = 1.0       # uniform arrowhead size multiplier (1.0 = default)

    _PEN_SEL     = QPen(QColor(WIRE_SEL),      wire_width_sel)
    _PEN_VALID   = QPen(QColor(COLOR_VALID),   wire_width)
    _PEN_INVALID = QPen(QColor(COLOR_INVALID), wire_width)

    def __init__(self, src: QPointF, dst: QPointF | None = None, src_port_type: str | None = None) -> None:
        super().__init__()
        self.src = src
        self.dst = dst or src
        self._drag_status: bool | None = None
        color = _get_port_color(src_port_type) if src_port_type else WIRE_IDLE
        self._pen_idle = QPen(QColor(color), ConnectionItem.wire_width)
        self.setZValue(-1)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable)
        self._refresh()

    def set_drag_status(self, status: bool | None) -> None:
        """Updates the wire color based on connection validity (None=Reset)."""
        self._drag_status = status
        self.update()

    def set_src(self, p: QPointF) -> None:
        self.src = p
        self._refresh()

    def set_dst(self, p: QPointF) -> None:
        self.dst = p
        self._refresh()

    def _refresh(self) -> None:
        s, e = self.src, self.dst
        path = QPainterPath(s)
        
        if ConnectionItem.wire_style == "linear":
            path.lineTo(e)
        elif ConnectionItem.wire_style == "straight":
            # Orthogonal/Manhattan style
            mid_x = s.x() + (e.x() - s.x()) * 0.5
            path.lineTo(mid_x, s.y())
            path.lineTo(mid_x, e.y())
            path.lineTo(e)
        else:
            dx = max(abs(e.x() - s.x()) * 0.5, 60.0)
            path.cubicTo(s + QPointF(dx, 0), e - QPointF(dx, 0), e)
            
        self.setPath(path)

    def shape(self):
        """Widen the hit area so thin wires are easy to click."""
        sk = QPainterPathStroker()
        sk.setWidth(10)
        return sk.createStroke(self.path())

    def paint(self, painter, option, widget=None):
        if self.isSelected():
            pen = self._PEN_SEL
        elif self._drag_status is True:
            pen = self._PEN_VALID
        elif self._drag_status is False:
            pen = self._PEN_INVALID
        else:
            pen = self._pen_idle

        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())
        
        # Draw Arrows
        path_len = self.path().length()
        if path_len > 30:
            spacing = ConnectionItem.arrow_spacing
            # Calculate total arrows, ensuring at least one
            num_arrows = max(1, int(path_len / spacing))

            painter.save()
            painter.setBrush(pen.color())
            painter.setPen(Qt.NoPen)

            s = ConnectionItem.arrow_scale
            arrow_head = QPolygonF([
                QPointF(-8 * s, -6 * s),
                QPointF( 6 * s,  0),
                QPointF(-8 * s,  6 * s),
            ])

            for i in range(1, num_arrows + 1):
                # Distribute arrows evenly
                percent = (i * (path_len / (num_arrows + 1))) / path_len

                if num_arrows == 1:
                    percent = 0.5

                arrow_pt = self.path().pointAtPercent(percent)
                tangent  = self.path().angleAtPercent(percent)

                painter.save()
                painter.translate(arrow_pt)
                painter.rotate(-tangent)
                painter.drawPolygon(arrow_head)
                painter.restore()
            painter.restore()
