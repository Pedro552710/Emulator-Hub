"""Lokale Ordner öffnen, ohne Spiel-Dateien zu lesen oder zu verändern."""
import os
from pathlib import Path
import re

from .archives import RESERVED
from .errors import HubError
from . import paths
from .portable import portable_enabled
from .profiles import _windows_documents


def folder_name(entry):
    """Emulatornamen als einzelnen Windows-sicheren Ordnernamen verwenden."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", entry["emulator"])
    name = " ".join(name.split()).strip(" .")[:90].rstrip(" .")
    if not name or name.split(".")[0].upper() in RESERVED:
        name = entry["id"]
    return name


def games_directories(settings):
    directories = settings.get("games_dir", {})
    if not isinstance(directories, dict):
        raise HubError("Die Spiele-Ordner in settings.json sind ungültig. Bitte games_dir als Zuordnung von Emulator-ID zu Ordnerpfad korrigieren.")
    return directories


def games_directory(entry, settings, catalog):
    directories = games_directories(settings)
    chosen = directories.get(entry["id"])
    if chosen is not None:
        if not isinstance(chosen, str) or not chosen.strip() or not Path(chosen).is_absolute():
            raise HubError("Der gespeicherte Spiele-Ordner ist ungültig. Bitte über Spiele-Ordner ändern einen vollständigen Ordnerpfad wählen oder auf Standard zurücksetzen.")
        return Path(chosen)
    name = folder_name(entry)
    if any(item["id"] != entry["id"] and folder_name(item).casefold() == name.casefold() for item in catalog.items):
        name += " (" + entry["id"] + ")"
    if portable_enabled():
        return paths.app_directory() / "Games" / name
    documents = _windows_documents() or Path(os.environ.get("USERPROFILE") or Path.home()) / "Documents"
    return documents / "EmulatorHub" / "Games" / name


def set_games_directory(entry, path, settings):
    if not isinstance(path, (str, Path)) or not str(path).strip():
        raise HubError("Bitte einen Spiele-Ordner auswählen.")
    path = Path(path)
    if not path.is_absolute():
        raise HubError("Der Spiele-Ordner benötigt einen vollständigen Ordnerpfad.")
    if path.exists() and not path.is_dir():
        raise HubError("Der gewählte Spiele-Pfad ist eine Datei. Bitte einen Ordner auswählen.")
    directories = games_directories(settings)
    directories[entry["id"]] = str(path)
    settings.set("games_dir", directories)
    return path


def reset_games_directory(entry, settings):
    directories = games_directories(settings)
    directories.pop(entry["id"], None)
    settings.set("games_dir", directories)


def open_directory(path):
    path = Path(path)
    if not path.is_dir():
        raise HubError(f"Der Ordner wurde nicht gefunden: {path}\nBitte den gespeicherten Ordnerpfad prüfen.")
    try:
        os.startfile(str(path))
    except OSError as exc:
        raise HubError(f"Der Ordner konnte nicht im Windows-Explorer geöffnet werden: {path}\n{exc}") from None
    return path
