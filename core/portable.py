"""Programmlokale Daten und verschiebbare Pfade im portablen Modus."""
from pathlib import Path, PurePosixPath

from .errors import HubError
from . import paths

PREFIX = "@hub:/"


def portable_enabled():
    return (paths.app_directory() / "portable.flag").is_file()


def portable_data_dir():
    return paths.app_directory() / "data"


def _root(state_path):
    program = paths.app_directory().resolve()
    return program if Path(state_path).resolve().parent == program / "data" else None


def _walk(value, convert):
    if isinstance(value, dict):
        return {key: _walk(item, convert) for key, item in value.items()}
    if isinstance(value, list):
        return [_walk(item, convert) for item in value]
    return convert(value) if isinstance(value, str) else value


def encode_paths(value, state_path):
    """Nur programmlokale absolute Pfade relativ speichern; externe beibehalten."""
    root = _root(state_path)
    if root is None or not portable_enabled():
        return value

    def encode(text):
        candidate = Path(text)
        if candidate.is_absolute():
            resolved = candidate.resolve()
            if resolved.is_relative_to(root):
                return PREFIX + resolved.relative_to(root).as_posix()
        return text

    return _walk(value, encode)


def decode_paths(value, state_path):
    """Beim Lesen relativ gespeicherte Pfade am aktuellen Programmort auflösen."""
    root = _root(state_path)

    def decode(text):
        if not text.startswith(PREFIX):
            return text
        relative = PurePosixPath(text[len(PREFIX):])
        if root is None or relative.is_absolute() or any(part in ("..", ".") or ":" in part or "\\" in part for part in relative.parts):
            raise HubError("Ein portabler Datenpfad ist ungültig. Bitte die JSON-Datei sichern und korrigieren; portable Daten gehören in den Ordner data neben dem Programm.")
        target = (root / Path(*relative.parts)).resolve()
        if not target.is_relative_to(root):
            raise HubError("Ein portabler Datenpfad führt außerhalb des Programmordners.")
        return str(target)

    return _walk(value, decode)
