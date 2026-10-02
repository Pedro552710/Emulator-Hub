"""Lokale BIOS-Prüfung und gezielte Spielstand-/Einstellungspfade.

Es werden ausschließlich vom Benutzer vorhandene Dateien geprüft. Der Checker
prüft Lesbarkeit und Größe, nicht Echtheit, Region oder Versionskompatibilität.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path, PurePosixPath
import re

from .errors import Cancelled, HubError

PROFILE_ROOTS = {"emulator", "localappdata", "roamingappdata", "userprofile", "documents"}


def relative_parts(value, *, allow_empty=False):
    """Validate catalog paths independently of the host operating system."""
    if not isinstance(value, str):
        raise HubError("Der Profilpfad im Katalog muss ein Text sein.")
    normalized = value.replace("\\", "/")
    if allow_empty and normalized in {"", "."}:
        return ()
    if (not normalized or normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized)
            or any(part in {"", ".", ".."} for part in normalized.split("/"))
            or any(char in normalized for char in ':<>"|?*')
            or any(ord(char) < 32 for char in normalized)):
        raise HubError("Der Katalog enthält einen ungültigen relativen Profilpfad.")
    parts = PurePosixPath(normalized).parts
    from .archives import RESERVED
    if any(part.endswith((".", " ")) or part.split(".")[0].upper() in RESERVED for part in parts):
        raise HubError("Der Katalog enthält einen ungültigen Windows-Profilpfad.")
    return parts


def emulator_directory(record, data_dir):
    if record and record.get("exe_path"):
        return Path(record["exe_path"]).absolute().parent
    if record and record.get("path"):
        return Path(record["path"]).absolute()
    raise HubError("Bitte den Emulator zuerst installieren oder seinen Ordner zuordnen.")


def _windows_documents():
    """Ask Windows for Documents, including OneDrive/administrator redirection."""
    if os.name != "nt":
        return None
    import ctypes
    import uuid

    class GUID(ctypes.Structure):
        _fields_ = [("data1", ctypes.c_uint32), ("data2", ctypes.c_uint16),
                    ("data3", ctypes.c_uint16), ("data4", ctypes.c_ubyte * 8)]

    folder_id = GUID.from_buffer_copy(uuid.UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7").bytes_le)
    value = ctypes.c_wchar_p()
    try:
        function = ctypes.windll.shell32.SHGetKnownFolderPath
        function.argtypes = [ctypes.POINTER(GUID), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_wchar_p)]
        function.restype = ctypes.c_long
        if function(ctypes.byref(folder_id), 0, None, ctypes.byref(value)) < 0:
            return None
        return Path(value.value) if value.value else None
    except (OSError, AttributeError):
        return None
    finally:
        if value:
            ctypes.windll.ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
            ctypes.windll.ole32.CoTaskMemFree(ctypes.cast(value, ctypes.c_void_p))


def _root_path(root, record, data_dir):
    user = Path(os.environ.get("USERPROFILE") or Path.home())
    roots = {
        "userprofile": user,
        "documents": _windows_documents() or user / "Documents",
        "localappdata": Path(os.environ.get("LOCALAPPDATA") or user / "AppData" / "Local"),
        "roamingappdata": Path(os.environ.get("APPDATA") or user / "AppData" / "Roaming"),
    }
    if root == "emulator":
        return emulator_directory(record, data_dir)
    if root not in roots:
        raise HubError("Der Profilpfad im Katalog verwendet einen unbekannten Basisordner.")
    return roots[root].absolute()


def _profile_path(spec, record, data_dir):
    """Honor explicitly documented native portable markers when already present."""
    portable = spec.get("portable")
    if portable:
        emulator = emulator_directory(record, data_dir)
        markers = portable.get("markers", [portable.get("marker")])
        for marker in markers:
            candidate = emulator.joinpath(*relative_parts(marker))
            present = candidate.is_dir() if portable.get("marker_type", "file") == "directory" else candidate.is_file()
            if present:
                base = emulator
                if portable.get("path_from_marker") and candidate.name == "portable.txt":
                    try:
                        if candidate.stat().st_size > 4096:
                            raise HubError("Der native portable.txt-Pfad ist zu lang. Bitte den tatsächlichen Profilordner manuell zuordnen.")
                        contents = candidate.read_text(encoding="utf-8-sig").strip()
                        if contents:
                            native = Path(contents)
                            base = native if native.is_absolute() else emulator / native
                    except (OSError, UnicodeError) as exc:
                        raise HubError(f"Der native portable.txt-Pfad konnte nicht gelesen werden: {exc}") from None
                parts = relative_parts(portable["directory"], allow_empty=True)
                return base.joinpath(*parts).absolute(), True
    base = _root_path(spec["root"], record, data_dir)
    return base.joinpath(*relative_parts(spec["directory"], allow_empty=True)), False


def _settings_data(settings):
    if settings is None:
        return {}
    if isinstance(settings, dict):
        data = settings
    elif hasattr(settings, "get"):
        # SettingsStore exposes get; avoid coupling services to Qt or storage.
        data = {name: settings.get(name, {}) for name in ("bios_overrides", "profile_overrides")}
        data["game_folders"] = settings.get("game_folders", [])
    else:
        return {}
    for name in ("bios_overrides", "profile_overrides"):
        if not isinstance(data.get(name, {}), dict):
            raise HubError("Eigene BIOS-/Sicherungszuordnungen in settings.json sind ungültig. Bitte die Einstellungen korrigieren.")
    folders = data.get("game_folders", [])
    if not isinstance(folders, list) or any(not isinstance(path, str) or not Path(path).is_absolute() for path in folders):
        raise HubError("Die Spieleordner in settings.json benötigen vollständige Dateipfade als Liste.")
    return data


def _check_cancel(event):
    if event is not None and event.is_set():
        raise Cancelled()


def _file_present(path):
    try:
        if path.is_file() and path.stat().st_size > 0:
            with path.open("rb") as handle:
                handle.read(1)
            return True
    except OSError:
        pass
    return False


def game_protection(data_dir, settings=None):
    """Read-only protections shared by profile backup and ZIP restoration."""
    from .paths import config_path
    from .state import read_json

    raw = read_json(Path(data_dir) / "library.json", {"schema_version": 1, "games": []}, "Die Spielebibliothek")
    if not isinstance(raw, dict) or not isinstance(raw.get("games"), list):
        raise HubError("Die Spielebibliothek ist beschädigt; Spielpfade können für die Sicherung nicht sicher geprüft werden.")
    protected = set()
    for game in raw["games"]:
        if not isinstance(game, dict) or not isinstance(game.get("path"), str) or not Path(game["path"]).is_absolute():
            raise HubError("Die Spielebibliothek enthält einen ungültigen Spielpfad. Bitte library.json korrigieren.")
        protected.add(Path(game["path"]).resolve())
    extensions = read_json(config_path("extensions.json", data_dir), {"extensions": {}}, "Die Dateiendungs-Konfiguration")
    if not isinstance(extensions, dict) or not isinstance(extensions.get("extensions"), dict):
        raise HubError("Die Dateiendungs-Konfiguration ist beschädigt; Spiel-Dateien können nicht sicher erkannt werden.")
    # Ambiguous .bin/.zip can also be native firmware or settings; known library
    # paths always remain protected regardless of extension or file existence.
    obvious = {suffix.casefold() for suffix, consoles in extensions["extensions"].items()
               if isinstance(suffix, str) and (isinstance(consoles, str)
                   or isinstance(consoles, list) and len(consoles) == 1)}
    obvious -= {".bin", ".zip"}
    return {"paths": protected, "extensions": obvious}


def assert_not_game_file(path, protection):
    path = Path(path)
    if path.resolve() in protection["paths"] or path.suffix.casefold() in protection["extensions"]:
        raise HubError(f"Eine Spiel-Datei darf nicht als Spielstand/Einstellung gesichert oder überschrieben werden: {path}\nBitte einen gezielten Save- oder Einstellungsordner auswählen.")


def check_bios(entry, record, data_dir, settings=None, progress=None, log=None, cancel_event=None):
    """Return German presence rows without downloading or modifying any file."""
    _check_cancel(cancel_event)
    data = _settings_data(settings)
    overrides = data.get("bios_overrides", {}).get(entry["id"])
    rows = []
    if overrides:
        specs = overrides
        if not isinstance(specs, list) or any(not isinstance(spec, dict) or not isinstance(spec.get("path"), str) for spec in specs):
            raise HubError("Eigene BIOS-Dateien benötigen eine Liste mit vollständigen Dateipfaden.")
        for index, spec in enumerate(specs):
            _check_cancel(cancel_event)
            path = Path(spec.get("path", ""))
            if not path.is_absolute():
                raise HubError("Eigene BIOS-Dateien benötigen einen vollständigen Dateipfad.")
            present = _file_present(path)
            rows.append({"label": spec.get("label") or path.name, "path": str(path),
                         "status": "vorhanden" if present else "fehlt",
                         "reason": "Eigene Datei lesbar; Echtheit und Kompatibilität werden nicht geprüft."
                         if present else "Die gewählte eigene Datei fehlt, ist leer oder nicht lesbar."})
            if progress:
                progress(round((index + 1) * 100 / len(specs)), "Eigene BIOS-Dateien prüfen")
    else:
        specs = entry.get("bios", [])
        for index, spec in enumerate(specs):
            _check_cancel(cancel_event)
            directory, _ = _profile_path(spec, record, data_dir)
            paths = [directory / name for name in spec["filenames"]]
            statuses = [_file_present(path) for path in paths]
            present = any(statuses) if spec.get("any_of", False) else all(statuses)
            displayed = " / ".join(str(path) for path in paths)
            note = spec.get("note", "")
            reason = "Datei vorhanden; Echtheit und Kompatibilität werden nicht geprüft." if present else (
                "Eigene Datei in diesem Ordner ablegen und denselben Pfad im Emulator einstellen."
            )
            if not spec.get("required", True):
                reason = "Optional: " + reason
            if note:
                reason += " " + note
            rows.append({"label": spec["label"], "path": displayed,
                         "status": "vorhanden" if present else "fehlt", "reason": reason})
            if progress:
                progress(round((index + 1) * 100 / len(specs)), "Lokale BIOS-Dateien prüfen")
    if not rows:
        note = entry.get("bios_note", "Für diesen Emulator ist kein zusätzliches BIOS im Katalog vorgesehen.")
        rows.append({"label": "BIOS / Firmware", "path": "", "status": "nicht konfiguriert", "reason": note})
    if progress:
        progress(100, "BIOS-Prüfung abgeschlossen")
    if log:
        for row in rows:
            log(f"{row['label']}: {row['status']} – {row['reason']}")
    return rows


def profile_paths(entry, record, data_dir, settings=None):
    """Resolve specific profiles; never include the entire emulator installation."""
    data = _settings_data(settings)
    own = data.get("profile_overrides", {}).get(entry["id"], {})
    if not isinstance(own, dict):
        raise HubError("Die eigene Sicherungszuordnung in settings.json ist ungültig.")
    overrides = own.get("backup_paths")
    if overrides is not None and not isinstance(overrides, list):
        raise HubError("Eigene Sicherungspfade müssen eine Liste mit gezielten Dateien oder Ordnern sein.")
    result = []
    if overrides is not None:
        emulator_root = emulator_directory(record, data_dir).resolve()
        forbidden = {emulator_root, Path(data_dir).resolve(), Path.home().resolve()}
        if record and record.get("path"):
            forbidden.add(Path(record["path"]).resolve())
        for root in PROFILE_ROOTS - {"emulator"}:
            forbidden.add(_root_path(root, record, data_dir).resolve())
        for index, value in enumerate(overrides):
            spec = {"path": value} if isinstance(value, str) else value
            if not isinstance(spec, dict) or not isinstance(spec.get("path"), str):
                raise HubError("Ein eigener Sicherungspfad benötigt einen vollständigen Dateipfad.")
            path = Path(spec.get("path", ""))
            if not path.is_absolute():
                raise HubError("Eigene Sicherungsordner benötigen vollständige Dateipfade.")
            if any(other.is_relative_to(path.resolve()) for other in forbidden) or path.resolve() == Path(path.anchor):
                raise HubError("Bitte einen gezielten Spielstand- oder Einstellungsordner wählen, keinen gesamten Programm-, Spiele- oder Benutzerordner.")
            kind = spec.get("type", "file" if path.is_file() else "directory")
            from .portable import encode_paths
            stored_path = encode_paths(str(path.absolute()), Path(data_dir) / "settings.json")
            identity = f"custom:{stored_path}:{kind}"
            result.append({"key": "p-" + hashlib.sha256(identity.encode()).hexdigest()[:20],
                           "label": spec.get("label") or path.name, "path": path.absolute(), "type": kind})
    else:
        for spec in entry.get("backup_paths", []):
            parts = relative_parts(spec["directory"])
            path, native_portable = _profile_path(spec, record, data_dir)
            identity = f"{spec['root']}:{'/'.join(parts)}:{spec.get('type', 'directory')}"
            result.append({"key": "p-" + hashlib.sha256(identity.encode()).hexdigest()[:20],
                           "label": spec["label"], "path": path, "type": spec.get("type", "directory"), "_native_portable": native_portable})
    protection = game_protection(data_dir, settings)
    game_folders = [Path(folder).resolve() for folder in data.get("game_folders", []) or []]
    seen = {}
    unique = []
    for spec in result:
        if spec["type"] not in {"file", "directory"}:
            raise HubError("Ein Sicherungspfad muss eine Datei oder ein Ordner sein.")
        resolved = spec["path"].resolve()
        if resolved in seen and spec["type"] == seen[resolved]["type"] and (spec.get("_native_portable") or seen[resolved].get("_native_portable")):
            continue
        if resolved in seen or any(resolved.is_relative_to(other) or other.is_relative_to(resolved) for other in seen):
            raise HubError("Sicherungspfade dürfen sich nicht überschneiden. Bitte die Zuordnung korrigieren.")
        if spec["type"] == "directory":
            if any(folder.is_relative_to(resolved) for folder in game_folders) or any(game.is_relative_to(resolved) for game in protection["paths"]):
                raise HubError("Dieser Profilordner enthält einen Spieleordner oder Spiel-Dateien aus der Bibliothek. Bitte gezielte Save- oder Einstellungsordner auswählen.")
        else:
            assert_not_game_file(spec["path"], protection)
        seen[resolved] = spec
        unique.append(spec)
    for spec in unique:
        spec.pop("_native_portable", None)
    return unique
