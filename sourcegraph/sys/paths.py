from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Return the app's base directory.

    When frozen by PyInstaller this is the directory containing the .exe.
    When running from source this is the repository root.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).parent.parent.parent
