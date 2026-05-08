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
        # Note: scene must exist before this is called
        self._widget = CustomUndoView(main_window.scene.undo_stack)
        self._widget.setStyleSheet(HISTORY_STYLE)
        self.setWidget(self._widget)

    def update_context(self, graph, scene) -> None:
        self._widget.setStack(scene.undo_stack)