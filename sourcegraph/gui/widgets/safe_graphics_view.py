import weakref
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QMouseEvent, QWheelEvent, QKeyEvent, QDragEnterEvent, QDragMoveEvent, QDropEvent

class SafeGraphicsView(QGraphicsView):
    """
    QGraphicsView subclass with safety guards against crashes during rapid scene switching.
    Uses internal flags to track scene state and ignores events when not ready.
    """
    def __init__(self, scene: QGraphicsScene | None = None, parent=None):
        super().__init__(scene, parent)
        self._active_scene_ref: weakref.ReferenceType[QGraphicsScene] | None = None
        self._is_scene_ready_for_events = False

        if scene:
            self.set_scene_active(scene, True)

    def setScene(self, scene: QGraphicsScene | None) -> None:
        """Override setScene to manage internal state."""
        if self._active_scene_ref and self._active_scene_ref():
            self.set_scene_active(self._active_scene_ref(), False)
        
        super().setScene(scene)
        
        if scene:
            self.set_scene_active(scene, True)
        else:
            self._active_scene_ref = None
            self._is_scene_ready_for_events = False

    def set_scene_active(self, scene: QGraphicsScene | None, active: bool) -> None:
        """Mark the scene as active/inactive for event processing."""
        if active and scene:
            self._active_scene_ref = weakref.ref(scene)
            self._is_scene_ready_for_events = True
        else:
            self._active_scene_ref = None
            self._is_scene_ready_for_events = False
            if self.scene() == scene:
                super().setScene(None)

    def is_ready_for_events(self) -> bool:
        """Check if the view can safely process events."""
        if not self._is_scene_ready_for_events:
            return False
        
        if not self.viewport().updatesEnabled():
            return False
            
        scene = self.scene()
        if scene is None:
            return False
        
        if not hasattr(scene, 'graph') or scene.graph is None:
            return False
            
        return True

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events(): event.ignore(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events(): event.ignore(); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events(): event.ignore(); return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if not self.is_ready_for_events(): event.ignore(); return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if not self.is_ready_for_events(): event.ignore(); return
        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if not self.is_ready_for_events(): event.ignore(); return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if not self.is_ready_for_events(): event.ignore(); return
        super().keyReleaseEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if not self.is_ready_for_events(): event.ignore(); return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        if not self.is_ready_for_events(): event.ignore(); return
        super().dragMoveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if not self.is_ready_for_events(): event.ignore(); return
        super().dropEvent(event)