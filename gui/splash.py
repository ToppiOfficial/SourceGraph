from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QGraphicsDropShadowEffect, QFrame
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QFont, QColor
from PySide6.QtWidgets import QApplication

from gui.theme import (
    SPLASH_BG_STYLE, SPLASH_PROGRESS_STYLE,
    FG_MAIN, FG_DIM, FONT_UI, ACCENT, BG_DARKER
)


class SrcGraphSplash(QWidget):
    """Slick redesigned startup splash screen with rounded corners and drop shadow."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(420, 200)

        self.setup_ui()
        self.center_on_screen()

    def setup_ui(self):
        # Main layout for the widget (contains the shadow margin)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # The actual container box with rounded corners and border
        self.container = QFrame()
        self.container.setObjectName("SplashContainer")
        self.container.setStyleSheet(SPLASH_BG_STYLE)
        
        # Drop Shadow Effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(4)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(40, 40, 40, 40)
        container_layout.setSpacing(10)

        # Title
        self.title = QLabel("SourceGraph")
        title_font = QFont(FONT_UI, 24, QFont.Bold)
        self.title.setFont(title_font)
        self.title.setStyleSheet(f"color: {FG_MAIN}; letter-spacing: 1px;")
        self.title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(self.title)

        container_layout.addStretch()

        # Progress Bar
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setStyleSheet(SPLASH_PROGRESS_STYLE)
        container_layout.addWidget(self.progress)

        # Status Label
        self.status = QLabel("Initializing…")
        status_font = QFont(FONT_UI, 10)
        self.status.setFont(status_font)
        self.status.setStyleSheet(f"color: {FG_DIM};")
        self.status.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(self.status)

        main_layout.addWidget(self.container)

    def center_on_screen(self):
        screen = QApplication.primaryScreen()
        screen_geo = screen.geometry()
        center_x = (screen_geo.width() - self.width()) // 2
        center_y = (screen_geo.height() - self.height()) // 2
        self.move(center_x, center_y)

    def set_status(self, message: str, progress: int) -> None:
        """Update splash status and progress bar."""
        self.status.setText(message)
        self.progress.setValue(progress)
        QApplication.processEvents()

    def finish(self, main_window: QWidget) -> None:
        """Close the splash screen."""
        self.close()
