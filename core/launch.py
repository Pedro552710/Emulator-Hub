"""Spielstart mit katalogisierten Argumentlisten; keine Shell oder Dateiveränderung."""

from __future__ import annotations

from pathlib import Path
import stat
import string
import subprocess

from .errors import HubError
from .installer import verify_windows_executable


def compatible_entries(catalog, console):
    return [entry for entry in catalog.items if console == entry["konsole"] or console in entry.get("supported_consoles", [])]


def build_launch_command(entry, exe, game_path):
    executable = Path(exe).resolve()
    game = Path(game_path)
    try:
        if game.is_symlink() or not game.is_file() or getattr(game.stat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise HubError("Die eigene Spiel-Datei wurde nicht gefunden oder ist eine Verknüpfung. Bitte den Spielordner prüfen und erneut scannen.")
    except OSError as exc:
        raise HubError(f"Die eigene Spiel-Datei konnte nicht gelesen werden. Bitte Zugriff und Spielordner prüfen: {exc}") from None
    game = game.resolve()
    extensions = entry.get("launch_extensions")
    if extensions is not None:
        if not isinstance(extensions, list) or any(not isinstance(s, str) for s in extensions):
            raise HubError("Die erlaubten Spiel-Dateiendungen im Katalog sind ungültig. Bitte launch_extensions prüfen.")
        if game.suffix.casefold() not in {s.casefold() for s in extensions}:
            note = entry.get("launch_note") or "Bitte das Spiel im unterstützten Format über die Emulatoroberfläche öffnen."
            raise HubError(f"Dieses Dateiformat kann mit dem gewählten Emulator nicht direkt gestartet werden. {note}")
    profiles = entry.get("launch_profiles", {})
    args = entry.get("launch_args")
    if entry.get("exe") and executable.name.casefold() != entry["exe"].casefold():
        # Alternative Programme benötigen ein eigenes dokumentiertes Profil.
        args = None
    if isinstance(profiles, dict):
        for filename, profile in profiles.items():
            if isinstance(filename, str) and filename.casefold() == executable.name.casefold():
                args = profile
                break
    if not isinstance(args, list) or not args:
        note = entry.get("launch_note") or "Bitte das Spiel über die Oberfläche des Emulators öffnen."
        raise HubError(f"Für diese Startdatei ist kein automatischer Spielstart hinterlegt. {note}")
    values = {"game": str(game), "game_dir": str(game.parent), "game_stem": game.stem,
              "exe_dir": str(executable.parent)}
    command = [str(executable)]
    formatter = string.Formatter()
    uses_game = False
    try:
        for template in args:
            if not isinstance(template, str) or not template or any(ord(c) < 32 for c in template):
                raise ValueError()
            for _, field, specification, conversion in formatter.parse(template):
                if field is not None:
                    if field not in values or specification or conversion:
                        raise ValueError()
                    uses_game |= field in {"game", "game_stem"}
            command.append(template.format_map(values))
    except (ValueError, KeyError):
        raise HubError("Die Startparameter im Katalog sind ungültig. Bitte launch_args bzw. launch_profiles prüfen.") from None
    if not uses_game:
        raise HubError("Die Startparameter enthalten keinen Spiel-Dateipfad oder Spielnamen. Bitte den Katalog prüfen.")
    return command


def launch_game(service, entry, game_path):
    identifier = entry["id"]
    record = service.installed.get(identifier)
    if not record or not service.is_installed(identifier):
        raise HubError("Für dieses Spiel ist der passende Emulator noch nicht installiert. Bitte zuerst Installieren wählen.")
    executable = Path(record["exe_path"]).resolve()
    if not executable.is_relative_to(Path(record["path"]).resolve()):
        raise HubError("Die Startdatei liegt außerhalb des gespeicherten Emulatorordners.")
    verify_windows_executable(executable, require_x64=False)
    command = build_launch_command(entry, executable, game_path)
    try:
        process = subprocess.Popen(command, cwd=executable.parent, shell=False)
    except OSError as exc:
        raise HubError(f"Das Spiel konnte nicht gestartet werden. Bitte Emulator und Spiel-Datei prüfen: {exc}") from None
    service.logger.info("%s gestartet: %s", entry["emulator"], game_path)
    return process
