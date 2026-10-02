"""Logo und Windows-Icon aus einer eigenen SVG- oder PNG-Datei erzeugen."""
import argparse
import os
from pathlib import Path
import re
import tempfile
import xml.etree.ElementTree as ET


ICON_SIZES = (16, 32, 48, 64, 128, 256)
PNG_SIZE = 1024
_application = None


def _svg_image(source, size):
    from PIL import Image
    from PySide6.QtCore import QByteArray, QRectF, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    from PySide6.QtWidgets import QApplication

    global _application
    contents = source.read_bytes()
    if b"<!DOCTYPE" in contents.upper() or b"<!ENTITY" in contents.upper():
        raise ValueError("Das SVG darf keine externen Dokumentdefinitionen enthalten.")
    try:
        root = ET.fromstring(contents)
    except ET.ParseError as exc:
        raise ValueError("Die SVG-Datei ist ungültig und kann nicht gelesen werden.") from exc
    if root.tag.rsplit("}", 1)[-1] != "svg":
        raise ValueError("Die Datei enthält kein SVG-Logo.")
    for element in root.iter():
        for key, value in element.attrib.items():
            if key.rsplit("}", 1)[-1] == "href" and not value.startswith(("#", "data:image/")):
                raise ValueError("Das SVG muss eigenständig sein; externe Bilder sind nicht erlaubt.")
        references = " ".join([element.text or "", *element.attrib.values()])
        if any(not match.strip(" '\"").startswith("#") for match in re.findall(r"url\((.*?)\)", references, re.I)):
            raise ValueError("Das SVG muss eigenständig sein; externe Ressourcen sind nicht erlaubt.")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _application = QApplication.instance() or QApplication([])
    renderer = QSvgRenderer(QByteArray(contents))
    if not renderer.isValid():
        raise ValueError("Die SVG-Datei konnte nicht als Logo gerendert werden.")
    original = renderer.defaultSize()
    if original.width() <= 0 or original.height() <= 0:
        raise ValueError("Das SVG benötigt eine gültige Größe oder viewBox.")
    factor = min(size / original.width(), size / original.height())
    width, height = original.width() * factor, original.height() * factor
    rendered = QImage(size, size, QImage.Format.Format_RGBA8888)
    rendered.fill(Qt.GlobalColor.transparent)
    painter = QPainter(rendered)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        renderer.render(painter, QRectF((size - width) / 2, (size - height) / 2, width, height))
    finally:
        painter.end()
    return Image.frombytes("RGBA", (size, size), bytes(rendered.constBits()), "raw", "RGBA", rendered.bytesPerLine())


def _png_image(source, size):
    from PIL import Image, ImageOps

    try:
        with Image.open(source) as original:
            if original.format != "PNG":
                raise ValueError("Die gewählte Datei ist kein PNG-Bild.")
            original.load()
            image = original.convert("RGBA")
    except (OSError, SyntaxError) as exc:
        raise ValueError("Die PNG-Datei ist beschädigt oder kann nicht gelesen werden.") from exc
    fitted = ImageOps.contain(image, (size, size), Image.Resampling.LANCZOS)
    square = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    square.paste(fitted, ((size - fitted.width) // 2, (size - fitted.height) // 2))
    return square


def make_icons(source, assets_dir):
    """Alle Ausgaben vorbereiten und prüfen; ein PNG-Original nie überschreiben."""
    from PIL import Image

    source, assets_dir = Path(source).resolve(), Path(assets_dir).resolve()
    if not source.is_file():
        raise ValueError(f"Die Logo-Datei wurde nicht gefunden: {source}")
    if source.suffix.lower() == ".svg":
        master = _svg_image(source, PNG_SIZE)
    elif source.suffix.lower() == ".png":
        master = _png_image(source, PNG_SIZE)
    else:
        raise ValueError("Bitte eine SVG- oder PNG-Datei als Logo verwenden.")
    png_target, ico_target = assets_dir / "logo.png", assets_dir / "icon.ico"
    preserve_png = source == png_target
    assets_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".icons-", dir=assets_dir) as temporary:
        stage = Path(temporary)
        variants = [master.resize((size, size), Image.Resampling.LANCZOS) for size in ICON_SIZES]
        variants[-1].save(stage / "icon.ico", format="ICO", sizes=[(size, size) for size in ICON_SIZES], append_images=variants[:-1])
        with Image.open(stage / "icon.ico") as icon:
            if icon.ico.sizes() != {(size, size) for size in ICON_SIZES}:
                raise ValueError("Das erzeugte Windows-Icon enthält nicht alle benötigten Größen.")
            for size in ICON_SIZES:
                icon.ico.getimage((size, size)).load()
        if not preserve_png:
            master.save(stage / "logo.png", format="PNG", optimize=True)
            with Image.open(stage / "logo.png") as image:
                image.verify()
        # Erst nach erfolgreichem Rendern und Prüfen bestehende Dateien ersetzen.
        if not preserve_png:
            os.replace(stage / "logo.png", png_target)
        os.replace(stage / "icon.ico", ico_target)
    return png_target, ico_target


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ein eigenes Logo in logo.png und ein Windows-Icon umwandeln.")
    parser.add_argument("--assets-dir", type=Path, default=Path(__file__).resolve().parent.parent / "assets", help="Zielordner für logo.png und icon.ico.")
    args = parser.parse_args(argv)
    source = args.assets_dir / "logo.svg"
    if not source.is_file():
        source = args.assets_dir / "logo.png"
    try:
        png, icon = make_icons(source, args.assets_dir)
    except (ValueError, OSError, ImportError) as exc:
        parser.exit(1, f"Icons konnten nicht erstellt werden: {exc}\n")
    print(f"Logo: {png}\nWindows-Icon: {icon}\nGrößen: {', '.join(map(str, ICON_SIZES))} Pixel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
