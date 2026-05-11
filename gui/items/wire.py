from __future__ import annotations
from PySide6.QtWidgets import QGraphicsPathItem, QMenu
from PySide6.QtGui     import QPainterPath, QPainterPathStroker, QPen, QColor, QPolygonF
from PySide6.QtCore    import QPointF, Qt
from gui.theme import *


class ConnectionItem(QGraphicsPathItem):
    """Cubic-bezier or linear wire between two ports."""

    _PEN_IDLE    = QPen(QColor(WIRE_IDLE), 2.0)
    _PEN_SEL     = QPen(QColor(WIRE_SEL), 2.5)
    _PEN_VALID   = QPen(QColor(COLOR_VALID), 2.0)
    _PEN_INVALID = QPen(QColor(COLOR_INVALID), 2.0)
    
    wire_style = "spline"

    def __init__(self, src: QPointF, dst: QPointF | None = None) -> None:
        super().__init__()
        self.src = src
        self.dst = dst or src
        self._drag_status: bool | None = None
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
            pen = self._PEN_IDLE

        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(self.path())
        
        # Draw Arrows
        path_len = self.path().length()
        if path_len > 30:
            spacing = 300.0
            # Calculate total arrows, ensuring at least one
            num_arrows = max(1, int(path_len / spacing))
            
            painter.save()
            painter.setBrush(pen.color())
            painter.setPen(Qt.NoPen)
            
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
                
                arrow_head = QPolygonF([
                    QPointF(-8, -6),
                    QPointF(6, 0),
                    QPointF(-8, 6)
                ])
                painter.drawPolygon(arrow_head)
                painter.restore()
            painter.restore()
