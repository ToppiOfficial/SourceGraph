from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt
from gui.panels.base_panel import BasePanel
from gui.widgets.custom_undo_view import CustomUndoView
from gui.theme import HISTORY_STYLE

class HistoryPanel(BasePanel):
    ID = "HistoryDock"
    TITLE = "History"
    DEFAULT_AREA = Qt.LeftDockWidgetArea

    def __init__(self, main_window) -> None:
        super().__init__(main_window)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._lock_label = QLabel("Undo disabled during execution")
        self._lock_label.setAlignment(Qt.AlignCenter)
        self._lock_label.setStyleSheet(
            "color: #888; font-size: 11px; padding: 4px;"
            "background: #1a1a1a; border-bottom: 1px solid #333;")
        self._lock_label.setVisible(False)
        layout.addWidget(self._lock_label)

        self._widget = CustomUndoView(main_window.scene.undo_stack)
        self._widget.setStyleSheet(HISTORY_STYLE)
        layout.addWidget(self._widget)

        self.setWidget(container)

    def update_context(self, graph, scene) -> None:
        self._widget.setStack(scene.undo_stack)

    def on_execution_lock(self, locked: bool) -> None:
        self._lock_label.setVisible(locked)
        if locked:
            self._widget.setStack(None)
        elif self.main_window.scene:
            self._widget.setStack(self.main_window.scene.undo_stack)
