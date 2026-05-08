from __future__ import annotations
from PySide6.QtWidgets import QDockWidget, QWidget
from PySide6.QtCore import Qt, QTimer

class BasePanel(QDockWidget):
    """
    Base class for all modular panels.
    Subclasses should define ID, TITLE, and DEFAULT_AREA.
    """
    ID = "BasePanel"
    TITLE = "Base Panel"
    DEFAULT_AREA = Qt.RightDockWidgetArea

    def __init__(self, main_window) -> None:
        super().__init__(self.TITLE, main_window)
        self.main_window = main_window
        self._widget = None
        self._active_scene = None
        self.setObjectName(self.ID)

    def get_widget(self) -> QWidget | None:
        """Return the internal widget used by this dock."""
        return self._widget

    def setup(self) -> None:
        """
        Override to perform initialization like signal connections.
        Called after the MainWindow has initialized its core components (graph, scene).
        """
        pass

    def switch_context_safe(self, nav_node) -> None:
        """
        Perform a deferred context switch to avoid Qt crashes when the 
        triggering UI item is deleted during event processing.
        """
        if not nav_node:
            return
        # Defer to the next event loop iteration
        QTimer.singleShot(0, lambda: self.main_window._switch_to_context(nav_node))

    def update_context(self, graph, scene) -> None:
        """Called when the active graph/scene changes (e.g. breadcrumb navigation)."""
        pass