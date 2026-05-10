"""
Icon loading utilities. Resolves icons from <exe_root>/icons/ at runtime.
Supports SVG (with optional recoloring) and raster formats (PNG, JPG, ICO, BMP).
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


_RASTER_EXTS = (".png", ".jpg", ".jpeg", ".ico", ".bmp", ".gif")
_SVG_EXT = ".svg"


@lru_cache(maxsize=1)
def _icons_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).parent
        while base != base.parent:
            if (base / "main.py").exists():
                break
            base = base.parent
    return base / "icons"


def _resolve(name: str) -> Path | None:
    """Return the Path for *name* inside the icons directory, or None if missing."""
    icons = _icons_dir()
    p = Path(name)

    # If the caller supplied an extension, try it directly first.
    if p.suffix:
        candidate = icons / name
        return candidate if candidate.is_file() else None

    # Otherwise probe SVG then raster formats.
    for ext in (_SVG_EXT,) + _RASTER_EXTS:
        candidate = icons / (name + ext)
        if candidate.is_file():
            return candidate

    return None


def _render_svg(path: Path, size: QSize, color: QColor | None) -> QPixmap:
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return QPixmap()

    pixmap = QPixmap(size)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing |
        QPainter.RenderHint.SmoothPixmapTransform |
        QPainter.RenderHint.TextAntialiasing
    )
    renderer.render(painter)
    painter.end()

    if color is not None:
        # Tint: multiply alpha channel from SVG with the desired color.
        image = pixmap.toImage().convertToFormat(QImage.Format_ARGB32)
        r, g, b = color.red(), color.green(), color.blue()
        for y in range(image.height()):
            for x in range(image.width()):
                pixel = image.pixel(x, y)
                alpha = (pixel >> 24) & 0xFF
                image.setPixel(x, y, (alpha << 24) | (r << 16) | (g << 8) | b)
        pixmap = QPixmap.fromImage(image)

    return pixmap


def load_pixmap(
    name: str,
    size: int | QSize | None = None,
    color: QColor | str | None = None,
) -> QPixmap:
    """
    Load an icon as QPixmap.

    Args:
        name:  Icon name with or without extension (e.g. ``"save"`` or ``"save.svg"``).
               Subdirectory paths are supported (``"toolbar/save"``).
        size:  Desired pixel size. ``int`` → square; ``QSize`` → exact dimensions.
               ``None`` uses the image's native size (SVGs default to 16×16).
        color: Tint color applied to SVG icons. Accepts ``QColor`` or CSS hex string
               (``"#ffffff"``). Ignored for raster icons.

    Returns:
        ``QPixmap`` — empty pixmap if the icon file is not found.
    """
    if isinstance(size, int):
        size = QSize(size, size)
    if size is None:
        size = QSize(16, 16)

    if isinstance(color, str):
        color = QColor(color)

    path = _resolve(name)
    if path is None:
        return QPixmap()

    if path.suffix.lower() == _SVG_EXT:
        return _render_svg(path, size, color)

    pixmap = QPixmap(str(path))
    if not pixmap.isNull() and (pixmap.width() != size.width() or pixmap.height() != size.height()):
        pixmap = pixmap.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return pixmap


def load_icon(
    name: str,
    size: int | QSize | None = 512,
    color: QColor | str | None = None,
) -> QIcon:
    """
    Load an icon as QIcon.

    Same parameters as :func:`load_pixmap`. Returns an empty ``QIcon`` if not found.
    """
    pixmap = load_pixmap(name, size, color)
    if pixmap.isNull():
        return QIcon()
    return QIcon(pixmap)


def icon_path(name: str) -> Path | None:
    """Return the resolved filesystem path for *name*, or ``None`` if not found."""
    return _resolve(name)
