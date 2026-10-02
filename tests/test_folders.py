import json
from pathlib import Path
import re
import shutil
import unittest
from unittest.mock import patch

from core.archives import RESERVED
from core.errors import HubError
from core.installer import HubService
from core.settings import SettingsStore
from tests.helpers import TemporaryDirectory, make_catalog, windows_executable


class FolderTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.program = self.root / "program"
        self.program.mkdir()
        shutil.copytree(Path(__file__).resolve().parent.parent / "configs", self.program / "configs")
        self.catalog, self.entry = make_catalog(self.program)
        app_directory = patch("core.paths.app_directory", return_value=self.program)
        app_directory.start()
        self.addCleanup(app_directory.stop)
        documents = patch("core.folders._windows_documents", return_value=self.root / "Documents")
        documents.start()
        self.addCleanup(documents.stop)
        explorer = patch("core.folders.os.startfile")
        self.explorer = explorer.start()
        self.addCleanup(explorer.stop)

    def service(self, data_dir):
        service = HubService(self.catalog, data_dir)
        self.addCleanup(self.close, service)
        return service

    @staticmethod
    def close(service):
        for handler in list(service.logger.handlers):
            handler.close()
            service.logger.removeHandler(handler)

    def test_uninstalled_games_folder_is_lazy_and_does_not_touch_games_or_library(self):
        service = self.service(self.root / "data")
        own_games = self.root / "my games"
        own_games.mkdir()
        game = own_games / "Eigene Datei.nes"
        game.write_bytes(b"provided local game file")
        service.settings.set("game_folders", [str(own_games)])
        before = game.read_bytes()
        expected = service.games_directory(self.entry)
        self.assertTrue(expected.is_relative_to(self.root / "Documents" / "EmulatorHub" / "Games"))
        self.assertFalse(expected.exists())
        self.assertFalse(service.is_installed(self.entry["id"]))
        self.assertEqual(service.open_games_folder(self.entry), expected)
        self.explorer.assert_called_once_with(str(expected))
        self.assertTrue(expected.is_dir())
        self.assertEqual(SettingsStore(service.data_dir).get("games_dir"), {self.entry["id"]: str(expected)})
        self.assertEqual(service.settings.get("game_folders"), [str(own_games)])
        self.assertEqual(game.read_bytes(), before)
        self.assertEqual(list(own_games.iterdir()), [game])

    def test_manual_folder_uses_recorded_root_and_reports_missing_or_explorer_failure(self):
        service = self.service(self.root / "data")
        folder = self.root / "own emulator"
        nested = folder / "bin"
        nested.mkdir(parents=True)
        (nested / self.entry["exe"]).write_bytes(windows_executable())
        service.register_manual(self.entry, folder)
        self.assertEqual(service.open_emulator_folder(self.entry), folder)
        self.explorer.assert_called_once_with(str(folder))
        self.explorer.side_effect = OSError("Zugriff verweigert")
        with self.assertRaisesRegex(HubError, "Windows-Explorer.*geöffnet"):
            service.open_emulator_folder(self.entry)
        self.explorer.side_effect = None
        self.explorer.reset_mock()
        folder.rename(self.root / "moved emulator")
        with self.assertRaisesRegex(HubError, "existiert nicht mehr.*"):
            service.open_emulator_folder(self.entry)
        self.explorer.assert_not_called()

    def test_custom_folder_persists_per_emulator_and_reset_leaves_its_files(self):
        service = self.service(self.root / "data")
        second = {**self.entry, "id": "second", "emulator": "Zweiter Emulator"}
        self.catalog.items.append(second)
        custom = self.root / "custom games"
        custom.mkdir()
        game = custom / "Eigene Datei.iso"
        game.write_bytes(b"unchanged custom game")
        second_custom = self.root / "second games"
        service.set_games_directory(self.entry, custom)
        service.set_games_directory(second, second_custom)
        reloaded = self.service(service.data_dir)
        self.assertEqual(reloaded.games_directory(self.entry), custom)
        self.assertEqual(reloaded.games_directory(second), second_custom)
        self.assertFalse(second_custom.exists())
        standard = reloaded.reset_games_directory(self.entry)
        self.assertTrue(standard.is_relative_to(self.root / "Documents"))
        self.assertFalse(standard.exists())
        self.assertEqual(SettingsStore(service.data_dir).get("games_dir"), {"second": str(second_custom)})
        self.assertEqual(game.read_bytes(), b"unchanged custom game")
        self.assertEqual(list(custom.iterdir()), [game])
        self.assertEqual(reloaded.settings.get("game_folders"), [])
        self.explorer.assert_not_called()

    def test_default_names_are_windows_safe_and_collision_free(self):
        service = self.service(self.root / "data")
        names = ["Same/Name", "Same\\Name", "CaseName", "casename", "CON", "...", "A" * 150]
        entries = [{**self.entry, "id": f"name-{index}", "emulator": name} for index, name in enumerate(names)]
        self.catalog.items.extend(entries)
        paths = [service.games_directory(entry) for entry in entries]
        self.assertEqual(len({str(path).casefold() for path in paths}), len(paths))
        for path in paths:
            with self.subTest(name=path.name):
                self.assertEqual(path.parent, self.root / "Documents" / "EmulatorHub" / "Games")
                self.assertFalse(re.search(r'[<>:"/\\|?*\x00-\x1f]', path.name))
                self.assertFalse(path.name.endswith((" ", ".")))
                self.assertNotIn(path.name.split(".")[0].upper(), RESERVED)
                self.assertLessEqual(len(path.name), 255)
                self.assertFalse(path.exists())

    def test_portable_default_and_custom_paths_follow_program_move(self):
        (self.program / "portable.flag").touch()
        service = self.service(None)
        second = {**self.entry, "id": "second", "emulator": "Zweiter Emulator"}
        third = {**self.entry, "id": "third", "emulator": "Dritter Emulator"}
        self.catalog.items.extend([second, third])
        standard = service.open_games_folder(self.entry)
        self.assertEqual(standard.parent, self.program / "Games")
        custom = self.program / "my custom games"
        custom.mkdir()
        game = custom / "Own.nes"
        game.write_bytes(b"provided game remains unchanged")
        service.set_games_directory(second, custom)
        stored = json.loads(service.settings.path.read_text(encoding="utf-8"))["games_dir"]
        self.assertTrue(all(path.startswith("@hub:/") for path in stored.values()))
        self.close(service)
        moved_program = self.root / "relocated program"
        shutil.copytree(self.program, moved_program)
        with patch("core.paths.app_directory", return_value=moved_program):
            moved = self.service(None)
            moved_standard = moved_program / standard.relative_to(self.program)
            moved_custom = moved_program / custom.relative_to(self.program)
            self.assertEqual(moved.games_directory(self.entry), moved_standard)
            self.assertEqual(moved.games_directory(second), moved_custom)
            self.assertEqual(moved.games_directory(third).parent, moved_program / "Games")
            self.assertEqual(moved.open_games_folder(self.entry), moved_standard)
            self.assertEqual(moved.open_games_folder(second), moved_custom)
            self.assertEqual((moved_custom / game.name).read_bytes(), b"provided game remains unchanged")
            self.assertEqual(moved.settings.get("game_folders"), [])
            self.explorer.assert_called_with(str(moved_custom))


if __name__ == "__main__":
    unittest.main()
