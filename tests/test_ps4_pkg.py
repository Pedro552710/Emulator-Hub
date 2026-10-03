"""Eigene synthetische Pakete: erkennen und an den externen Viewer übergeben."""

from copy import deepcopy
import json
from pathlib import Path
import stat
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core.catalog import Catalog
from core.errors import HubError
from core.installer import HubService
from core.launch import (build_launch_command, build_ps4_pkg_tool_command as build_package_command,
                         compatible_entries, launch_game)
from core.library import LibraryStore, is_ps4_package
from tests.helpers import TemporaryDirectory, windows_executable


class PS4PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = Catalog()
        self.helper = self.catalog.by_id("ps4-pkg-tool")
        self.emulator = self.catalog.by_id("shadps4")
        self.service = HubService(self.catalog, self.root / "data")
        self.service.settings.set("show_hidden", True)  # PS4-Funktionen bleiben ausdrücklich testbar.
        self.addCleanup(self.close_logger)
        self.games = self.root / "Eigene PS4-Dateien & Zeichen; $(test)"
        self.games.mkdir()
        self.package = self.games / "Eigenes Paket & Update; $(test).PKG"
        self.package.write_bytes(b"synthetischer Platzhalter, kein echtes Spielpaket")
        self.scan()
        self.identifier = self.service.library.games[0]["id"]

    def close_logger(self):
        for handler in list(self.service.logger.handlers):
            handler.close()
            self.service.logger.removeHandler(handler)

    def scan(self):
        return self.service.library.scan([self.games], Mock(), Mock(), threading.Event())

    def install_helper(self):
        folder = self.root / "Eigenes Hilfsprogramm mit Leerzeichen"
        folder.mkdir()
        executable = folder / self.helper["exe"]
        executable.write_bytes(windows_executable())
        self.service.register_manual(self.helper, folder)
        return executable

    def test_scan_records_packages_as_ps4_paths_only_and_keeps_files_unchanged(self):
        before = self.package.read_bytes()
        game = self.service.library.get_game(self.identifier)
        self.assertTrue(is_ps4_package(game))
        self.assertEqual(game["console"], "PlayStation 4")
        self.assertEqual(game["candidates"], ["PlayStation 4"])
        self.assertEqual(game["path"], str(self.package))
        self.assertFalse(game["missing"])
        self.assertFalse(game["launchable"])
        self.assertEqual(game["package_kind"], "ps4_pkg")
        self.assertEqual(game["last_played"], "")
        self.assertIsNone(game["emulator_id"])
        self.assertEqual(self.scan()["added"], 0)
        self.assertEqual(self.package.read_bytes(), before)
        self.assertEqual(list(self.games.iterdir()), [self.package])

    def test_saved_wrong_console_or_launchable_marker_cannot_make_package_a_game(self):
        path = self.service.library.path
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["games"][0].update({"console": "NES", "candidates": ["NES"],
                                    "assigned_manually": True, "emulator_id": "mesen", "launchable": True})
        path.write_text(json.dumps(payload), encoding="utf-8")
        library = LibraryStore(self.service.data_dir, self.catalog, self.service.settings)
        game = library.get_game(self.identifier)
        self.assertEqual(game["console"], "PlayStation 4")
        self.assertEqual(game["candidates"], ["PlayStation 4"])
        self.assertFalse(game["launchable"])
        self.assertIsNone(game["emulator_id"])
        with self.assertRaisesRegex(HubError, "nicht direkt startbar"):
            library.launch_game(self.identifier)

    def test_old_or_misassigned_extension_config_still_identifies_packages_as_ps4(self):
        for extensions in ({".nes": "NES"}, {".pkg": "NES"}):
            with self.subTest(extensions=extensions):
                config = self.root / "custom-extensions.json"
                config.write_text(json.dumps({"schema_version": 1, "extensions": extensions}), encoding="utf-8")
                library = LibraryStore(self.root / "custom-data", self.catalog, self.service.settings,
                                       config_path=config)
                library.scan([self.games], Mock(), Mock(), threading.Event())
                self.assertEqual(library.extensions[".pkg"], ["PlayStation 4"])
                self.assertEqual(library.games[0]["console"], "PlayStation 4")

    def test_assigned_ps4_games_folder_adds_only_packages_without_persisting_extra_roots(self):
        assigned = self.root / "Zugeordneter eigener PS4-Ordner"
        assigned.mkdir()
        package = assigned / "Eigenes Update.pkg"
        package.write_bytes(b"synthetischer Platzhalter")
        (assigned / "Anderes Spiel.nes").write_bytes(b"synthetische Datei")
        self.service.set_games_directory(self.emulator, assigned)
        self.service.library.set_roots([self.games])
        result = self.scan()
        self.assertEqual(result["added"], 1)
        self.assertEqual({Path(game["path"]) for game in self.service.library.games}, {self.package, package})
        self.assertEqual(self.service.settings.get("game_folders"), [str(self.games)])
        self.assertEqual(package.read_bytes(), b"synthetischer Platzhalter")

    def test_package_console_cannot_be_changed_to_make_it_launchable(self):
        with self.assertRaisesRegex(HubError, "PS4-Pakete"):
            self.service.library.set_console(self.identifier, "NES")
        self.assertEqual(self.service.library.get_game(self.identifier)["console"], "PlayStation 4")

    def test_packages_are_rejected_at_every_game_start_layer_without_process_or_history(self):
        game = self.service.library.get_game(self.identifier)
        with patch("core.launch.subprocess.Popen") as process, patch.object(self.service, "install") as install:
            for action in (
                    lambda: self.service.launch_game(self.identifier),
                    lambda: self.service.library.launch_game(self.identifier),
                    lambda: self.service._launch_game(game, self.emulator["id"]),
                    lambda: launch_game(self.service, self.emulator, self.package),
                    lambda: build_launch_command({"exe": "other.exe", "launch_args": ["{game}"]},
                                                 self.root / "other.exe", self.package)):
                with self.subTest(action=action), self.assertRaisesRegex(HubError, "nicht direkt startbar"):
                    action()
        process.assert_not_called()
        install.assert_not_called()
        self.assertEqual(self.service.library.get_game(self.identifier)["last_played"], "")
        self.assertEqual(self.service.settings.recent_emulators, [])

    def test_literal_viewer_argument_list_has_no_shell_and_handoff_keeps_histories(self):
        executable = self.install_helper()
        game_before = self.service.library.get_game(self.identifier)
        settings_before = self.service.settings.path.read_bytes() if self.service.settings.path.exists() else None
        with patch("core.launch.subprocess.Popen") as process, patch.object(self.service, "install") as install:
            result = self.service.open_ps4_package(self.identifier)
        process.assert_called_once_with([str(executable), str(self.package)], cwd=executable.parent, shell=False)
        self.assertIs(result, process.return_value)
        install.assert_not_called()
        self.assertEqual(self.service.library.get_game(self.identifier), game_before)
        settings_after = self.service.settings.path.read_bytes() if self.service.settings.path.exists() else None
        self.assertEqual(settings_after, settings_before)
        self.assertEqual(self.package.read_bytes(), b"synthetischer Platzhalter, kein echtes Spielpaket")

    def test_handoff_does_not_open_or_parse_package_contents(self):
        executable = self.install_helper()
        original_open = Path.open

        def only_executable_open(path, *args, **kwargs):
            if path == self.package:
                self.fail("Der Hub darf keine Paketinhalte lesen.")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", only_executable_open), patch("core.launch.subprocess.Popen") as process:
            self.service.open_ps4_package(self.identifier)
        process.assert_called_once_with([str(executable), str(self.package)], cwd=executable.parent, shell=False)

    def test_missing_tool_offers_explicit_installation_without_downloading(self):
        with patch.object(self.service, "install") as install, patch("core.launch.subprocess.Popen") as process:
            with self.assertRaisesRegex(HubError, "ausdrücklich"):
                self.service.open_ps4_package(self.identifier)
        install.assert_not_called()
        process.assert_not_called()

    def test_wrong_file_missing_package_or_reparse_point_is_not_handed_off(self):
        executable = self.install_helper()
        wrong = self.games / "eboot.bin"
        wrong.write_bytes(b"synthetische Datei")
        for path in (wrong, self.games / "fehlt.pkg", self.games):
            with self.subTest(path=path), self.assertRaises(HubError):
                build_package_command(self.helper, executable, path)
        original_lstat = Path.lstat

        def lstat_with_reparse(path, *args, **kwargs):
            if path == self.package:
                return SimpleNamespace(st_mode=original_lstat(path, *args, **kwargs).st_mode,
                                       st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT)
            return original_lstat(path, *args, **kwargs)

        with patch.object(Path, "lstat", lstat_with_reparse), self.assertRaisesRegex(HubError, "Verknüpfung"):
            build_package_command(self.helper, executable, self.package)

    def test_unproven_package_parameters_and_wrong_startfile_are_rejected(self):
        executable = self.install_helper()
        for args in (["--install", "{package}"], ["{package}", "--silent"], "{package}", [], None):
            with self.subTest(args=args), self.assertRaisesRegex(HubError, "belegter"):
                build_package_command({**self.helper, "package_args": args}, executable, self.package)
        with self.assertRaisesRegex(HubError, "Startdatei passt"):
            build_package_command(self.helper, self.root / "other.exe", self.package)

    def test_tool_start_failure_or_outside_executable_is_readable_and_no_game_history_changes(self):
        self.install_helper()
        with patch("core.launch.subprocess.Popen", side_effect=OSError("Zugriff verweigert")):
            with self.assertRaisesRegex(HubError, "Runtime"):
                self.service.open_ps4_package(self.identifier)
        self.service.installed[self.helper["id"]]["path"] = str(self.root / "anderer Ordner")
        with patch("core.launch.subprocess.Popen") as process, self.assertRaisesRegex(HubError, "außerhalb"):
            self.service.open_ps4_package(self.identifier)
        process.assert_not_called()
        self.assertEqual(self.service.library.get_game(self.identifier)["last_played"], "")
        self.assertEqual(self.service.settings.recent_emulators, [])

    def test_helper_never_becomes_an_emulator_candidate_or_aggregate_update_target(self):
        self.assertNotIn(self.helper, compatible_entries(self.catalog, "PlayStation 4"))
        self.assertIn(self.emulator, compatible_entries(self.catalog, "PlayStation 4"))
        helper = deepcopy(self.helper)
        helper["supported_consoles"] = ["PlayStation 4"]
        self.catalog.items.append(helper)
        self.assertNotIn(helper, compatible_entries(self.catalog, "PlayStation 4"))
        self.install_helper()
        self.service.installed[self.helper["id"]].update({"version": "1.0", "managed": True})
        with patch.object(self.service.github, "latest") as latest:
            checked = self.service.check_updates(Mock(), Mock(), threading.Event())
        latest.assert_not_called()
        self.assertNotIn(self.helper["id"], checked)
        with patch.object(self.service, "check_updates", return_value={self.helper["id"]: "99.0"}), patch.object(self.service, "install") as install:
            result = self.service.update_all(Mock(), Mock(), threading.Event())
        install.assert_not_called()
        self.assertNotIn(self.helper["id"], result["updated"])

    def test_utility_download_requires_review_and_explicit_click_before_any_network(self):
        with patch.object(self.service.github, "latest") as latest, patch.object(self.service.policy, "get") as download:
            with self.assertRaisesRegex(HubError, "Downloadhinweis"):
                self.service.install(self.helper, Mock(), Mock(), threading.Event())
        latest.assert_not_called()
        download.assert_not_called()

    def test_download_preview_only_reads_release_metadata_and_is_bound_to_reviewed_source(self):
        source = f"https://github.com/{self.helper['github_repo']}/releases/download/v1.8.0/PS4-PKG-Tool-v1.8.0.zip"
        digest = "1ef9bb1f4ec1ad4e10f5a7d814e216323019385977c5b4409c911c5943884ea1"
        asset = {"name": "PS4-PKG-Tool-v1.8.0.zip", "browser_download_url": source, "digest": "sha256:" + digest}
        release = {"tag_name": "v1.8.0", "draft": False, "prerelease": False, "assets": [asset]}
        with patch.object(self.service.github, "latest", return_value=release), patch.object(
                self.service.github, "asset", return_value=asset), patch.object(self.service.policy, "get") as download:
            preview = self.service.prepare_install(self.helper)
        download.assert_not_called()
        self.assertIn(source, preview.notice)
        self.assertIn(digest, preview.notice)
        self.assertIn("Drittprogramm", preview.notice)
        self.assertIn("Antivirus", preview.notice)
        with patch.object(self.service, "_install") as install:
            self.service.install(self.helper, Mock(), Mock(), threading.Event(), preview=preview)
            with self.assertRaisesRegex(HubError, "Downloadhinweis"):
                self.service.install(self.helper, Mock(), Mock(), threading.Event(), preview=preview)
        install.assert_called_once()

    def test_starting_helper_gui_is_not_recorded_as_an_emulator(self):
        executable = self.install_helper()
        with patch("core.installer.subprocess.Popen") as process:
            self.service.start(self.helper)
        process.assert_called_once_with([str(executable)], cwd=executable.parent, shell=False)
        self.assertEqual(self.service.settings.recent_emulators, [])


if __name__ == "__main__":
    unittest.main()
