import sys
import os
import shutil
from PySide6.QtWidgets import QApplication
from gui.main_window   import MainWindow


def cleanup_pycache() -> None:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for root, dirs, _ in os.walk(base_dir):
        for d in dirs:
            if d == "__pycache__":
                path = os.path.join(root, d)
                try:
                    shutil.rmtree(path)
                except Exception:
                    pass


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    try:
        sys.exit(app.exec())
    finally:
        cleanup_pycache()


if __name__ == "__main__":
    main()
