"""Opt-in WinGet support with pinned manifests and checked portable downloads.

No catalog entry enables this automatically. The small accepted manifest subset
deliberately falls back to the manual guide for installers requiring elevation,
dependencies, custom switches, or a download outside an official GitHub release.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import requests
import yaml

from .archives import assert_plain_tree, safe_member
from .errors import Cancelled, HubError


SOURCE_URL = "https://cdn.winget.microsoft.com/cache"
SOURCE_TYPE = "Microsoft.PreIndexed.Package"
SOURCE_ID = "Microsoft.Winget.Source_8wekyb3d8bbwe"
MAX_DOWNLOAD = 2 * 1024 ** 3
MAX_MANIFEST = 1024 * 1024
MAX_OUTPUT = 2 * 1024 * 1024
MANIFEST_URL = re.compile(
    r"https://raw\.githubusercontent\.com/microsoft/winget-pkgs/[a-fA-F0-9]{40}/"
    r"manifests/[A-Za-z0-9_./-]+\.ya?ml"
)
ASSET_URL = re.compile(
    r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/releases/download/[^/?#]+/[^/?#]+"
)
ROOT_FIELDS = {
    "PackageIdentifier", "PackageVersion", "ManifestType", "ManifestVersion", "Installers",
    "InstallerType", "NestedInstallerType", "Scope", "MinimumOSVersion", "ReleaseDate",
    "InstallerLocale", "UpgradeBehavior", "Dependencies", "ElevationRequirement",
    "InstallerSwitches", "NestedInstallerFiles", "InstallerSuccessCodes",
}
INSTALLER_FIELDS = {
    "Architecture", "InstallerUrl", "InstallerSha256", "InstallerType", "NestedInstallerType",
    "Scope", "InstallerLocale", "MinimumOSVersion", "Dependencies", "ElevationRequirement",
    "InstallerSwitches", "NestedInstallerFiles", "UpgradeBehavior", "InstallerSuccessCodes",
}


class WingetClient:
    def __init__(self, policy):
        self.policy = policy

    @staticmethod
    def _identity(identifier, version=None):
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9]+(?:\.[A-Za-z0-9_-]+)+", identifier):
            raise HubError("Die WinGet-Paket-ID ist nicht sicher hinterlegt. Bitte die Anleitung verwenden.")
        if version is not None and (not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,79}", version)):
            raise HubError("WinGet benötigt eine explizit festgelegte Paketversion.")

    @staticmethod
    def _executable():
        if os.name != "nt":
            raise HubError("WinGet ist nur unter Windows verfügbar. Bitte die manuelle Anleitung verwenden.")
        executable = shutil.which("winget")
        if not executable:
            raise HubError("WinGet wurde nicht gefunden. Bitte die manuelle Anleitung verwenden.")
        return executable

    @staticmethod
    def _check_cancel(cancel_event):
        if cancel_event.is_set():
            raise Cancelled()

    def _run(self, command, log, cancel_event):
        """Poll a file-backed child; an active package operation is never killed."""
        self._check_cancel(cancel_event)
        collected = bytearray()
        pending = ""
        cancel_logged = False
        try:
            with tempfile.TemporaryDirectory(prefix="EmulatorHub-winget-") as directory:
                output = Path(directory) / "output.log"
                with output.open("wb") as writer:
                    process = subprocess.Popen(
                        command, stdin=subprocess.DEVNULL, stdout=writer,
                        stderr=subprocess.STDOUT, shell=False,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    with output.open("rb") as reader:
                        finished = False
                        while not finished:
                            try:
                                process.communicate(timeout=1)
                                finished = True
                            except subprocess.TimeoutExpired:
                                pass
                            raw = reader.read(MAX_OUTPUT)
                            if len(collected) < MAX_OUTPUT:
                                collected.extend(raw[:MAX_OUTPUT - len(collected)])
                            pending += raw.decode("utf-8", errors="replace")
                            lines = pending.split("\n")
                            pending = lines.pop()
                            for line in lines:
                                if line.strip():
                                    log(line.strip()[:2000])
                            # Bound an unterminated line without changing captured JSON.
                            if len(pending) > 4000:
                                log(pending[:2000])
                                pending = pending[-2000:]
                            if cancel_event.is_set() and not cancel_logged:
                                log("Abbruch angefordert. Der laufende WinGet-Schritt wird sicher beendet; der Prozess wird nicht erzwungen beendet.")
                                cancel_logged = True
                        if pending.strip():
                            log(pending.strip()[:2000])
                if process.returncode:
                    raise HubError(f"WinGet konnte den Vorgang nicht abschließen (Code {process.returncode}). Bitte das Protokoll und die manuelle Anleitung prüfen.")
        except HubError:
            raise
        except (OSError, subprocess.SubprocessError) as exc:
            raise HubError(f"WinGet konnte nicht ausgeführt werden: {exc}") from None
        return collected.decode("utf-8-sig", errors="replace")

    def _verify_source(self, executable, log, cancel_event):
        self.policy.validate(SOURCE_URL)
        raw = self._run([executable, "source", "export", "winget", "--disable-interactivity"], log, cancel_event)
        try:
            source = json.loads(raw)
        except ValueError:
            raise HubError("Die WinGet-Quelle konnte nicht sicher geprüft werden. Bitte die Anleitung verwenden.") from None
        if not isinstance(source, dict) or any(source.get(key) != value for key, value in {
            "Name": "winget", "Arg": SOURCE_URL, "Type": SOURCE_TYPE, "Identifier": SOURCE_ID,
        }.items()):
            raise HubError("Die lokale WinGet-Quelle stimmt nicht mit der offiziellen Microsoft-Quelle überein.")

    @staticmethod
    def _yaml_shape(node, depth=0):
        if depth > 12:
            raise HubError("Das WinGet-Manifest ist ungewöhnlich verschachtelt.")
        if isinstance(node, yaml.nodes.MappingNode):
            keys = set()
            for key, value in node.value:
                if not isinstance(key, yaml.nodes.ScalarNode) or key.tag != "tag:yaml.org,2002:str" or key.value in keys:
                    raise HubError("Das WinGet-Manifest enthält ungültige oder doppelte Felder.")
                keys.add(key.value)
                WingetClient._yaml_shape(value, depth + 1)
        elif isinstance(node, yaml.nodes.SequenceNode):
            for item in node.value:
                WingetClient._yaml_shape(item, depth + 1)

    @staticmethod
    def _no_dependencies(data):
        if isinstance(data, dict):
            for key, value in data.items():
                if "dependenc" in str(key).casefold() and value not in (None, {}, [], ""):
                    raise HubError("WinGet-Pakete mit Abhängigkeiten sind nicht automatisch freigegeben.")
                WingetClient._no_dependencies(value)
        elif isinstance(data, list):
            for value in data:
                WingetClient._no_dependencies(value)

    def _manifest(self, entry, cancel_event):
        identifier, version = entry.get("winget_id"), entry.get("winget_version")
        self._identity(identifier, version)
        if not version:
            raise HubError("Für WinGet fehlt die festgelegte Version im Katalog.")
        url = entry.get("winget_manifest_url", "")
        if not isinstance(url, str) or not MANIFEST_URL.fullmatch(url):
            raise HubError("WinGet benötigt ein offizielles Microsoft-Manifest mit fest angehefteter Git-Revision (40 Zeichen).")
        self.policy.validate(url)
        raw = bytearray()
        try:
            with self.policy.get(url, stream=True) as response:
                for chunk in response.iter_content(65536):
                    self._check_cancel(cancel_event)
                    raw.extend(chunk)
                    if len(raw) > MAX_MANIFEST:
                        raise HubError("Das WinGet-Manifest ist ungewöhnlich groß.")
            text = raw.decode("utf-8-sig")
            # Reject aliases and duplicate keys before safe_load can hide ambiguity.
            for token in yaml.scan(text):
                if isinstance(token, (yaml.tokens.AliasToken, yaml.tokens.AnchorToken)):
                    raise HubError("WinGet-Manifeste mit YAML-Verweisen werden nicht automatisch verwendet.")
            self._yaml_shape(yaml.compose(text))
            data = yaml.safe_load(text)
        except HubError:
            raise
        except (UnicodeError, yaml.YAMLError, requests.exceptions.RequestException) as exc:
            raise HubError(f"Das WinGet-Manifest konnte nicht sicher gelesen werden: {exc}") from None
        if (not isinstance(data, dict) or set(data) - ROOT_FIELDS or data.get("ManifestType") != "installer"
                or data.get("PackageIdentifier") != identifier or data.get("PackageVersion") != version):
            raise HubError("Das WinGet-Manifest passt nicht zum festgelegten Paket oder enthält nicht freigegebene Optionen.")
        self._no_dependencies(data)
        installers = data.get("Installers")
        if not isinstance(installers, list) or not installers:
            raise HubError("Das WinGet-Manifest enthält keinen verwendbaren Installer.")
        matches = []
        for installer in installers:
            if not isinstance(installer, dict) or set(installer) - INSTALLER_FIELDS:
                raise HubError("Das WinGet-Manifest enthält nicht freigegebene Installer-Optionen.")
            merged = {**data, **installer}
            kind = merged.get("InstallerType")
            if (merged.get("Scope") != "user" or kind not in {"portable", "zip"}
                    or merged.get("ElevationRequirement") not in (None, "elevationProhibited")
                    or merged.get("InstallerSwitches") not in (None, {})
                    or merged.get("InstallerSuccessCodes") not in (None, [])
                    or merged.get("UpgradeBehavior") not in (None, "install")):
                raise HubError("Nur portable WinGet-Pakete ohne Admin-Rechte, zusätzliche Schalter und Deinstallationsschritte sind freigegeben.")
            if kind == "zip":
                if merged.get("NestedInstallerType") != "portable":
                    raise HubError("WinGet-ZIP-Dateien dürfen nur einen portablen Emulator enthalten.")
                nested = merged.get("NestedInstallerFiles")
                if not isinstance(nested, list) or len(nested) != 1 or not isinstance(nested[0], dict):
                    raise HubError("Die portable Startdatei im WinGet-ZIP ist nicht eindeutig hinterlegt.")
                file = nested[0]
                if set(file) - {"RelativeFilePath", "PortableCommandAlias"}:
                    raise HubError("Die WinGet-ZIP-Konfiguration ist nicht freigegeben.")
                filename = file.get("RelativeFilePath")
                if not isinstance(filename, str) or not filename.lower().endswith(".exe"):
                    raise HubError("Die WinGet-ZIP-Startdatei ist ungültig.")
                safe_member(filename, Path.cwd())
                alias = file.get("PortableCommandAlias")
                if alias is not None and (not isinstance(alias, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", alias)):
                    raise HubError("Der WinGet-Befehlsname ist nicht sicher hinterlegt.")
            elif merged.get("NestedInstallerType") or merged.get("NestedInstallerFiles"):
                raise HubError("Die portable WinGet-Konfiguration enthält unerwartete verschachtelte Installer.")
            asset_url, digest = installer.get("InstallerUrl"), installer.get("InstallerSha256")
            if not isinstance(asset_url, str) or not ASSET_URL.fullmatch(asset_url):
                raise HubError("WinGet-Downloads sind nur aus festgelegten offiziellen GitHub-Release-Dateien freigegeben.")
            self.policy.validate(asset_url)
            suffix = ".zip" if kind == "zip" else ".exe"
            if not asset_url.casefold().endswith(suffix):
                raise HubError("Die WinGet-Datei passt nicht zum freigegebenen portablen Installerformat.")
            if asset_url.split("/releases/download/", 1)[1].split("/", 1)[0].casefold() in {"latest", "nightly", "continuous", "main", "master", "canary"}:
                raise HubError("WinGet benötigt einen festen Release-Tag statt einer beweglichen Entwicklungsversion.")
            if not isinstance(digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest):
                raise HubError("Für den WinGet-Download fehlt eine gültige SHA-256-Prüfsumme.")
            if installer.get("Architecture") == "x64":
                matches.append({**merged, "InstallerSha256": digest.lower()})
        if len(matches) != 1:
            raise HubError("Der Windows-x64-Installer im WinGet-Manifest ist nicht eindeutig. Bitte die Anleitung verwenden.")
        return matches[0]

    def _preflight(self, installer, progress, cancel_event):
        received = 0
        digest = hashlib.sha256()
        try:
            with self.policy.get(installer["InstallerUrl"], stream=True) as response:
                total = int(response.headers.get("Content-Length", 0))
                if total < 0 or total > MAX_DOWNLOAD:
                    raise HubError("Der WinGet-Download überschreitet die sichere Größe.")
                for chunk in response.iter_content(256 * 1024):
                    self._check_cancel(cancel_event)
                    if not chunk:
                        continue
                    received += len(chunk)
                    if received > MAX_DOWNLOAD:
                        raise HubError("Der WinGet-Download ist ungewöhnlich groß.")
                    digest.update(chunk)
                    progress(min(60, int(received / total * 60)) if total else -1, "WinGet-Quelle und SHA-256 prüfen …")
                if not received or (total and received != total):
                    raise HubError("Die WinGet-Downloadprüfung ist unvollständig.")
        except HubError:
            raise
        except (ValueError, requests.exceptions.RequestException) as exc:
            raise HubError(f"Die WinGet-Downloadquelle konnte nicht geprüft werden: {exc}") from None
        if digest.hexdigest() != installer["InstallerSha256"]:
            raise HubError("Die WinGet-SHA-256-Prüfsumme stimmt nicht überein. Installation gestoppt.")

    @staticmethod
    def _safe_target(target):
        target = Path(target).absolute()
        for ancestor in (target, *target.parents):
            if ancestor.is_symlink():
                raise HubError("Der WinGet-Zielordner darf keine Verknüpfung enthalten.")
            if ancestor.exists():
                info = ancestor.lstat()
                if ancestor.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise HubError("Der WinGet-Zielordner darf keine Verknüpfung enthalten.")
        if target.exists():
            if not target.is_dir():
                raise HubError("Der WinGet-Zielpfad ist kein Ordner.")
            assert_plain_tree(target)
        return target

    def install(self, entry, target, progress, log, cancel_event):
        self._check_cancel(cancel_event)
        target = self._safe_target(target)
        installer = self._manifest(entry, cancel_event)
        executable = self._executable()
        self._verify_source(executable, log, cancel_event)
        self._check_cancel(cancel_event)
        self._preflight(installer, progress, cancel_event)
        self._check_cancel(cancel_event)
        log("Offizielle WinGet-Quelle, feste Paketversion und SHA-256 erfolgreich geprüft.")
        progress(65, "WinGet installiert für den aktuellen Benutzer …")
        self._run([
            executable, "install", "--id", entry["winget_id"], "--exact",
            "--version", entry["winget_version"], "--source", "winget", "--architecture", "x64",
            "--scope", "user", "--installer-type", installer["InstallerType"], "--location", str(target),
            "--accept-source-agreements", "--accept-package-agreements", "--disable-interactivity",
        ], log, cancel_event)
        # Late imports avoid a circular dependency with the shared HubService.
        from .installer import find_executable, verify_windows_executable
        try:
            assert_plain_tree(target)
            start = find_executable(target, entry)
            verify_windows_executable(start)
        except (HubError, OSError):
            raise HubError("WinGet hat den Vorgang beendet, aber die Startdatei liegt nicht im gewählten Ordner. Bitte über die Anleitung den tatsächlich installierten Ordner manuell zuordnen.") from None
        progress(100, "WinGet-Installation abgeschlossen.")
        return {
            "path": str(target), "exe_path": str(start), "version": entry["winget_version"],
            "date": datetime.now(timezone.utc).isoformat(), "method": "winget", "managed": False,
            "winget_id": entry["winget_id"], "shortcuts": [], "sha256": installer["InstallerSha256"],
        }

    def uninstall(self, record, log, cancel_event):
        self._check_cancel(cancel_event)
        identifier, version = record.get("winget_id"), record.get("version")
        self._identity(identifier, version)
        if record.get("method") != "winget" or not version:
            raise HubError("Diese Installation enthält keine sichere WinGet-Paketzuordnung.")
        executable = self._executable()
        self._verify_source(executable, log, cancel_event)
        self._check_cancel(cancel_event)
        self._run([
            executable, "uninstall", "--id", identifier, "--exact", "--version", version,
            "--source", "winget", "--scope", "user", "--accept-source-agreements", "--disable-interactivity",
        ], log, cancel_event)
        log("WinGet-Paket für den aktuellen Benutzer entfernt.")
