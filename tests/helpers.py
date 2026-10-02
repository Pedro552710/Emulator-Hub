import json
from pathlib import Path
import struct
import tempfile

from core.catalog import Catalog, LEGAL_NOTICE


class TemporaryDirectory(tempfile.TemporaryDirectory):
    """Testordner mit Langpfad, auch wenn TEMP/TMP einen Windows-Kurznamen enthält."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = str(Path(self.name).resolve())


def windows_executable(marker=b"version-one", *, machine=0x8664):
    image = bytearray(128)
    image[:2] = b"MZ"
    struct.pack_into("<I", image, 0x3c, 64)
    image[64:68] = b"PE\0\0"
    struct.pack_into("<H", image, 68, machine)
    return bytes(image) + marker


def make_catalog(root, *, method="auto_github"):
    entry = {
        "id": "test-emulator", "kategorie": "Nintendo", "hersteller": "Nintendo",
        "konsole": "Testkonsole", "emulator": "Testemulator", "plattformen": "Windows",
        "pc_anforderung": "Niedrig", "official_url": "https://github.com/official/emulator",
        "download_anleitung": "Offizielle Windows-Datei herunterladen.", "hinweis": LEGAL_NOTICE,
        "install_methode": method, "github_repo": "official/emulator",
        "download_muster": r"emulator-win-x64\.zip", "exe": "emulator.exe",
        "manuelle_schritte": ["Offizielle Seite öffnen.", "Windows-Archiv entpacken."],
        "archive_type": "zip",
    }
    path = Path(root) / "catalog.json"
    path.write_text(json.dumps({
        "schema_version": 1, "categories": ["Nintendo"],
        "official_sources": ["https://github.com/official/emulator"], "emulators": [entry],
    }), encoding="utf-8")
    return Catalog(path), entry


class Response:
    """Small requests-compatible response; tests never contact the internet."""

    def __init__(self, body=b"", *, status=200, headers=None, payload=None):
        self.status_code = status
        self.headers = headers or {}
        self.content = json.dumps(payload).encode() if payload is not None else body
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.closed = True

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return json.loads(self.content)

    def iter_content(self, chunk_size=8192):
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset:offset + chunk_size]
