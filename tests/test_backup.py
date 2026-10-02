import hashlib
import json
import os
from pathlib import Path
import stat
import threading
import unittest
from unittest.mock import patch
import zipfile

from core.backup import BackupManager, MANIFEST
from core.errors import Cancelled, HubError
from tests.helpers import TemporaryDirectory


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.emulator = self.root / "emulator"
        self.emulator.mkdir()
        self.saves = self.emulator / "saves"
        self.saves.mkdir()
        self.record = {"path": str(self.emulator), "exe_path": str(self.emulator / "emulator.exe")}
        self.entry = {"id": "test-emulator", "backup_paths": [
            {"label": "Spielstände", "root": "emulator", "directory": "saves", "type": "directory"},
            {"label": "Einstellungen", "root": "emulator", "directory": "config.ini", "type": "file"},
        ]}
        self.manager = BackupManager(self.root / "data")

    def backup(self):
        return self.manager.backup(self.entry, self.record, self.root / "chosen")

    def rewrite_zip(self, archive, *, manifest_edit=None, contents_edit=None, extra=None):
        with zipfile.ZipFile(archive) as zf:
            contents = {info.filename: zf.read(info) for info in zf.infolist()}
        manifest = json.loads(contents[MANIFEST])
        if manifest_edit:
            manifest_edit(manifest)
        contents[MANIFEST] = json.dumps(manifest).encode()
        if contents_edit:
            contents_edit(contents)
        if extra:
            contents.update(extra)
        with zipfile.ZipFile(archive, "w") as zf:
            for name, body in contents.items():
                zf.writestr(name, body)

    def test_backup_restore_snapshots_current_before_overwrite_and_preserves_unrelated(self):
        save = self.saves / "my-game.sav"
        save.write_bytes(b"original")
        (self.emulator / "config.ini").write_text("original", encoding="utf-8")
        (self.emulator / "my-game.nes").write_bytes(b"game-file")
        archive = self.backup()
        save.write_bytes(b"current")
        unrelated = self.saves / "other-game.sav"
        unrelated.write_bytes(b"untouched")
        observed = []
        original_replace = os.replace
        def record_replace(source, target):
            if Path(target) == save:
                observed.append(list((self.root / "data/backups/test-emulator").glob("*.zip")))
            return original_replace(source, target)
        with patch("core.backup.os.replace", side_effect=record_replace):
            result = self.manager.restore(self.entry, self.record, archive)
        self.assertTrue(observed[0])
        self.assertEqual(result["count"], 2)
        self.assertEqual(save.read_bytes(), b"original")
        self.assertEqual(unrelated.read_bytes(), b"untouched")
        self.assertEqual((self.emulator / "my-game.nes").read_bytes(), b"game-file")
        with zipfile.ZipFile(result["safety_backup"]) as zf:
            self.assertIn(b"current", [zf.read(i) for i in zf.namelist() if i != MANIFEST])
        with zipfile.ZipFile(archive) as zf:
            self.assertFalse(any("my-game.nes" in name for name in zf.namelist()))

    def test_malicious_extra_zip_paths_never_write_outside_profile(self):
        for name in ("../escape.txt", "profiles/../../escape.txt", "C:/escape.txt", "profiles/unknown-key/escape.txt", "not-in-manifest.txt"):
            archive = self.backup()
            self.rewrite_zip(archive, extra={name: b"evil"})
            with self.subTest(name=name), self.assertRaises(HubError):
                self.manager.restore(self.entry, self.record, archive)
            self.assertFalse((self.root / "escape.txt").exists())

    def test_wrong_emulator_and_unapproved_key_rejected(self):
        for mutate in (lambda m: m.update(emulator_id="other"), lambda m: m["profiles"][0].update(key="outside")):
            archive = self.backup()
            self.rewrite_zip(archive, manifest_edit=mutate)
            with self.assertRaises(HubError):
                self.manager.restore(self.entry, self.record, archive)

    def test_hash_mismatch_prevents_safety_backup_and_overwrite(self):
        save = self.saves / "game.sav"
        save.write_bytes(b"saved")
        archive = self.backup()
        save.write_bytes(b"current")
        def tamper(contents):
            name = next(name for name in contents if name != MANIFEST)
            contents[name] = b"EVIL!"
        self.rewrite_zip(archive, contents_edit=tamper)
        with self.assertRaisesRegex(HubError, "prüfsumme"):
            self.manager.restore(self.entry, self.record, archive)
        self.assertEqual(save.read_bytes(), b"current")
        self.assertFalse((self.root / "data/backups").exists())

    def test_restore_failure_rolls_back_files_and_new_paths(self):
        (self.saves / "a.sav").write_bytes(b"archive-a")
        (self.saves / "b.sav").write_bytes(b"archive-b")
        archive = self.backup()
        (self.saves / "a.sav").write_bytes(b"current-a")
        (self.saves / "b.sav").write_bytes(b"current-b")
        original_replace = os.replace
        def fail_second(source, target):
            if Path(target) == self.saves / "b.sav":
                raise PermissionError("Datei gesperrt")
            return original_replace(source, target)
        with patch("core.backup.os.replace", side_effect=fail_second):
            with self.assertRaisesRegex(HubError, "zurückgesetzt"):
                self.manager.restore(self.entry, self.record, archive)
        self.assertEqual((self.saves / "a.sav").read_bytes(), b"current-a")
        self.assertEqual((self.saves / "b.sav").read_bytes(), b"current-b")
        self.assertTrue(list((self.root / "data/backups/test-emulator").glob("*.zip")))

    def test_snapshot_failure_prevents_any_writes(self):
        save = self.saves / "game.sav"
        save.write_bytes(b"saved")
        archive = self.backup()
        save.write_bytes(b"current")
        with patch.object(self.manager, "backup", side_effect=HubError("Kein Speicherplatz")):
            with self.assertRaisesRegex(HubError, "Speicherplatz"):
                self.manager.restore(self.entry, self.record, archive)
        self.assertEqual(save.read_bytes(), b"current")

    def test_link_in_zip_is_rejected(self):
        archive = self.backup()
        with zipfile.ZipFile(archive, "a") as zf:
            link = zipfile.ZipInfo("profiles/unsafe/link")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(link, "outside")
        with self.assertRaises(HubError):
            self.manager.restore(self.entry, self.record, archive)

    def test_target_junction_is_rejected_before_read_or_write(self):
        external = self.root / "external"
        external.mkdir()
        link = self.saves / "linked"
        if os.name == "nt":
            import subprocess
            completed = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(external)], capture_output=True)
            if completed.returncode:
                self.skipTest("Junction konnte nicht angelegt werden")
            self.addCleanup(lambda: link.rmdir() if link.exists() else None)
        else:
            link.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(HubError, "Verknüpfungen"):
            self.backup()

    def test_missing_profiles_are_valid_and_empty_restore_still_takes_snapshot(self):
        archive = self.backup()
        result = self.manager.restore(self.entry, self.record, archive)
        self.assertEqual(result["count"], 0)
        self.assertTrue(result["safety_backup"].is_file())

    def test_cancellation_leaves_no_partial_archive(self):
        (self.saves / "game.sav").write_bytes(b"save")
        event = threading.Event()
        event.set()
        with self.assertRaises(Cancelled):
            self.manager.backup(self.entry, self.record, self.root / "chosen", cancel_event=event)
        self.assertFalse(list((self.root / "chosen").glob("*.zip")))
        self.assertFalse(list((self.root / "chosen").glob("*.tmp")))

    def test_zip_destination_cannot_be_inside_source(self):
        with self.assertRaises(HubError):
            self.manager.backup(self.entry, self.record, self.saves / "backups")

    def test_unreadable_subfolder_does_not_create_incomplete_successful_zip(self):
        def unreadable_walk(path, **kwargs):
            kwargs["onerror"](PermissionError(13, "Zugriff verweigert", str(self.saves / "locked")))
            return iter(())
        with patch("core.backup.os.walk", side_effect=unreadable_walk), self.assertRaisesRegex(HubError, "vollständig gelesen"):
            self.backup()
        self.assertFalse(list((self.root / "chosen").glob("*.zip")))

    def test_game_file_inside_profile_is_not_copied_into_backup(self):
        game = self.saves / "OwnGame.nes"
        game.write_bytes(b"unchanged own game")
        with self.assertRaisesRegex(HubError, "Spiel"):
            self.backup()
        self.assertEqual(game.read_bytes(), b"unchanged own game")
        self.assertFalse(list((self.root / "chosen").glob("*.zip")))

    def test_restore_cannot_overwrite_newly_registered_game_file(self):
        save = self.saves / "own.sav"
        save.write_bytes(b"archive progress")
        archive = self.backup()
        save.write_bytes(b"current unchanged file")
        # Even unusual configured game endings are protected by exact metadata.
        self.manager.data_dir.mkdir(exist_ok=True)
        (self.manager.data_dir / "library.json").write_text(json.dumps({"schema_version": 1, "games": [{"path": str(save)}]}), encoding="utf-8")
        with self.assertRaisesRegex(HubError, "Spiel"):
            self.manager.restore(self.entry, self.record, archive)
        self.assertEqual(save.read_bytes(), b"current unchanged file")
        self.assertFalse((self.manager.data_dir / "backups").exists())


if __name__ == "__main__":
    unittest.main()
