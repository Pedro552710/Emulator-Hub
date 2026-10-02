"""Atomare Speicherung; eine beschädigte Datei wird niemals still überschrieben."""
import json
import os
from pathlib import Path
import tempfile

from .errors import HubError
from .portable import decode_paths, encode_paths


def read_installed(path):
    path = Path(path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or any(not isinstance(v, dict) for v in data.values()):
            raise ValueError()
        for key, value in data.items():
            if not isinstance(key, str) or not all(isinstance(value.get(k), str) for k in ("path", "exe_path", "version", "date")):
                raise ValueError()
        return decode_paths(data, path)
    except (OSError, ValueError):
        raise HubError(f"Die Installationsliste ist beschädigt oder nicht lesbar: {path}\nBitte diese Datei sichern und korrigieren oder umbenennen.") from None


def write_installed(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix="installed-", suffix=".tmp", delete=False) as handle:
            name = handle.name
            json.dump(encode_paths(data, path), handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    except OSError as exc:
        raise HubError(f"Die Installationsliste konnte nicht gespeichert werden: {exc}") from None
    finally:
        if name and Path(name).exists():
            Path(name).unlink(missing_ok=True)
