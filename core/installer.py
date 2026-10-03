"""Download, Integritätsprüfung und transaktionale portable Installation."""
from datetime import datetime, timezone
from dataclasses import dataclass
import copy
import hashlib
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import threading
import uuid

from packaging.version import Version, InvalidVersion
import requests

from .archives import extract_archive, assert_plain_tree, remove_managed_tree
from .errors import HubError, Cancelled
from .github import GitHubClient
from .security import URLPolicy
from .shortcuts import create_shortcuts, remove_shortcuts
from .storage import read_installed, write_installed
from .winget import WingetClient
from .settings import SettingsStore
from .paths import ensure_config
from .systemcheck import load_thresholds, detect_hardware, assess
from .portable import portable_enabled, portable_data_dir

MAX_DOWNLOAD = 2 * 1024 ** 3
SETTINGS_EXTENSIONS = {".ini", ".cfg", ".json", ".toml", ".yaml", ".yml", ".xml"}


@dataclass(frozen=True)
class DownloadPreview:
    """Reviewed download metadata; the archive is fetched only after a UI click."""

    entry_id: str
    source: str
    version: str
    asset_name: str
    sha256: str | None
    notice: str
    token: str


def default_data_dir():
    if portable_enabled():
        return portable_data_dir()
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))) / "EmulatorHub"


def _version_newer(latest, current):
    if current in ("", "unbekannt", "manuell"):
        return False
    try:
        return Version(latest.lstrip("vV")) > Version(current.lstrip("vV"))
    except InvalidVersion:
        return latest != current


def find_executable(folder, entry):
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise HubError("Der ausgewählte Ordner wurde nicht gefunden.")
    names = [entry.get("exe", ""), *entry.get("alternative_exes", [])]
    names = {n.casefold() for n in names if n and Path(n).name == n and n.lower().endswith(".exe")}
    matches = [p for p in folder.rglob("*.exe") if p.name.casefold() in names
               and p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(folder)]
    if not matches:
        raise HubError(f"Startdatei nicht gefunden ({entry.get('exe') or 'EXE nicht hinterlegt'}). Bitte den entpackten Emulatorordner auswählen.")
    # Reihenfolge priorisiert die dokumentierte Startdatei über Alternativen.
    primary = [p for p in matches if p.name.casefold() == entry.get("exe", "").casefold()]
    matches = primary or matches
    if len(matches) != 1:
        raise HubError("Mehrere passende Startdateien gefunden. Bitte einen spezifischeren Unterordner auswählen.")
    return matches[0]


def verify_windows_executable(path, require_x64=True):
    try:
        with Path(path).open("rb") as handle:
            head = handle.read(64)
            if len(head) < 64 or head[:2] != b"MZ":
                raise ValueError()
            handle.seek(struct.unpack_from("<I", head, 0x3c)[0])
            signature = handle.read(6)
            if signature[:4] != b"PE\x00\x00":
                raise ValueError()
            machine = struct.unpack_from("<H", signature, 4)[0]
            if machine not in ({0x8664} if require_x64 else {0x8664, 0x14c}):
                raise ValueError()
    except (OSError, ValueError, struct.error):
        raise HubError("Die Startdatei ist keine passende Windows-EXE. Bitte die offizielle Windows-x64-Version verwenden.") from None


class HubService:
    def __init__(self, catalog, data_dir=None):
        self.catalog = catalog
        self.data_dir = Path(data_dir or default_data_dir()).resolve()
        self.emulator_dir = self.data_dir / "emulators"
        self.emulator_dir.mkdir(parents=True, exist_ok=True)
        if self.data_dir.is_symlink() or self.emulator_dir.is_symlink():
            raise HubError("Der Datenordner darf keine Verknüpfung sein.")
        self.installed_path = self.data_dir / "installed.json"
        self.installed = read_installed(self.installed_path)
        self.latest_versions = {}
        self._download_previews = {}
        self.policy = URLPolicy(catalog.official_sources)
        self.github = GitHubClient(self.policy)
        self.winget = WingetClient(self.policy)
        self.log_path = self.data_dir / "hub.log"
        self.logger = logging.getLogger(f"EmulatorHub.{self.data_dir}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        if not self.logger.handlers:
            handler = RotatingFileHandler(self.log_path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
            self.logger.addHandler(handler)
        self._lock = threading.RLock()
        self.settings = SettingsStore(self.data_dir)
        ensure_config("system_requirements.json", self.data_dir)
        self.thresholds = load_thresholds(self.data_dir)
        self.system_report = self.settings.get("system_report")
        if not isinstance(self.system_report, dict):
            self.system_report = None
        from .library import LibraryStore
        ensure_config("extensions.json", self.data_dir)
        self.library = LibraryStore(self.data_dir, catalog, self.settings, launcher=self._launch_game)
        from .metadata import MetadataService
        self.metadata = MetadataService(self.data_dir, self.settings)

    def _launch_game(self, game, emulator_id=None):
        from .launch import compatible_entries, launch_game
        from .library import is_ps4_package
        if is_ps4_package(game):
            raise HubError("Im PS4 PKG Tool installieren; PKG-Dateien sind nicht direkt startbar.")
        candidates = compatible_entries(self.catalog, game["console"])
        if not candidates:
            raise HubError("Für diese Konsole ist noch kein Emulator im Katalog hinterlegt.")
        if emulator_id:
            entry = next((e for e in candidates if e["id"] == emulator_id), None)
            if entry is None:
                raise HubError("Der gewählte Emulator passt nicht zur zugeordneten Konsole.")
        else:
            entry = next((e for e in candidates if self.is_installed(e["id"])), candidates[0])
        process = launch_game(self, entry, game["path"])
        game["emulator_id"] = entry["id"]
        try:
            self.settings.touch_emulator(entry["id"])
        except HubError as exc:
            self.logger.warning("Spiel gestartet; Emulator-Verlauf konnte nicht gespeichert werden: %s", exc)
        return process

    def launch_game(self, game_id, emulator_id=None):
        result = self.library.launch_game(game_id, emulator_id)
        if getattr(self.library, "last_warning", ""):
            self.logger.warning(self.library.last_warning)
        return result

    def open_ps4_package(self, game_id):
        from .launch import open_ps4_package
        from .library import is_ps4_package
        game = self.library.get_game(game_id)
        if not is_ps4_package(game):
            raise HubError("Bitte ein PS4-Paket aus der Bibliothek auswählen. Das Hilfsprogramm ist nur für eigene PKG-Dateien vorgesehen.")
        entry = self.catalog.by_id("ps4-pkg-tool")
        return open_ps4_package(self, entry, game["path"])

    def systemcheck(self, progress, log, cancel_event):
        self.thresholds = load_thresholds(self.data_dir)
        report = detect_hardware(progress, lambda text: self._log(log, text), cancel_event, self.thresholds)
        self.settings.set("system_report", report)
        self.system_report = report
        return report

    def compatibility(self, entry):
        return assess(entry, self.system_report, self.thresholds)

    def _profile_record(self, entry):
        record = self.installed.get(entry["id"])
        if not record or not self.is_installed(entry["id"]):
            raise HubError("Bitte diesen Emulator zunächst installieren oder seinen vorhandenen Ordner zuordnen.")
        return record

    def check_bios(self, entry, progress, log, cancel_event):
        from .profiles import check_bios
        with self._lock:
            return check_bios(entry, self._profile_record(entry), self.data_dir, self.settings,
                              progress, lambda text: self._log(log, text), cancel_event)

    def profile_paths(self, entry):
        from .profiles import profile_paths
        return profile_paths(entry, self._profile_record(entry), self.data_dir, self.settings)

    def backup(self, entry, destination, progress, log, cancel_event):
        from .backup import BackupManager
        with self._lock:
            return BackupManager(self.data_dir).backup(entry, self._profile_record(entry), destination,
                    progress, lambda text: self._log(log, text), cancel_event, self.settings)

    def restore_backup(self, entry, archive, progress, log, cancel_event):
        from .backup import BackupManager
        with self._lock:
            return BackupManager(self.data_dir).restore(entry, self._profile_record(entry), archive,
                    progress, lambda text: self._log(log, text), cancel_event, self.settings)

    def update_all(self, progress, log, cancel_event):
        """Fehler einzelner Emulatoren isolieren und den Gesamtfortschritt melden."""
        with self._lock:
            checked = self.check_updates(lambda value, phase: progress(int(max(0, value) * .2), phase), log, cancel_event)
            result = {"updated": [], "failed": {}, "skipped": [], "cancelled": False}
            candidates = []
            for entry in self.catalog.visible_items(self.settings.get("show_hidden", False)):
                if entry.get("deprecated"):
                    if entry["id"] in self.installed:
                        result["skipped"].append(entry["id"])
                        self._log(log, entry["deprecated_note"])
                    continue
                if entry.get("entry_type") == "utility":
                    if entry["id"] in self.installed:
                        result["skipped"].append(entry["id"])
                        self._log(log, f"{entry['emulator']}: Hilfsprogramme nur nach ausdrücklichem Installationsklick aktualisieren.")
                    continue
                record = self.installed.get(entry["id"])
                if not record:
                    continue
                if entry["id"] not in checked or not _version_newer(checked[entry["id"]], record["version"]):
                    result["skipped"].append(entry["id"])
                    continue
                if entry["install_methode"] == "manuell" or (not record.get("managed") and record.get("method") != "winget"):
                    result["skipped"].append(entry["id"])
                    self._log(log, f"{entry['emulator']}: Aktualisierung bitte manuell durchführen.")
                    continue
                candidates.append(entry)
            for index, entry in enumerate(candidates):
                if cancel_event.is_set():
                    result["cancelled"] = True
                    break
                def overall(percent, phase, index=index):
                    fraction = max(0, min(100, percent)) / 100
                    progress(int(20 + 80 * (index + fraction) / len(candidates)), f"{index+1}/{len(candidates)} · {entry['emulator']} · {phase}")
                try:
                    self.install(entry, overall, log, cancel_event, shortcuts={})
                    result["updated"].append(entry["id"])
                except Cancelled:
                    result["cancelled"] = True
                    break
                except Exception as exc:
                    result["failed"][entry["id"]] = str(exc)
                    self._log(log, f"{entry['emulator']}: Aktualisierung fehlgeschlagen; nächster Emulator wird fortgesetzt. {exc}")
            progress(100, "Aktualisierung abgebrochen." if result["cancelled"] else "Alle Aktualisierungen abgeschlossen.")
            self._log(log, f"Gesamt: {len(result['updated'])} aktualisiert, {len(result['failed'])} Fehler, {len(result['skipped'])} unverändert oder manuell zu prüfen.")
            return result

    def _log(self, callback, message):
        self.logger.info(message)
        callback(message)

    def _save(self, records):
        write_installed(self.installed_path, records)
        self.installed = records

    def is_installed(self, identifier):
        record = self.installed.get(identifier)
        return bool(record and Path(record["exe_path"]).is_file())

    def open_emulator_folder(self, entry):
        from .folders import open_directory
        record = self.installed.get(entry["id"])
        if not record:
            raise HubError("Dieser Emulator ist noch nicht installiert. Bitte ihn zuerst installieren oder seinen vorhandenen Ordner zuordnen.")
        path = Path(record["path"])
        if not path.is_dir():
            raise HubError(f"Der gespeicherte Emulator-Ordner existiert nicht mehr: {path}\nBitte den Emulator erneut installieren oder seinen aktuellen Ordner zuordnen.")
        return open_directory(path)

    def games_directory(self, entry):
        from .folders import games_directory
        return games_directory(entry, self.settings, self.catalog)

    def set_games_directory(self, entry, path):
        from .folders import set_games_directory
        return set_games_directory(entry, path, self.settings)

    def reset_games_directory(self, entry):
        from .folders import reset_games_directory
        reset_games_directory(entry, self.settings)
        return self.games_directory(entry)

    def open_games_folder(self, entry):
        from .folders import open_directory
        path = self.games_directory(entry)
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HubError(f"Der Spiele-Ordner konnte nicht angelegt werden: {path}\nBitte Zugriffsrechte und den Ordnerpfad prüfen. {exc}") from None
        # Auch erstmals benutzte Standardpfade pro Emulator festhalten.
        self.set_games_directory(entry, path)
        return open_directory(path)

    def status(self, identifier):
        if not self.is_installed(identifier):
            return "nicht installiert"
        latest = self.latest_versions.get(identifier)
        if latest and _version_newer(latest, self.installed[identifier]["version"]):
            return "Update verfügbar"
        return "installiert"

    def open_official(self, entry):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        self.policy.validate(entry["official_url"])
        if not QDesktopServices.openUrl(QUrl(entry["official_url"])):
            raise HubError("Der Standardbrowser konnte nicht geöffnet werden.")

    def start(self, entry):
        from .launch import build_emulator_command
        record = self.installed.get(entry["id"])
        if not record or not self.is_installed(entry["id"]):
            raise HubError("Die Startdatei wurde nicht gefunden. Bitte den Emulator erneut installieren oder den Ordner zuordnen.")
        executable = Path(record["exe_path"]).resolve()
        if not executable.is_relative_to(Path(record["path"]).resolve()):
            raise HubError("Die Startdatei liegt außerhalb des gespeicherten Emulatorordners.")
        verify_windows_executable(executable, require_x64=False)
        command, note = build_emulator_command(entry, executable)
        try:
            try:
                subprocess.Popen(command, cwd=Path(command[0]).parent, shell=False)
            except OSError as exc:
                if Path(command[0]) == executable or not entry.get("launcher"):
                    raise
                self.logger.warning("QTLauncher konnte nicht gestartet werden: %s", exc)
                command, note = build_emulator_command(entry, executable, prefer_launcher=False)
                subprocess.Popen(command, cwd=executable.parent, shell=False)
                note = "QTLauncher konnte nicht gestartet werden. shadPS4 startet im Big-Picture-Modus (-b). Bitte die manuelle Launcher-Einrichtung prüfen."
            self.logger.info("%s gestartet", entry["emulator"])
            if note:
                self.logger.info("%s", note)
            if entry.get("entry_type") != "utility":
                try:
                    self.settings.touch_emulator(entry["id"])
                except HubError as exc:
                    self.logger.warning("Emulator gestartet, Verlauf konnte nicht gespeichert werden: %s", exc)
            return note
        except OSError as exc:
            raise HubError(f"Der Emulator konnte nicht gestartet werden: {exc}") from None

    def register_manual(self, entry, folder):
        with self._lock:
            executable = find_executable(folder, entry)
            verify_windows_executable(executable, require_x64=False)
            previous = self.installed.get(entry["id"], {})
            if previous.get("managed") or previous.get("method") == "winget":
                if Path(folder).resolve() == Path(previous["path"]).resolve():
                    return previous
                raise HubError("Dieser Emulator wird bereits automatisch verwaltet. Bitte zuerst deinstallieren, bevor du einen anderen Ordner zuordnest.")
            record = {"path": str(Path(folder).resolve()), "exe_path": str(executable.resolve()),
                      "version": "unbekannt", "date": datetime.now(timezone.utc).isoformat(),
                      "managed": False, "method": "manuell", "shortcuts": []}
            records = dict(self.installed)
            records[entry["id"]] = record
            self._save(records)
            self.logger.info("%s manuell zugeordnet: %s", entry["emulator"], folder)
            return record

    def _download(self, url, path, progress, cancel_event, expected_size=None):
        received = 0
        digest = hashlib.sha256()
        try:
            with self.policy.get(url, stream=True) as response:
                total = int(response.headers.get("Content-Length", 0)) or expected_size or 0
                if total > MAX_DOWNLOAD:
                    raise HubError("Der Download überschreitet die zulässige Größe (2 GiB).")
                with Path(path).open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=256 * 1024):
                        if cancel_event.is_set():
                            raise Cancelled()
                        if not chunk:
                            continue
                        received += len(chunk)
                        if received > MAX_DOWNLOAD:
                            raise HubError("Der Download ist ungewöhnlich groß und wurde gestoppt.")
                        handle.write(chunk)
                        digest.update(chunk)
                        percent = min(84, int(received / total * 84)) if total else -1
                        progress(percent, f"Herunterladen · {received / 1024**2:.1f} MiB" + (f" / {total / 1024**2:.1f} MiB" if total else ""))
                if not received or (total and received != total) or (expected_size and received != expected_size):
                    raise HubError("Der Download ist unvollständig. Bitte erneut versuchen.")
        except HubError:
            raise
        except (OSError, requests.exceptions.RequestException, ValueError) as exc:
            raise HubError(f"Herunterladen fehlgeschlagen. Bitte Verbindung und freien Speicherplatz prüfen: {exc}") from None
        return digest.hexdigest()

    def _checksum(self, entry, release, asset):
        digest = asset.get("digest", "") if asset else ""
        if digest and re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest):
            return digest.split(":")[1].lower()
        if entry.get("sha256"):
            return entry["sha256"].lower()
        url = entry.get("checksum_url")
        target_name = asset["name"] if asset else Path(entry.get("direct_url", "")).name
        if not url and release:
            pattern = entry.get("checksum_muster")
            checks = [a for a in release["assets"] if
                      (pattern and re.fullmatch(pattern, a.get("name", ""), re.I))
                      or a.get("name", "").lower() in (target_name.lower() + ".sha256", target_name.lower() + ".sha256sum", "sha256sums", "sha256sums.txt", "checksums.sha256", "checksums.txt")]
            per_file = [a for a in checks if a.get("name", "").lower().startswith(target_name.lower() + ".sha256")]
            checks = per_file or checks
            if len(checks) == 1:
                url = checks[0]["browser_download_url"]
            elif checks:
                raise HubError("Mehrere Prüfsummendateien gefunden. Installation gestoppt; bitte die Anleitung verwenden.")
        if not url:
            return None
        with self.policy.get(url, stream=True) as response:
            raw = bytearray()
            for chunk in response.iter_content(65536):
                raw.extend(chunk)
                if len(raw) > 1024 * 1024:
                    raise HubError("Die Prüfsummendatei ist ungewöhnlich groß.")
        text = raw.decode("utf-8-sig", errors="replace")
        for line in text.splitlines():
            match = re.fullmatch(r"\s*([a-fA-F0-9]{64})(?:\s+\*?(.+?))?\s*", line)
            if match and (match[2] == target_name or (not match[2] and len(text.splitlines()) == 1)):
                return match[1].lower()
            match = re.fullmatch(r"SHA256\s*\((.+)\)\s*=\s*([a-fA-F0-9]{64})", line, re.I)
            if match and match[1] == target_name:
                return match[2].lower()
        raise HubError("Die veröffentlichte SHA-256-Prüfsumme konnte nicht eindeutig gelesen werden. Installation gestoppt.")

    def prepare_install(self, entry):
        """Resolve a stable utility release without downloading its executable archive."""
        with self._lock:
            if entry.get("deprecated"):
                raise HubError(entry["deprecated_note"])
            if entry.get("entry_type") != "utility" or entry.get("install_methode") != "auto_github":
                raise HubError("Für dieses Hilfsprogramm bitte die manuelle Anleitung verwenden.")
            release = self.github.latest(entry["github_repo"], force=True)
            asset = self.github.asset(entry, release)
            expected = self._checksum(entry, release, asset)
            if not expected:
                raise HubError("Die offizielle Quelle veröffentlicht für dieses Asset keine SHA-256-Prüfsumme. Bitte die manuelle Anleitung verwenden; das Hilfsprogramm wird nicht automatisch heruntergeladen.")
            checksum = f"SHA-256 der offiziellen Quelle: {expected}"
            source = asset["browser_download_url"]
            notice = (f"{entry['emulator']} ist ein Drittprogramm und stammt nicht vom Emulator-Hub-Projekt.\n\n"
                      f"Quelle: {source}\nRelease: {release['tag_name']}\nDatei: {asset['name']}\n{checksum}\n\n"
                      "Antivirusprogramme können bei unsignierten Programmen warnen. "
                      "Der Hub lädt das Programm erst nach deinem ausdrücklichen Installationsklick herunter.\n"
                      "PS4 PKG Tool benötigt die separat vorhandene .NET 10 Desktop Runtime; Lizenz: GPL-3.0.")
            preview = DownloadPreview(entry["id"], source, release["tag_name"], asset["name"],
                                      expected, notice, uuid.uuid4().hex)
            # Keep the release private so callers cannot replace the reviewed URL or hash.
            self._download_previews = {preview.token: (preview, entry["github_repo"],
                                                       copy.deepcopy(release), copy.deepcopy(asset))}
            return preview

    def install(self, entry, progress_callback, log_callback, cancel_event, shortcuts=None, *, preview=None):
        with self._lock:
            if entry.get("deprecated"):
                raise HubError(entry["deprecated_note"])
            prepared = None
            if entry.get("entry_type") == "utility":
                prepared = self._download_previews.get(getattr(preview, "token", None))
                if (not prepared or prepared[0] != preview or preview.entry_id != entry["id"]
                        or prepared[1] != entry.get("github_repo")):
                    raise HubError("Dieses Drittprogramm benötigt zuerst den Downloadhinweis und einen ausdrücklichen Installationsklick. Bitte Installieren wählen.")
                self._download_previews.pop(preview.token)
            return self._install(entry, progress_callback, log_callback, cancel_event, shortcuts or {}, prepared)

    def _install(self, entry, progress, log, cancel_event, shortcuts, prepared=None):
        if entry.get("deprecated"):
            raise HubError(entry["deprecated_note"])
        method = entry["install_methode"]
        if method == "manuell":
            raise HubError("Für diesen Emulator ist eine manuelle Einrichtung vorgesehen. Bitte die Anleitung verwenden.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", entry["id"]):
            raise HubError("Ungültige Emulator-ID im Katalog.")
        target = self.emulator_dir / entry["id"]
        previous = self.installed.get(entry["id"])
        if method == "winget":
            if previous and previous.get("method") != "winget":
                raise HubError("Bitte zuerst die vorhandene Installation oder manuelle Zuordnung entfernen, bevor du WinGet verwendest.")
            if target.exists() and not previous:
                raise HubError("Der Zielordner enthält bereits Dateien. Bitte vor der WinGet-Installation sichern oder manuell zuordnen.")
            record = self.winget.install(entry, target, progress,
                                         lambda message: self._log(log, message), cancel_event)
            if previous:
                record["shortcuts"] = previous.get("shortcuts", [])
            records = dict(self.installed)
            records[entry["id"]] = record
            try:
                self._save(records)
            except HubError as exc:
                raise HubError(f"WinGet hat den Emulator installiert, aber die Zuordnung konnte nicht gespeichert werden. Bitte den Ordner über die Anleitung auswählen: {exc}") from None
            try:
                if any(shortcuts.values()):
                    created = create_shortcuts(entry, record["exe_path"], shortcuts)
                    record["shortcuts"] = sorted(set(record["shortcuts"] + created))
                    self._save(records)
            except Exception as exc:
                self._log(log, str(exc))
            return record
        if previous and not previous.get("managed"):
            raise HubError("Dieser Emulator wurde manuell zugeordnet. Bitte zuerst die Zuordnung entfernen; danach ist die automatische Installation möglich.")
        if target.exists() and not previous:
            raise HubError("Der Zielordner enthält bereits Dateien. Bitte den Ordner manuell zuordnen oder vor der Installation sichern.")
        if target.exists():
            assert_plain_tree(target)
        release = asset = None
        if cancel_event.is_set():
            raise Cancelled()
        progress(-1, "Offizielles Release ermitteln …")
        if method == "auto_github":
            release = prepared[2] if prepared else self.github.latest(entry["github_repo"])
            asset = prepared[3] if prepared else self.github.asset(entry, release)
            url, filename, version = asset["browser_download_url"], asset["name"], release["tag_name"]
        elif method == "auto_direct":
            if entry.get("direct_resolver") == "winuae":
                from .direct import resolve_winuae
                direct = resolve_winuae(self.policy, entry, cancel_event)
                url, filename, version = direct.url, direct.name, direct.version
                if (previous and previous["version"] not in ("", "unbekannt", "manuell")
                        and _version_newer(previous["version"], version)):
                    self.latest_versions.pop(entry["id"], None)
                    raise HubError("WinUAE: Die ermittelte Version ist älter als die installierte. Bitte manuell prüfen.")
            else:
                url = entry.get("direct_url", "")
                self.policy.validate(url)
                filename = Path(url.split("?")[0]).name or "download.zip"
                version = entry.get("direct_version", "unbekannt")
        else:
            raise HubError("Unbekannte Installationsmethode. Bitte den Katalog prüfen.")
        if Path(filename).name != filename or any(c in filename for c in ':\\/'):
            raise HubError("Ungültiger Name der Download-Datei.")
        self._log(log, f"{entry['emulator']}: offizieller Download {filename} ({version})")
        backup = self.emulator_dir / f"_backup_{entry['id']}_{uuid.uuid4().hex}"
        swapped = False
        saved = False
        work = Path(tempfile.mkdtemp(prefix=f"_install_{entry['id']}_", dir=self.emulator_dir))
        try:
            archive = work / filename
            expected = prepared[0].sha256 if prepared else self._checksum(entry, release, asset)
            actual = self._download(url, archive, progress, cancel_event, asset.get("size") if asset else None)
            if expected:
                if actual != expected:
                    raise HubError("Die SHA-256-Prüfsumme stimmt nicht überein. Die Datei wurde verworfen.")
                self._log(log, "SHA-256 erfolgreich geprüft.")
            else:
                self._log(log, "Die offizielle Quelle veröffentlicht für diese Datei keine SHA-256-Prüfsumme.")
            kind = entry.get("archive_type") or ("7z" if filename.lower().endswith(".7z") else "zip")
            if kind == "installer":
                # Ein interaktiver Installer benötigt anschließend eine sichere Ordnerzuordnung.
                verify_windows_executable(archive, require_x64=False)
                destination = self.data_dir / "downloads"
                destination.mkdir(exist_ok=True)
                installer_path = destination / f"{entry['id']}-{filename}"
                shutil.copy2(archive, installer_path)
                subprocess.Popen([str(installer_path)], shell=False)
                raise HubError("Der offizielle Installer wurde gestartet. Nach Abschluss bitte über die Anleitung den installierten Ordner auswählen.")
            progress(86, "Archiv sicher entpacken …")
            content = work / "content"
            if entry.get("direct_resolver") == "winuae":
                extract_archive(archive, content, kind, cancel_event,
                                progress=lambda fraction: progress(86 + int(8 * fraction), "WinUAE entpacken …"))
            else:
                extract_archive(archive, content, kind, cancel_event)
            executable = find_executable(content, entry)
            verify_windows_executable(executable)
            relative_exe = executable.relative_to(content)
            assert_plain_tree(content)
            if target.exists():
                # Bestehende Benutzerdaten übernehmen; konfigurierte Einstellungen behalten.
                merged = work / "merged"
                shutil.copytree(target, merged)
                shutil.copytree(content, merged, dirs_exist_ok=True)
                for existing in target.rglob("*"):
                    if existing.is_file() and existing.suffix.lower() in SETTINGS_EXTENSIONS:
                        output = merged / existing.relative_to(target)
                        output.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(existing, output)
                content = merged
            if cancel_event.is_set():
                raise Cancelled()
            progress(95, "Installation speichern …")
            if target.exists():
                target.rename(backup)
            content.rename(target)
            swapped = True
            record = {"path": str(target), "exe_path": str(target / relative_exe),
                      "version": version, "date": datetime.now(timezone.utc).isoformat(),
                      "managed": True, "method": method, "sha256": actual,
                      "shortcuts": previous.get("shortcuts", []) if previous else []}
            records = dict(self.installed)
            records[entry["id"]] = record
            self._save(records)
            saved = True
            try:
                if any(shortcuts.values()):
                    created = create_shortcuts(entry, Path(record["exe_path"]), shortcuts)
                    record["shortcuts"] = sorted(set(record["shortcuts"] + created))
                    self._save(records)
            except Exception as exc:
                self._log(log, str(exc))
            progress(100, f"{entry['emulator']} ist installiert.")
            self._log(log, f"Installation abgeschlossen: {target}")
            if entry.get("launcher", {}).get("install_methode") == "manuell":
                self._log(log, entry["launcher"]["note"])
            return record
        except Exception as exc:
            if swapped and not saved:
                remove_managed_tree(target, self.emulator_dir)
            if backup.exists() and not saved:
                backup.rename(target)
            self.logger.exception("Installation von %s fehlgeschlagen", entry["id"])
            if isinstance(exc, HubError):
                raise
            raise HubError(f"Installation fehlgeschlagen. Die bisherige Installation bleibt erhalten: {exc}") from None
        finally:
            if backup.exists() and saved:
                try:
                    remove_managed_tree(backup, self.emulator_dir)
                except (OSError, HubError) as exc:
                    self._log(log, f"Vorherige Installation als Sicherung erhalten: {backup} ({exc})")
            if work.exists():
                try:
                    remove_managed_tree(work, self.emulator_dir)
                except (OSError, HubError) as exc:
                    self._log(log, f"Temporärer Ordner konnte nicht entfernt werden: {exc}")

    def uninstall(self, entry, log_callback, cancel_event):
        with self._lock:
            record = self.installed.get(entry["id"])
            if not record:
                return
            if cancel_event.is_set():
                raise Cancelled()
            if record.get("method") == "winget":
                self.winget.uninstall(record, lambda message: self._log(log_callback, message), cancel_event)
                records = dict(self.installed)
                del records[entry["id"]]
                self._save(records)
                remove_shortcuts(entry, record.get("shortcuts", []))
                self.latest_versions.pop(entry["id"], None)
                self._log(log_callback, f"{entry['emulator']}: WinGet-Paket und Hub-Zuordnung entfernt.")
                return
            tombstone = None
            if record.get("managed"):
                target = Path(record["path"])
                expected = self.emulator_dir / entry["id"]
                if target != expected or target.resolve() != expected.absolute():
                    raise HubError("Der gespeicherte Installationspfad ist nicht sicher. Bitte die Dateien manuell entfernen.")
                if target.exists():
                    assert_plain_tree(target)
                    tombstone = self.emulator_dir / f"_remove_{entry['id']}_{uuid.uuid4().hex}"
                    target.rename(tombstone)
            try:
                records = dict(self.installed)
                del records[entry["id"]]
                self._save(records)
            except Exception:
                if tombstone:
                    tombstone.rename(expected)
                raise
            remove_shortcuts(entry, record.get("shortcuts", []))
            if tombstone:
                try:
                    remove_managed_tree(tombstone, self.emulator_dir)
                except OSError as exc:
                    self._log(log_callback, f"Zuordnung entfernt. Dateien bitte manuell löschen: {tombstone} ({exc})")
            self.latest_versions.pop(entry["id"], None)
            self._log(log_callback, f"{entry['emulator']}: " + ("deinstalliert." if record.get("managed") else "Zuordnung entfernt; persönliche Dateien bleiben erhalten."))

    def check_updates(self, progress_callback, log_callback, cancel_event):
        entries = [e for e in self.catalog.visible_items(self.settings.get("show_hidden", False))
                   if e["id"] in self.installed and e.get("entry_type") != "utility" and not e.get("deprecated")]
        releases = {}
        result = {}
        for index, entry in enumerate(entries):
            if cancel_event.is_set():
                raise Cancelled()
            progress_callback(int(index / max(1, len(entries)) * 100), f"Updates prüfen · {entry['emulator']}")
            repo = entry.get("github_repo")
            record = self.installed[entry["id"]]
            if entry.get("direct_resolver") == "winuae":
                from .direct import resolve_winuae
                try:
                    version = resolve_winuae(self.policy, entry, cancel_event).version
                    self.latest_versions[entry["id"]] = version
                    result[entry["id"]] = version
                    if record["version"] in ("unbekannt", "manuell", ""):
                        self._log(log_callback, f"{entry['emulator']}: aktuell {version}; installierte Version unbekannt, bitte manuell prüfen.")
                    else:
                        self._log(log_callback, f"{entry['emulator']}: installiert {record['version']}, aktuell {version}.")
                except Cancelled:
                    raise
                except HubError as exc:
                    self.latest_versions.pop(entry["id"], None)
                    self._log(log_callback, f"{entry['emulator']}: manuell prüfen. {exc}")
                continue
            if record.get("method") == "winget":
                version = entry.get("winget_version")
                if version:
                    self.latest_versions[entry["id"]] = version
                    result[entry["id"]] = version
                    self._log(log_callback, f"{entry['emulator']}: installiert {record['version']}, geprüfte WinGet-Katalogversion {version}. Neuere Paketversionen benötigen ein geprüftes Manifest im Katalog.")
                continue
            if not repo or record["version"] == "unbekannt":
                self._log(log_callback, f"{entry['emulator']}: Versionsvergleich nicht verfügbar; bitte die offizielle Seite prüfen.")
                continue
            try:
                if repo not in releases:
                    releases[repo] = self.github.latest(repo, force=True)
                version = releases[repo]["tag_name"]
                self.latest_versions[entry["id"]] = version
                result[entry["id"]] = version
                self._log(log_callback, f"{entry['emulator']}: installiert {record['version']}, aktuell {version}.")
            except HubError as exc:
                self._log(log_callback, f"{entry['emulator']}: Updateprüfung fehlgeschlagen: {exc}")
        progress_callback(100, "Updateprüfung abgeschlossen.")
        return result
