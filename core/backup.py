"""Gezielte ZIP-Sicherungen mit geprüfter Wiederherstellung und Rücknahme."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import zipfile

from .archives import MAX_EXPANDED, MAX_FILES, safe_member
from .errors import Cancelled, HubError
from .profiles import profile_paths, game_protection, assert_not_game_file

MANIFEST = "emulator-hub-backup.json"
CHUNK_SIZE = 1024 * 1024


def _cancel(event):
    if event is not None and event.is_set():
        raise Cancelled()


def _plain_path(path):
    """Reject every existing parent link, including Windows junctions."""
    for item in [path, *path.parents]:
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if item.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise HubError("Eine Sicherung oder Wiederherstellung über Verknüpfungen ist nicht möglich. Bitte den tatsächlichen Speicherordner auswählen.")


def _files(profiles, event, protection):
    files, total = [], 0
    for profile in profiles:
        _cancel(event)
        path = profile["path"]
        _plain_path(path)
        if not path.exists():
            continue
        if profile["type"] == "file":
            if not path.is_file():
                raise HubError(f"Der Sicherungspfad ist keine Datei: {path}")
            candidates = [path]
        else:
            if not path.is_dir():
                raise HubError(f"Der Sicherungspfad ist kein Ordner: {path}")
            candidates = []
            # os.walk must not follow symbolic links/reparse points.
            def unreadable(error):
                raise HubError(f"Der Sicherungsordner konnte nicht vollständig gelesen werden: {error.filename}. Bitte Zugriffsrechte prüfen und erneut sichern.")

            for directory, folders, names in os.walk(path, followlinks=False, onerror=unreadable):
                _cancel(event)
                for name in folders + names:
                    _plain_path(Path(directory) / name)
                candidates.extend(Path(directory) / name for name in names)
        for source in sorted(candidates):
            _cancel(event)
            _plain_path(source)
            assert_not_game_file(source, protection)
            if not source.is_file():
                raise HubError(f"Dieser Sicherungspfad enthält eine besondere, nicht unterstützte Datei: {source}")
            size = source.stat().st_size
            total += size
            if total > MAX_EXPANDED or len(files) >= MAX_FILES:
                raise HubError("Die Sicherung überschreitet 4 GB oder 50.000 Dateien. Bitte kleinere Spielstand- oder Einstellungsordner auswählen.")
            relative = source.name if profile["type"] == "file" else source.relative_to(path).as_posix()
            member = f"profiles/{profile['key']}/{relative}"
            safe_member(member, Path(tempfile.gettempdir()) / "hub-backup-check")
            files.append((profile, source, member, size))
    return files


class BackupManager:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)

    def backup(self, entry, record, destination, progress=None, log=None, cancel_event=None, settings=None):
        """Create one atomic ZIP in a chosen directory, including missing profiles."""
        profiles = profile_paths(entry, record, self.data_dir, settings)
        if not profiles:
            raise HubError("Für diesen Emulator sind noch keine gezielten Sicherungspfade konfiguriert. Bitte seine Spielstand-/Einstellungsordner zuordnen.")
        destination = Path(destination)
        _plain_path(destination)
        for profile in profiles:
            if destination.resolve() == profile["path"].resolve() or destination.resolve().is_relative_to(profile["path"].resolve()):
                raise HubError("Der ZIP-Zielordner darf nicht im zu sichernden Spielstand- oder Einstellungsordner liegen.")
        destination.mkdir(parents=True, exist_ok=True)
        files = _files(profiles, cancel_event, game_protection(self.data_dir, settings))
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        archive = destination / f"{entry['id']}-{stamp}.zip"
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination, prefix="hub-backup-", suffix=".tmp", delete=False) as handle:
                temp_path = Path(handle.name)
            manifest = {
                "schema_version": 1, "emulator_id": entry["id"], "created_at": datetime.now(timezone.utc).isoformat(),
                "profiles": [{"key": p["key"], "label": p["label"], "type": p["type"],
                              "present": p["path"].exists()} for p in profiles], "files": [],
            }
            total = sum(item[3] for item in files) or 1
            done = 0
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                for profile, source, member, size in files:
                    _cancel(cancel_event)
                    digest = hashlib.sha256()
                    copied = 0
                    _plain_path(source)
                    with source.open("rb") as src, zf.open(member, "w") as dst:
                        while chunk := src.read(CHUNK_SIZE):
                            _cancel(cancel_event)
                            copied += len(chunk)
                            if copied > size:
                                raise HubError("Eine Datei wurde während der Sicherung geändert. Bitte den Emulator schließen und die Sicherung erneut starten.")
                            digest.update(chunk)
                            dst.write(chunk)
                            done += len(chunk)
                            if progress:
                                progress(min(99, round(done * 100 / total)), f"Sichern: {source.name}")
                    if copied != size:
                        raise HubError("Eine Datei wurde während der Sicherung geändert. Bitte erneut sichern.")
                    manifest["files"].append({"path": member, "size": size, "sha256": digest.hexdigest()})
                zf.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False, indent=2))
            _cancel(cancel_event)
            os.replace(temp_path, archive)
            if log:
                log(f"{len(files)} Dateien gesichert: {archive}")
                for profile in profiles:
                    if not profile["path"].exists():
                        log(f"Noch nicht vorhanden: {profile['label']} ({profile['path']})")
            if progress:
                progress(100, "ZIP-Sicherung abgeschlossen")
            return archive
        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            raise HubError(f"Die Sicherung konnte nicht erstellt werden: {exc}") from None
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def _stage(self, entry, profiles, archive, stage, progress, cancel_event, protection):
        """Validate all names, mappings, hashes and limits before touching profiles."""
        approved = {p["key"]: p for p in profiles}
        try:
            with zipfile.ZipFile(archive) as zf:
                infos = zf.infolist()
                if len(infos) > MAX_FILES + 1 or sum(i.file_size for i in infos) > MAX_EXPANDED:
                    raise HubError("Das ZIP überschreitet die sichere Größe oder Dateianzahl.")
                seen = set()
                info_by_name = {}
                for info in infos:
                    _cancel(cancel_event)
                    safe_member(info.filename, stage)
                    folded = info.filename.replace("\\", "/").casefold()
                    if (folded in seen or "\\" in info.filename or info.is_dir() or info.flag_bits & 1
                            or stat.S_ISLNK(info.external_attr >> 16)):
                        raise HubError("Das ZIP enthält doppelte, verschlüsselte oder nicht unterstützte Pfade/Verknüpfungen.")
                    seen.add(folded)
                    info_by_name[info.filename] = info
                manifest_info = info_by_name.get(MANIFEST)
                if manifest_info is None or manifest_info.file_size > 16 * 1024 * 1024:
                    raise HubError("Dieses ZIP ist keine gültige Emulator-Hub-Sicherung.")
                manifest = json.loads(zf.read(MANIFEST).decode("utf-8"))
                if not isinstance(manifest, dict) or manifest.get("schema_version") != 1 or manifest.get("emulator_id") != entry["id"]:
                    raise HubError("Die Sicherung gehört zu einem anderen Emulator oder hat ein unbekanntes Format.")
                saved_profiles = manifest.get("profiles")
                saved_files = manifest.get("files")
                if not isinstance(saved_profiles, list) or not isinstance(saved_files, list):
                    raise HubError("Das Sicherungsmanifest ist beschädigt.")
                keys = set()
                for saved in saved_profiles:
                    if (not isinstance(saved, dict) or saved.get("key") not in approved
                            or saved.get("key") in keys or saved.get("type") != approved[saved["key"]]["type"]):
                        raise HubError("Die Sicherung enthält nicht zugeordnete Profilpfade. Bitte die ursprüngliche Pfadzuordnung wiederherstellen.")
                    keys.add(saved["key"])
                targets, members = [], set()
                for index, item in enumerate(saved_files):
                    _cancel(cancel_event)
                    if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                        raise HubError("Das Sicherungsmanifest enthält einen ungültigen Dateieintrag.")
                    member = item["path"]
                    parts = member.split("/")
                    if len(parts) < 3 or parts[0] != "profiles" or parts[1] not in keys or member in members:
                        raise HubError("Das ZIP enthält einen nicht erlaubten Zielpfad.")
                    profile = approved[parts[1]]
                    if profile["type"] == "file":
                        if len(parts) != 3 or parts[2] != profile["path"].name:
                            raise HubError("Die Dateisicherung passt nicht zum zugeordneten Profilpfad.")
                        target = profile["path"]
                    else:
                        target = safe_member("/".join(parts[2:]), profile["path"])
                    _plain_path(target)
                    assert_not_game_file(target, protection)
                    if target.exists() and not target.is_file():
                        raise HubError(f"Der Wiederherstellungspfad ist keine Datei: {target}")
                    info = info_by_name.get(member)
                    if (info is None or type(item.get("size")) is not int or item["size"] != info.file_size
                            or not isinstance(item.get("sha256"), str) or len(item["sha256"]) != 64):
                        raise HubError("Das Sicherungsmanifest stimmt nicht mit den ZIP-Dateien überein.")
                    staged = safe_member(member, stage)
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    copied = 0
                    with zf.open(info) as src, staged.open("wb") as dst:
                        while chunk := src.read(CHUNK_SIZE):
                            _cancel(cancel_event)
                            copied += len(chunk)
                            if copied > info.file_size:
                                raise HubError("Das ZIP enthält eine Datei mit ungültiger Größe.")
                            digest.update(chunk)
                            dst.write(chunk)
                    if copied != item["size"] or digest.hexdigest() != item["sha256"]:
                        raise HubError("Die Sicherung ist beschädigt: Eine Dateiprüfsumme stimmt nicht.")
                    members.add(member)
                    targets.append((staged, target))
                    if progress:
                        progress(round((index + 1) * 25 / max(1, len(saved_files))), "Sicherung vollständig prüfen")
                if set(info_by_name) != members | {MANIFEST}:
                    raise HubError("Das ZIP enthält Dateien, die nicht im Sicherungsmanifest stehen.")
                return targets
        except (OSError, UnicodeError, ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as exc:
            raise HubError(f"Die Sicherung konnte nicht geprüft werden: {exc}") from None

    def restore(self, entry, record, archive, progress=None, log=None, cancel_event=None, settings=None):
        """Restore approved files after a safety backup; preserve unrelated files."""
        profiles = profile_paths(entry, record, self.data_dir, settings)
        if not profiles:
            raise HubError("Bitte zuerst die Spielstand-/Einstellungsordner für diesen Emulator zuordnen.")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="hub-restore-", dir=self.data_dir) as temporary:
            stage = Path(temporary)
            targets = self._stage(entry, profiles, Path(archive), stage / "checked", progress, cancel_event,
                                  game_protection(self.data_dir, settings))
            _cancel(cancel_event)
            safety_progress = (lambda value, text: progress(25 + round(value * .35), "Aktuellen Stand sichern: " + text)) if progress else None
            safety = self.backup(entry, record, self.data_dir / "backups" / entry["id"],
                                 safety_progress, log, cancel_event, settings)
            if log:
                log(f"Sicherheitsbackup vor Wiederherstellung: {safety}")
            changed, created_dirs = [], []
            try:
                for index, (source, target) in enumerate(targets):
                    _cancel(cancel_event)
                    _plain_path(target)
                    old_copy = None
                    if target.exists():
                        old_copy = stage / "rollback" / str(index)
                        old_copy.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, old_copy)
                    absent = []
                    parent = target.parent
                    while not parent.exists():
                        absent.append(parent)
                        parent = parent.parent
                    target.parent.mkdir(parents=True, exist_ok=True)
                    created_dirs.extend(reversed(absent))
                    # An atomic file replacement avoids partially overwritten saves.
                    handle, filename = tempfile.mkstemp(prefix="hub-restore-", suffix=".tmp", dir=target.parent)
                    os.close(handle)
                    replacement = Path(filename)
                    try:
                        shutil.copy2(source, replacement)
                        _cancel(cancel_event)
                        _plain_path(target)
                        os.replace(replacement, target)
                        changed.append((target, old_copy))
                    finally:
                        replacement.unlink(missing_ok=True)
                    if progress:
                        progress(60 + round((index + 1) * 40 / max(1, len(targets))), f"Wiederherstellen: {target.name}")
            except Exception as exc:
                rollback_errors = []
                for target, old_copy in reversed(changed):
                    try:
                        _plain_path(target)
                        if old_copy is None:
                            target.unlink(missing_ok=True)
                        else:
                            shutil.copy2(old_copy, target)
                    except (OSError, HubError) as rollback_exc:
                        rollback_errors.append(str(rollback_exc))
                for directory in reversed(created_dirs):
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
                reason = "Bereits ersetzte Dateien wurden zurückgesetzt." if not rollback_errors else "Die automatische Rücknahme war nicht vollständig möglich."
                raise HubError(f"Wiederherstellung abgebrochen: {exc}\n{reason}\nDer vorherige Stand liegt in: {safety}") from None
            if progress:
                progress(100, "Wiederherstellung abgeschlossen")
            if log:
                log(f"{len(targets)} Dateien wiederhergestellt. Andere Dateien bleiben erhalten.")
            return {"safety_backup": safety, "count": len(targets)}
