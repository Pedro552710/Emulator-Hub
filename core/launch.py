"""Spielstart mit katalogisierten Argumentlisten; keine Shell oder Dateiveränderung."""

from __future__ import annotations

from pathlib import Path
import stat
import string
import subprocess

from .errors import HubError
from .installer import verify_windows_executable
from .library import PS4_PACKAGE_STATUS, is_ps4_package


def compatible_entries(catalog, console):
    return [entry for entry in catalog.items if entry.get("entry_type") != "utility"
            and (console == entry["konsole"] or console in entry.get("supported_consoles", []))]


def build_emulator_command(entry, exe, *, prefer_launcher=True):
    """GUI-Start mit optionalem lokalen Launcher; Spielargumente bleiben getrennt."""
    executable = Path(exe).resolve()
    arguments = entry.get("start_args", [])
    if (not isinstance(arguments, list) or any(not isinstance(arg, str) or not arg
            or any(ord(char) < 32 for char in arg) or "{" in arg or "}" in arg for arg in arguments)):
        raise HubError("Die Emulator-Startparameter im Katalog sind ungültig. Bitte start_args prüfen.")
    # Auch bestehende Installationen und ältere bearbeitete Kataloge sicher starten.
    if executable.name.casefold() == "shadps4.exe" and not arguments:
        arguments = ["-b"]
    launcher = entry.get("launcher")
    if isinstance(launcher, dict):
        if prefer_launcher:
            from .profiles import relative_parts
            try:
                parts = relative_parts(launcher.get("directory"))
            except HubError:
                raise HubError("Der Launcher-Unterordner im Katalog ist ungültig.") from None
            name = launcher.get("exe", "")
            if not isinstance(name, str) or Path(name).name != name or not name.lower().endswith(".exe") or any(c in name for c in "/\\:"):
                raise HubError("Die Launcher-Startdatei im Katalog ist ungültig.")
            launcher_args = launcher.get("args", [])
            if (not isinstance(launcher_args, list) or any(not isinstance(arg, str) or not arg
                    or any(ord(char) < 32 for char in arg) or "{" in arg or "}" in arg for arg in launcher_args)):
                raise HubError("Die Launcher-Startparameter im Katalog sind ungültig.")
            base = executable.parent
            for candidate in (base.joinpath(*parts, name), base / name):
                try:
                    if not candidate.is_file():
                        continue
                    resolved = candidate.resolve()
                    if (not resolved.is_relative_to(base) or resolved == executable
                            or resolved.name.casefold() == "shadps4.exe"):
                        continue
                    # Keine Launcher außerhalb des Profils über Links/Junctions verwenden.
                    chain = [candidate]
                    parent = candidate.parent
                    while parent != base:
                        chain.append(parent)
                        parent = parent.parent
                    if any(path.is_symlink() or getattr(path.lstat(), "st_file_attributes", 0)
                           & stat.FILE_ATTRIBUTE_REPARSE_POINT for path in chain):
                        continue
                    verify_windows_executable(resolved)
                except (OSError, HubError):
                    continue
                return [str(resolved), *launcher_args], "QTLauncher gestartet. Den shadPS4-Kern bei Bedarf im Version Manager über Add Custom auswählen."
        return [str(executable), *arguments], "QTLauncher nicht verfügbar. shadPS4 startet im Big-Picture-Modus (-b); den QTLauncher über die Anleitung manuell einrichten."
    return [str(executable), *arguments], entry.get("start_note")


def build_launch_command(entry, exe, game_path):
    if is_ps4_package(game_path):
        raise HubError(f"{PS4_PACKAGE_STATUS}; PKG-Dateien sind nicht direkt startbar.")
    if entry.get("entry_type") == "utility":
        raise HubError("Dieses Hilfsprogramm ist kein Emulator und kann keine Spiele starten.")
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
    if is_ps4_package(game_path) or entry.get("entry_type") == "utility":
        # Vor jeder Emulator-Auswahl und ohne Lesen des Paketinhalts ablehnen.
        build_launch_command(entry, entry.get("exe", ""), game_path)
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


def build_ps4_pkg_tool_command(entry, exe, package_path):
    """Nur den belegten GUI-Aufruf mit einem PKG-Pfad zusammensetzen."""
    if (entry.get("id") != "ps4-pkg-tool" or entry.get("entry_type") != "utility"
            or entry.get("github_repo") != "pearlxcore/PS4PKGTool"
            or entry.get("package_args") != ["{package}"]):
        raise HubError("Für dieses Hilfsprogramm ist kein belegter PKG-Aufruf hinterlegt. Bitte die Anleitung verwenden.")
    executable = Path(exe).resolve()
    if executable.name.casefold() != "ps4 pkg tool.exe" or executable.name.casefold() != entry.get("exe", "").casefold():
        raise HubError("Die Startdatei passt nicht zum hinterlegten PS4 PKG Tool. Bitte den offiziellen Programmordner zuordnen.")
    package = Path(package_path)
    if not is_ps4_package(package):
        raise HubError("Bitte eine eigene PS4-PKG-Datei auswählen. Andere Dateitypen werden nicht an das Hilfsprogramm übergeben.")
    try:
        if (package.is_symlink() or not package.is_file()
                or getattr(package.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise HubError("Die eigene PKG-Datei wurde nicht gefunden oder ist eine Verknüpfung. Bitte den Spielordner prüfen und erneut scannen.")
    except OSError as exc:
        raise HubError(f"Die eigene PKG-Datei ist nicht zugänglich. Bitte Dateipfad und Zugriffsrechte prüfen: {exc}") from None
    return [str(executable), str(package.resolve())]


def launch_ps4_pkg_tool(service, entry, package_path):
    """Übergabe an den externen PKG Viewer, ohne Installation oder Spielverlauf."""
    record = service.installed.get(entry["id"])
    if not record or not service.is_installed(entry["id"]):
        raise HubError("PS4 PKG Tool ist noch nicht installiert. Bitte das Hilfsprogramm ausdrücklich über Installieren oder die manuelle Anleitung einrichten.")
    executable = Path(record["exe_path"]).resolve()
    if not executable.is_relative_to(Path(record["path"]).resolve()):
        raise HubError("Die Startdatei liegt außerhalb des gespeicherten Hilfsprogrammordners.")
    verify_windows_executable(executable)
    command = build_ps4_pkg_tool_command(entry, executable, package_path)
    try:
        process = subprocess.Popen(command, cwd=executable.parent, shell=False)
    except OSError as exc:
        raise HubError(f"PS4 PKG Tool konnte nicht geöffnet werden. Bitte Programmordner und benötigte .NET Desktop Runtime prüfen: {exc}") from None
    service.logger.info("PS4-Paket an %s übergeben: %s", entry["emulator"], package_path)
    return process


def open_ps4_package(service, entry, package_path):
    """Übergabe für den bestehenden Hub-Service-Aufruf."""
    return launch_ps4_pkg_tool(service, entry, package_path)
