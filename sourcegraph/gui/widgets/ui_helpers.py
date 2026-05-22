"""Shared UI utility functions for panels and dialogs.

Provides reusable Qt helpers that would otherwise be duplicated across
panel and dialog modules.
"""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QDialog, QApplication
from PySide6.QtGui import QCursor


def make_separator() -> QFrame:
    """Return a styled 1px horizontal divider frame suitable for panel layouts."""
    # Deferred import to avoid a circular dependency with gui.theme
    # (gui.theme imports gui.widgets.icon_provider, which triggers this package).
    from sourcegraph.gui.theme import BORDER_DARK
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(
        f"background: {BORDER_DARK}; border: none; max-height: 1px; margin: 2px 0px;"
    )
    return sep


def position_near_cursor(dialog: QDialog) -> None:
    """Move *dialog* so it appears near the cursor, clamped to the current screen."""
    pos    = QCursor.pos()
    screen = QApplication.screenAt(pos) or QApplication.primaryScreen()
    avail  = screen.availableGeometry()

    dialog.adjustSize()
    dw = dialog.sizeHint().width()
    dh = dialog.sizeHint().height()

    x = pos.x() + 14
    y = pos.y() - dh // 2

    x = max(avail.left(), min(x, avail.right() - dw))
    y = max(avail.top(), min(y, avail.bottom() - dh))

    dialog.move(x, y)
