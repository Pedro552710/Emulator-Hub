"""Gemeinsame atomare JSON-Speicherung für neue lokale Benutzerdaten."""
import copy
import json
import os
from pathlib import Path
import tempfile

from .errors import HubError
from .portable import decode_paths, encode_paths


def read_json(path, default, label="Datei"):
    path = Path(path)
    if not path.exists():
        return copy.deepcopy(default)
    try:
        return decode_paths(json.loads(path.read_text(encoding="utf-8-sig")), path)
    except (OSError, UnicodeError, ValueError) as exc:
        raise HubError(f"{label} konnte nicht gelesen werden: {path}\nBitte die Datei sichern und korrigieren oder umbenennen. {exc}") from None


def write_json(path, data, label="Datei"):
    path = Path(path)
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=path.stem + "-", suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(encode_paths(data, path), handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except (OSError, TypeError, ValueError) as exc:
        raise HubError(f"{label} konnte nicht gespeichert werden: {exc}") from None
    finally:
        if temporary and temporary.exists():
            temporary.unlink(missing_ok=True)
