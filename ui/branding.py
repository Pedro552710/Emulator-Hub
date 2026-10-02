"""Austauschbares Logo und scharfe Qt-Symbole für den Emulator Hub."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

from core.paths import app_directory, resource_path


# Auch ohne Bilddateien bleibt die ursprüngliche Controller-Marke verfügbar.
_FALLBACK_SVG = b'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 42 42">
<rect width="42" height="42" rx="11" fill="#203f3b"/>
<path d="M11 15C15 11 27 11 31 15C34 19 36 29 31 29L26 25H16L11 29C6 29 8 19 11 15Z"
 fill="none" stroke="#62dfb6" stroke-width="1.8"/>
<path d="M12 20H18M15 17V23" stroke="#62dfb6" stroke-width="1.8"/>
<g fill="#62dfb6"><circle cx="27.4" cy="18.4" r="1.4"/><circle cx="30.4" cy="22.4" r="1.4"/></g>
</svg>'''
_ICON_SIZES = (16, 32, 48, 64, 128, 256)


def logo_path() -> Path | None:
    """Externe Logos haben Vorrang vor eingebetteten Ressourcen der EXE."""
    for directory in (app_directory() / "assets", resource_path("assets")):
        for filename in ("logo.svg", "logo.png"):
            path = directory / filename
            if path.is_file():
                return path
    return None


def _load_logo() -> tuple[QSvgRenderer | None, QPixmap | None]:
    path = logo_path()
    if path is not None:
        if path.suffix.lower() == ".svg":
            renderer = QSvgRenderer(str(path))
            if renderer.isValid() and not renderer.defaultSize().isEmpty():
                return renderer, None
        else:
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                return None, pixmap
        logging.getLogger("emulator_hub").warning(
            "Das Logo in %s kann nicht gelesen werden. Die Standardmarke wird verwendet.", path
        )
    return QSvgRenderer(_FALLBACK_SVG), None


def _fit_rect(bounds: QRectF, source_size: QSize) -> QRectF:
    """Das Seitenverhältnis erhalten und freie Ränder transparent lassen."""
    scale = min(bounds.width() / source_size.width(), bounds.height() / source_size.height())
    width, height = source_size.width() * scale, source_size.height() * scale
    return QRectF(bounds.center().x() - width / 2, bounds.center().y() - height / 2, width, height)


def _paint_logo(painter: QPainter, bounds: QRectF, renderer: QSvgRenderer | None, pixmap: QPixmap | None) -> None:
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if renderer is not None:
        renderer.render(painter, _fit_rect(bounds, renderer.defaultSize()))
    elif pixmap is not None:
        painter.drawPixmap(_fit_rect(bounds, pixmap.size()), pixmap, QRectF(pixmap.rect()))


def application_icon() -> QIcon:
    """Fenster- und Taskleistensymbol aus demselben Logo wie die Seitenleiste."""
    renderer, source = _load_logo()
    icon = QIcon()
    for size in _ICON_SIZES:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        _paint_logo(painter, QRectF(0, 0, size, size), renderer, source)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class HubLogo(QWidget):
    """Das Logo direkt in logischen Pixeln zeichnen, auch bei hoher Skalierung."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(42, 42)
        self.setAccessibleName("Emulator-Hub-Logo")
        self._renderer, self._pixmap = _load_logo()

    def paintEvent(self, event):
        painter = QPainter(self)
        _paint_logo(painter, QRectF(self.rect()), self._renderer, self._pixmap)
        painter.end()
