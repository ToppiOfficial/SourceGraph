from __future__ import annotations
from PySide6.QtWidgets import QGraphicsPathItem
from PySide6.QtGui     import QPainterPath, QPainterPathStroker, QPen, QColor
from PySide6.QtCore    import QPointF
from gui.theme import *


class ConnectionItem(QGraphicsPathItem):
    """Cubic-bezier wire between two ports (or a drag preview)."""

    _PEN_IDLE    = QPen(QColor(WIRE_IDLE), 2.0)
    _PEN_SEL     = QPen(QColor(WIRE_SEL), 2.5)
    _PEN_VALID   = QPen(QColor(COLOR_VALID), 2.0)
    _PEN_INVALID = QPen(QColor(COLOR_INVALID), 2.0)

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
        dx   = max(abs(e.x() - s.x()) * 0.5, 60.0)
        path = QPainterPath(s)
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
        painter.drawPath(self.path())
