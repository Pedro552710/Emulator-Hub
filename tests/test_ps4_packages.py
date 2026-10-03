"""Eigene PS4-Pakete bleiben Metadaten; nur das externe Tool erhält den Pfad."""

import json
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

from core.errors import Cancelled, HubError
from core.folders import set_games_directory
from core.launch import (
    build_launch_command,
    build_ps4_pkg_tool_command,
    compatible_entries,
    launch_game,
    launch_ps4_pkg_tool,
)
from core.library import LibraryStore, PS4_PACKAGE_STATUS, game_status, is_ps4_package
from core.settings import SettingsStore
from tests.helpers import TemporaryDirectory, make_catalog, windows_executable


class Ps4PackageLibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog, _ = make_catalog(self.root)
        self.entry = self.catalog.items[0]
        self.entry["konsole"] = "PlayStation 4"
        self.data = self.root / "data"
        self.settings = SettingsStore(self.data)
        self.library = LibraryStore(self.data, self.catalog, self.settings, launcher=Mock())
        self.games = self.root / "Eigene Spiele"
        self.games.mkdir()
        self.package = self.games / "Eigenes Spiel & Zeichen; $(test) ä {Spiel}.PKG"
        self.package.write_bytes(b"synthetische Datei, kein PS4-Paket")

    def scan(self, roots=None, cancel=None):
        return self.library.scan([self.games] if roots is None else roots, Mock(), Mock(), cancel or threading.Event())

    def test_scan_lists_pkg_as_package_never_launchable_and_does_not_read_contents(self):
        with patch.object(Path, "read_bytes", side_effect=AssertionError("Paketinhalt darf nicht gelesen werden")):
            self.scan()
        game = self.library.games[0]
        self.assertEqual(Path(game["path"]), self.package)
        self.assertEqual(game["console"], "PlayStation 4")
        self.assertEqual(game["candidates"], ["PlayStation 4"])
        self.assertEqual(game["package_kind"], "ps4_pkg")
        self.assertIs(game["launchable"], False)
        self.assertEqual(game_status(game), PS4_PACKAGE_STATUS)
        self.assertTrue(is_ps4_package(game))
        with self.assertRaisesRegex(HubError, "Im PS4 PKG Tool installieren"):
            self.library.launch_game(game["id"], self.entry["id"])
        self.library.launcher.assert_not_called()
        self.assertEqual(self.library.get_game(game["id"])["last_played"], "")
        self.assertEqual(self.package.read_bytes(), b"synthetische Datei, kein PS4-Paket")

    def test_pkg_is_not_reassigned_to_other_console_even_with_custom_configuration(self):
        custom = self.root / "custom-extensions.json"
        custom.write_text(json.dumps({"schema_version": 1, "extensions": {".pkg": "NES", ".nes": "NES"}}), encoding="utf-8")
        self.library = LibraryStore(self.data, self.catalog, self.settings, config_path=custom)
        self.scan()
        game = self.library.games[0]
        self.assertEqual(game["console"], "PlayStation 4")
        with self.assertRaisesRegex(HubError, "anderen Konsole"):
            self.library.set_console(game["id"], "NES")

    def test_ps4_games_directory_adds_only_packages_without_changing_other_folder_scans(self):
        set_games_directory(self.entry, self.games, self.settings)
        (self.games / "eboot.bin").write_bytes(b"synthetisch")
        other = self.root / "Anderer Emulator"
        other.mkdir()
        (other / "Anderes.pkg").write_bytes(b"synthetisch")
        (other / "Anderes.nes").write_bytes(b"synthetisch")
        other_entry = {**self.entry, "id": "other-emulator", "konsole": "NES"}
        self.catalog.items.append(other_entry)
        set_games_directory(other_entry, other, self.settings)
        result = self.scan([])
        self.assertEqual(result["added"], 1)
        self.assertEqual([g["path"] for g in self.library.games], [str(self.package)])
        result = self.scan([self.games, self.games])
        self.assertEqual(result["added"], 1)  # EBOOT erst im ausdrücklich gewählten Scan.
        self.assertEqual(result["total"], 2)

    def test_saved_pkg_metadata_cannot_mark_package_as_launchable_after_reload(self):
        self.scan()
        raw = json.loads(self.library.path.read_text(encoding="utf-8"))
        raw["games"][0].update({"console": "NES", "launchable": True, "emulator_id": "mesen"})
        self.library.path.write_text(json.dumps(raw), encoding="utf-8")
        reloaded = LibraryStore(self.data, self.catalog, self.settings, launcher=Mock())
        game = reloaded.games[0]
        self.assertIs(game["launchable"], False)
        self.assertEqual(game["console"], "PlayStation 4")
        self.assertIsNone(game["emulator_id"])
        with self.assertRaisesRegex(HubError, "Im PS4 PKG Tool installieren"):
            reloaded.launch_game(game["id"])
        reloaded.launcher.assert_not_called()

    def test_cancelled_scan_preserves_package_metadata(self):
        self.scan()
        saved = self.library.path.read_bytes()
        cancel = threading.Event()
        cancel.set()
        with self.assertRaises(Cancelled):
            self.scan(cancel=cancel)
        self.assertEqual(self.library.path.read_bytes(), saved)

    def test_utility_is_never_a_compatible_emulator(self):
        utility = {**self.entry, "id": "ps4-pkg-tool", "entry_type": "utility"}
        self.catalog.items.append(utility)
        self.assertEqual(compatible_entries(self.catalog, "PlayStation 4"), [self.entry])
        with self.assertRaisesRegex(HubError, "kein Emulator"):
            build_launch_command(utility, self.root / "Tool.exe", self.games / "eboot.bin")


class Ps4PackageLaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "Externes PS4 Tool & Zeichen"
        self.folder.mkdir()
        self.exe = self.folder / "PS4 PKG Tool.exe"
        self.exe.write_bytes(windows_executable())
        games = self.root / "Meine eigenen Pakete"
        games.mkdir()
        self.package = games / "Spiel & Zeichen; $(test) ä {Spiel}.pkg"
        self.package.write_bytes(b"synthetische Datei, kein PS4-Paket")
        self.entry = {"id": "ps4-pkg-tool", "entry_type": "utility", "emulator": "PS4 PKG Tool",
                      "exe": "PS4 PKG Tool.exe", "package_args": ["{package}"],
                      "github_repo": "pearlxcore/PS4PKGTool"}
        self.service = Mock()
        self.service.installed = {self.entry["id"]: {"path": str(self.folder), "exe_path": str(self.exe)}}
        self.service.is_installed.return_value = True

    def test_tool_receives_exact_absolute_path_as_single_argument_without_shell(self):
        with patch("core.launch.subprocess.Popen") as start:
            process = launch_ps4_pkg_tool(self.service, self.entry, self.package)
        start.assert_called_once_with([str(self.exe.resolve()), str(self.package.resolve())],
                                      cwd=self.folder, shell=False)
        self.assertIs(process, start.return_value)
        self.assertEqual(self.package.read_bytes(), b"synthetische Datei, kein PS4-Paket")

    def test_pkg_cannot_be_started_by_any_emulator_or_catalog_override(self):
        emulator = {"id": "emulator", "exe": self.exe.name, "launch_args": ["{game}"], "launch_extensions": [".pkg"]}
        with patch("core.launch.subprocess.Popen") as start:
            with self.assertRaisesRegex(HubError, "Im PS4 PKG Tool installieren"):
                build_launch_command(emulator, self.exe, self.package)
            with self.assertRaisesRegex(HubError, "Im PS4 PKG Tool installieren"):
                launch_game(self.service, emulator, self.package)
        start.assert_not_called()

    def test_missing_tool_missing_package_wrong_type_and_outside_executable_do_not_spawn(self):
        with patch("core.launch.subprocess.Popen") as start:
            self.service.is_installed.return_value = False
            with self.assertRaisesRegex(HubError, "noch nicht installiert"):
                launch_ps4_pkg_tool(self.service, self.entry, self.package)
            self.service.is_installed.return_value = True
            with self.assertRaisesRegex(HubError, "nicht gefunden"):
                launch_ps4_pkg_tool(self.service, self.entry, self.root / "fehlt.pkg")
            with self.assertRaisesRegex(HubError, "Andere Dateitypen"):
                launch_ps4_pkg_tool(self.service, self.entry, self.root / "eboot.bin")
            self.service.installed[self.entry["id"]]["path"] = str(self.root / "Anderes Tool")
            with self.assertRaisesRegex(HubError, "außerhalb"):
                launch_ps4_pkg_tool(self.service, self.entry, self.package)
        start.assert_not_called()

    def test_only_verified_fixed_gui_call_is_allowed(self):
        for change in ({"package_args": ["--install", "{package}"]}, {"entry_type": "emulator"},
                       {"github_repo": "other/PS4-PKG-Tool"}, {"id": "other-tool"}):
            with self.subTest(change=change), self.assertRaisesRegex(HubError, "kein belegter PKG-Aufruf"):
                build_ps4_pkg_tool_command({**self.entry, **change}, self.exe, self.package)
        with self.assertRaisesRegex(HubError, "Startdatei passt nicht"):
            build_ps4_pkg_tool_command(self.entry, self.folder / "other.exe", self.package)

    def test_start_failure_and_corrupt_tool_are_readable_errors(self):
        with patch("core.launch.subprocess.Popen", side_effect=OSError("Zugriff verweigert")), self.assertRaisesRegex(HubError, "konnte nicht geöffnet"):
            launch_ps4_pkg_tool(self.service, self.entry, self.package)
        self.exe.write_bytes(b"keine EXE")
        with patch("core.launch.subprocess.Popen") as start, self.assertRaisesRegex(HubError, "Windows-EXE"):
            launch_ps4_pkg_tool(self.service, self.entry, self.package)
        start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
