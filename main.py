import sys
import os
import shutil

# When frozen by PyInstaller, sys._MEIPASS (bundled intern/) is already on
# sys.path. We also need the exe directory so importlib can find the external
# plugins/ directory that lives there.
if getattr(sys, 'frozen', False):
    _exe_dir = os.path.dirname(sys.executable)
    if _exe_dir not in sys.path:
        sys.path.insert(0, _exe_dir)

from PySide6.QtWidgets import QApplication
from sourcegraph.sys.paths import app_root
from sourcegraph.sys.registry import discover_builtin_nodes
from sourcegraph.gui.main_window import MainWindow


def cleanup_pycache() -> None:
    if getattr(sys, 'frozen', False):
        return
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

    from sourcegraph.gui.splash import SourceGraphSplash
    splash = SourceGraphSplash()
    splash.show()
    app.processEvents()

    splash.set_status("Discovering nodes…", 10)
    discover_builtin_nodes()

    win = MainWindow(on_progress=splash.set_status)
    win.show()
    splash.finish(win)

    try:
        sys.exit(app.exec())
    finally:
        cleanup_pycache()


if __name__ == "__main__":
    main()
