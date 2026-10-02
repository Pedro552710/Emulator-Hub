import json
import os
from pathlib import Path
import shutil
import threading
import unittest
from unittest.mock import Mock, patch

from core.errors import HubError
from core.installer import HubService, default_data_dir
from core.settings import SettingsStore
from core.state import read_json
from core.storage import read_installed
from tests.helpers import TemporaryDirectory, make_catalog, windows_executable


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def service(self, program):
        catalog, entry = make_catalog(program)
        service = HubService(catalog)
        self.addCleanup(self.close, service)
        return service, entry

    @staticmethod
    def close(service):
        for handler in list(service.logger.handlers):
            handler.close()
            service.logger.removeHandler(handler)

    def test_normal_mode_keeps_localappdata_default_and_explicit_override(self):
        program = self.root / "program"
        program.mkdir()
        shutil.copytree(Path(__file__).resolve().parent.parent / "configs", program / "configs")
        with patch("core.paths.app_directory", return_value=program), patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "local")}):
            self.assertEqual(default_data_dir(), self.root / "local" / "EmulatorHub")
            (program / "portable.flag").touch()
            self.assertEqual(default_data_dir(), program / "data")
            catalog, _ = make_catalog(program)
            service = HubService(catalog, self.root / "explicit")
            self.addCleanup(self.close, service)
            self.assertEqual(service.data_dir, self.root / "explicit")

    def test_moving_portable_program_preserves_installed_and_local_game_paths(self):
        program = self.root / "original"
        program.mkdir()
        (program / "portable.flag").touch()
        # Defaults are copied from the project exactly as in a bundled EXE.
        shutil.copytree(Path(__file__).resolve().parent.parent / "configs", program / "configs")
        with patch("core.paths.app_directory", return_value=program):
            service, entry = self.service(program)
            folder = service.emulator_dir / entry["id"]
            folder.mkdir()
            exe = folder / entry["exe"]
            exe.write_bytes(windows_executable())
            service._save({entry["id"]: {"path": str(folder), "exe_path": str(exe),
                          "version": "1.0", "date": "2026-10-01", "managed": True}})
            games = program / "own games"
            games.mkdir()
            game = games / "Eigene Testdatei.nes"
            game.write_bytes(b"only test metadata")
            external = self.root / "external"
            service.library.set_roots([games, external])
            service.library.scan([games], Mock(), Mock(), threading.Event())
            saves = folder / "saves"
            saves.mkdir()
            (saves / "slot.sav").write_bytes(b"portable saved progress")
            service.settings.set("profile_overrides", {entry["id"]: {"backup_paths": [str(saves)]}})
            archive = service.backup(entry, service.data_dir / "backups", Mock(), Mock(), threading.Event())
            self.assertIn("@hub:/data/emulators/", service.installed_path.read_text())
            self.assertIn("@hub:/own games", service.settings.path.read_text())
            self.assertIn(str(external).replace("\\", "\\\\"), service.settings.path.read_text())
            self.close(service)
        relocated = self.root / "relocated"
        shutil.copytree(program, relocated)
        with patch("core.paths.app_directory", return_value=relocated):
            moved, entry = self.service(relocated)
            self.assertTrue(moved.is_installed(entry["id"]))
            self.assertEqual(Path(moved.installed[entry["id"]]["exe_path"]), relocated / "data" / "emulators" / entry["id"] / entry["exe"])
            self.assertEqual(moved.settings.get("game_folders"), [str(relocated / "own games"), str(external)])
            self.assertEqual(Path(moved.library.games[0]["path"]), relocated / "own games" / game.name)
            self.assertEqual(moved.library.scan([relocated / "own games"], Mock(), Mock(), threading.Event())["added"], 0)
            moved_save = relocated / "data" / "emulators" / entry["id"] / "saves" / "slot.sav"
            moved_save.write_bytes(b"current after move")
            moved_archive = relocated / archive.relative_to(program)
            self.assertEqual(moved.restore_backup(entry, moved_archive, Mock(), Mock(), threading.Event())["count"], 1)
            self.assertEqual(moved_save.read_bytes(), b"portable saved progress")

    def test_portable_traversal_is_rejected_before_path_use(self):
        program = self.root / "program"
        data = program / "data"
        data.mkdir(parents=True)
        path = data / "settings.json"
        path.write_text(json.dumps({"game_folders": ["@hub:/../../other"]}))
        with patch("core.paths.app_directory", return_value=program), self.assertRaises(HubError):
            read_json(path, {})


class ComfortServiceTests(unittest.TestCase):
    def test_service_routes_bios_backup_and_restore_with_safety_backup(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog, entry = make_catalog(root)
            entry["bios"] = [{"label": "Eigene Firmware", "root": "emulator", "directory": "firmware", "filenames": ["own.bin"], "required": True}]
            entry["backup_paths"] = [{"label": "Spielstände", "root": "emulator", "directory": "saves", "type": "directory"}]
            service = HubService(catalog, root / "data")
            try:
                folder = service.emulator_dir / entry["id"]
                folder.mkdir()
                exe = folder / entry["exe"]
                exe.write_bytes(windows_executable())
                service._save({entry["id"]: {"path": str(folder), "exe_path": str(exe), "version": "1.0", "date": "2026-10-01"}})
                event, progress, log = threading.Event(), Mock(), Mock()
                self.assertEqual(service.check_bios(entry, progress, log, event)[0]["status"], "fehlt")
                saves = folder / "saves"
                saves.mkdir()
                save = saves / "slot.sav"
                save.write_bytes(b"old saved progress")
                archive = service.backup(entry, root / "chosen backups", progress, log, event)
                save.write_bytes(b"new saved progress")
                result = service.restore_backup(entry, archive, progress, log, event)
                self.assertTrue(result["safety_backup"].is_file())
                self.assertEqual(save.read_bytes(), b"old saved progress")
                self.assertEqual(result["count"], 1)
            finally:
                PortableTests.close(service)


if __name__ == "__main__":
    unittest.main()
