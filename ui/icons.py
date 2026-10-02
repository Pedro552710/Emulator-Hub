"""Einfache dunkle Qt-Symbole ohne zusätzliche Bilddateien."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


_SHAPES = {
    "folder": '<path d="M3 9V6Q3 4 5 4H9L11 7H19Q21 7 21 9V17Q21 19 19 19H5Q3 19 3 17V9Z"/><path d="M3 9H21"/>',
    "gamepad": '<path d="M7 7C10 5 14 5 17 7C20 9 22 18 19 18L15 15H9L5 18C2 18 4 9 7 7Z"/><path d="M6 11H10M8 9V13"/><circle cx="16" cy="10" r="1" fill="currentColor" stroke="none"/><circle cx="18" cy="13" r="1" fill="currentColor" stroke="none"/>',
}


def folder_icon(kind: str) -> QIcon:
    """Ordner und Gamepad in normaler und ausgegrauter Darstellung zeichnen."""
    icon = QIcon()
    for mode, color in ((QIcon.Mode.Normal, "#a9bcd5"), (QIcon.Mode.Disabled, "#61758e")):
        pixmap = QPixmap(40, 40)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" color="{color}" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{_SHAPES[kind]}</svg>'
        QSvgRenderer(svg.encode("utf-8")).render(painter)
        painter.end()
        icon.addPixmap(pixmap, mode)
    return icon
