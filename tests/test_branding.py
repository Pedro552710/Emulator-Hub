"""Logo-Auswahl und Darstellung ohne Downloads oder echte Benutzerdaten."""

from pathlib import Path
import unittest
from unittest.mock import patch

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QRegion
from PySide6.QtWidgets import QApplication, QWidget

from ui.branding import HubLogo, application_icon, logo_path
from tests.helpers import TemporaryDirectory


class BrandingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    @staticmethod
    def png(path, width=80, height=40):
        path.parent.mkdir(parents=True, exist_ok=True)
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor("#e74c3c"))
        assert image.save(str(path))

    @staticmethod
    def svg(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="#4388ed"/></svg>', encoding="utf-8")

    def test_external_png_takes_precedence_over_bundled_svg(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            external, bundled = root / "program", root / "embedded"
            self.png(external / "assets" / "logo.png")
            self.svg(bundled / "assets" / "logo.svg")
            with patch("ui.branding.app_directory", return_value=external), patch("ui.branding.resource_path", return_value=bundled / "assets"):
                self.assertEqual(logo_path(), external / "assets" / "logo.png")
                icon = application_icon()
                self.assertEqual({size.width() for size in icon.availableSizes()}, {16, 32, 48, 64, 128, 256})
                self.assertEqual(icon.pixmap(QSize(128, 128)).toImage().pixelColor(64, 64), QColor("#e74c3c"))

    def test_sidebar_preserves_png_aspect_ratio_at_double_scale(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self.png(root / "assets" / "logo.png")
            with patch("ui.branding.app_directory", return_value=root), patch("ui.branding.resource_path", return_value=root / "assets"):
                widget = HubLogo()
                image = QImage(84, 84, QImage.Format.Format_ARGB32)
                image.setDevicePixelRatio(2)
                image.fill(Qt.GlobalColor.transparent)
                painter = QPainter(image)
                widget.render(painter, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)
                painter.end()
                self.assertEqual(widget.size(), QSize(42, 42))
                self.assertEqual(image.pixelColor(42, 42), QColor("#e74c3c"))
                self.assertEqual(image.pixelColor(42, 10).alpha(), 0)
                self.assertEqual(image.pixelColor(42, 73).alpha(), 0)
                self.assertEqual(image.pixelColor(1, 42), QColor("#e74c3c"))
                widget.deleteLater()

    def test_svg_preferred_in_same_directory_and_missing_assets_have_fallback(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self.png(root / "assets" / "logo.png")
            self.svg(root / "assets" / "logo.svg")
            with patch("ui.branding.app_directory", return_value=root), patch("ui.branding.resource_path", return_value=root / "assets"):
                self.assertEqual(logo_path(), root / "assets" / "logo.svg")
                self.assertEqual(application_icon().pixmap(QSize(64, 64)).toImage().pixelColor(32, 32), QColor("#4388ed"))
            missing = root / "missing"
            with patch("ui.branding.app_directory", return_value=missing), patch("ui.branding.resource_path", return_value=missing / "assets"):
                self.assertIsNone(logo_path())
                fallback = application_icon().pixmap(QSize(64, 64)).toImage()
                self.assertEqual(fallback.pixelColor(32, 32).alpha(), 255)
                self.assertFalse(application_icon().isNull())


if __name__ == "__main__":
    unittest.main()
