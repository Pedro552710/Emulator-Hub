from pathlib import Path
import unittest

from PIL import Image

from tools.make_icons import ICON_SIZES, make_icons
from tests.helpers import TemporaryDirectory


class MakeIconTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_svg_produces_all_windows_sizes_and_transparent_png(self):
        source = Path(__file__).resolve().parent.parent / "assets" / "logo.svg"
        png, icon = make_icons(source, self.root)
        with Image.open(icon) as image:
            self.assertEqual(image.ico.sizes(), {(size, size) for size in ICON_SIZES})
            for size in ICON_SIZES:
                self.assertEqual(image.ico.getimage((size, size)).size, (size, size))
        with Image.open(png) as image:
            self.assertEqual(image.size, (1024, 1024))
            self.assertEqual(image.getpixel((0, 0))[3], 0)
            self.assertGreater(image.getpixel((512, 512))[3], 0)

    def test_png_original_is_preserved_and_non_square_logo_is_padded(self):
        source = self.root / "logo.png"
        Image.new("RGBA", (80, 40), (98, 223, 182, 255)).save(source)
        original = source.read_bytes()
        _, icon = make_icons(source, self.root)
        self.assertEqual(source.read_bytes(), original)
        with Image.open(icon) as image:
            rendered = image.ico.getimage((256, 256))
            self.assertEqual(rendered.getpixel((128, 0))[3], 0)
            self.assertEqual(rendered.getpixel((128, 128)), (98, 223, 182, 255))

    def test_invalid_or_external_svg_keeps_previous_outputs(self):
        png, icon = self.root / "logo.png", self.root / "icon.ico"
        png.write_bytes(b"previous png")
        icon.write_bytes(b"previous ico")
        source = self.root / "logo.svg"
        for contents in ('<svg', '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://example.test/image.png"/></svg>'):
            source.write_text(contents, encoding="utf-8")
            with self.assertRaises(ValueError):
                make_icons(source, self.root)
            self.assertEqual(png.read_bytes(), b"previous png")
            self.assertEqual(icon.read_bytes(), b"previous ico")


if __name__ == "__main__":
    unittest.main()
