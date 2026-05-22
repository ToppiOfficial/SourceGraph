from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTextEdit
from sourcegraph.gui.panels.base_panel import BasePanel
from sourcegraph.gui.logger import log

class ConsolePanel(BasePanel):
    ID = "ConsoleDock"
    TITLE = "Console"
    DEFAULT_AREA = Qt.BottomDockWidgetArea

    def __init__(self, main_window) -> None:
        super().__init__(main_window)
        self._widget = QTextEdit()
        self._widget.setReadOnly(True)
        self.setWidget(self._widget)
        self.hide()

    def setup(self):
        log.set_sink(self._widget, self)
        log.setup_redirection()