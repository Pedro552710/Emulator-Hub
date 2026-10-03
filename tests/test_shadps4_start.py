"""shadPS4 ohne Fremdprozess: QTLauncher bevorzugen, Core nur mit Parametern."""

import base64
from pathlib import Path
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

from core.catalog import Catalog
from core.errors import HubError
from core.installer import HubService
from core.launch import build_emulator_command
from core.shortcuts import create_shortcuts
from tests.helpers import TemporaryDirectory, windows_executable


class ShadPS4StartTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.catalog = Catalog()
        self.entry = self.catalog.by_id("shadps4")
        self.service = HubService(self.catalog, self.root / "data")
        self.service.settings.set("show_hidden", True)  # PS4-Funktionen bleiben ausdrücklich testbar.
        self.addCleanup(self.close_logger)
        self.folder = self.root / "Eigener PS4-Emulator & Zeichen"
        self.folder.mkdir()
        self.core = self.folder / "shadPS4.exe"
        self.core.write_bytes(windows_executable())

    def close_logger(self):
        for handler in list(self.service.logger.handlers):
            handler.close()
            self.service.logger.removeHandler(handler)

    def launcher(self, directory="qtlauncher", *, content=None):
        folder = self.folder / directory
        folder.mkdir(parents=True, exist_ok=True)
        executable = folder / "shadPS4QtLauncher.exe"
        executable.write_bytes(windows_executable() if content is None else content)
        return executable

    def assert_start(self, executable, arguments):
        with patch("core.installer.subprocess.Popen") as start:
            note = self.service.start(self.entry)
        start.assert_called_once_with([str(executable), *arguments], cwd=executable.parent, shell=False)
        command = start.call_args.args[0]
        if Path(command[0]).name.casefold() == "shadps4.exe":
            self.assertGreater(len(command), 1)
            self.assertIn("Big-Picture", note)
            self.assertIn("-b", note)
        else:
            self.assertIn("QTLauncher", note)
        self.assertEqual(self.service.settings.recent_emulators[0]["id"], "shadps4")

    def test_core_only_manual_install_starts_big_picture_and_never_parameterless(self):
        self.service.register_manual(self.entry, self.folder)
        self.assert_start(self.core, ["-b"])

    def test_existing_core_record_prefers_manually_added_qtlauncher_in_subfolder(self):
        self.service.register_manual(self.entry, self.folder)
        qt = self.launcher()
        self.assert_start(qt, [])
        self.assertEqual(Path(self.service.installed[self.entry["id"]]["exe_path"]), self.core)
        qt.unlink()
        self.assert_start(self.core, ["-b"])

    def test_corrupt_optional_launcher_does_not_start_an_unvalidated_binary(self):
        self.service.register_manual(self.entry, self.folder)
        self.launcher(content=b"synthetische Datei ohne Windows-EXE")
        self.assert_start(self.core, ["-b"])

    def test_optional_launcher_through_reparse_directory_is_ignored(self):
        self.service.register_manual(self.entry, self.folder)
        qt = self.launcher()
        original_lstat = Path.lstat
        intercepted = []

        def reparse(path, *args, **kwargs):
            if path == qt.parent:
                intercepted.append(path)
                return SimpleNamespace(st_mode=0, st_file_attributes=0x400)
            return original_lstat(path, *args, **kwargs)

        with patch("pathlib.Path.lstat", reparse):
            self.assert_start(self.core, ["-b"])
        self.assertTrue(intercepted)

    def test_older_or_edited_catalog_without_start_args_cannot_make_core_parameterless(self):
        disguised_core = self.folder / "qtlauncher" / "shadPS4.exe"
        disguised_core.parent.mkdir()
        disguised_core.write_bytes(windows_executable())
        for arguments in (None, []):
            for launcher_name in ("shadPS4QtLauncher.exe", "shadPS4.exe"):
                entry = {**self.entry, "launcher": {**self.entry["launcher"], "exe": launcher_name}}
                if arguments is None:
                    entry.pop("start_args", None)
                else:
                    entry["start_args"] = arguments
                with self.subTest(arguments=arguments, launcher_name=launcher_name):
                    command, note = build_emulator_command(entry, self.core)
                    self.assertEqual(command, [str(self.core), "-b"])
                    self.assertIn("Big-Picture", note)

    def test_standard_launcher_subfolder_precedes_flat_copy_and_ignores_unrelated_folders(self):
        self.service.register_manual(self.entry, self.folder)
        preferred = self.launcher()
        self.launcher("")
        self.launcher("Fremder Unterordner")
        self.assert_start(preferred, [])

    def test_flat_launcher_is_supported_and_a_failed_spawn_falls_back_to_big_picture(self):
        self.service.register_manual(self.entry, self.folder)
        qt = self.launcher("")
        self.assert_start(qt, [])
        with patch("core.installer.subprocess.Popen", side_effect=[OSError("Qt-Laufzeit fehlt"), Mock()]) as start:
            note = self.service.start(self.entry)
        self.assertEqual(start.call_args_list, [call([str(qt)], cwd=qt.parent, shell=False),
                                               call([str(self.core), "-b"], cwd=self.core.parent, shell=False)])
        self.assertIn("Big-Picture", note)
        self.assertIn("-b", note)

    def test_start_error_remains_readable_and_does_not_record_success(self):
        self.service.register_manual(self.entry, self.folder)
        with patch("core.installer.subprocess.Popen", side_effect=OSError("Zugriff verweigert")) as start:
            with self.assertRaisesRegex(HubError, "konnte nicht gestartet"):
                self.service.start(self.entry)
        self.assertEqual(start.call_args.args[0], [str(self.core), "-b"])
        self.assertEqual(self.service.settings.recent_emulators, [])

    def test_core_shortcut_includes_big_picture_parameter(self):
        desktop = self.root / "Desktop"
        with patch("core.shortcuts.shortcut_folders", return_value={"desktop": desktop}), patch(
            "core.shortcuts.subprocess.run", return_value=Mock(returncode=0)
        ) as run:
            paths = create_shortcuts(self.entry, self.core, {"desktop": True})
        script = base64.b64decode(run.call_args.args[0][-1]).decode("utf-16le")
        self.assertIn("$s.Arguments='-b'", script)
        self.assertIn(str(self.core), script)
        self.assertEqual(paths, [str(desktop / "Emulator Hub - shadps4.lnk")])

    def test_qtlauncher_shortcut_targets_the_gui_instead_of_parameterless_core(self):
        qt = self.launcher()
        desktop = self.root / "Desktop"
        with patch("core.shortcuts.shortcut_folders", return_value={"desktop": desktop}), patch(
            "core.shortcuts.subprocess.run", return_value=Mock(returncode=0)
        ) as run:
            create_shortcuts(self.entry, self.core, {"desktop": True})
        script = base64.b64decode(run.call_args.args[0][-1]).decode("utf-16le")
        self.assertIn(str(qt), script)
        self.assertNotIn("$s.TargetPath='" + str(self.core), script)

    def test_library_uses_documented_core_game_arguments_even_when_gui_is_available(self):
        self.service.register_manual(self.entry, self.folder)
        self.launcher()
        games = self.root / "Eigene Spiele"
        games.mkdir()
        eboot = games / "eboot.bin"
        original = b"nur synthetische eigene Testdatei"
        eboot.write_bytes(original)
        self.service.library.scan([games], Mock(), Mock(), threading.Event())
        game_id = self.service.library.games[0]["id"]
        self.service.library.set_console(game_id, "PlayStation 4")
        with patch("core.launch.subprocess.Popen") as start:
            self.service.launch_game(game_id, self.entry["id"])
        start.assert_called_once_with([str(self.core), "-g", str(eboot)], cwd=self.core.parent, shell=False)
        self.assertNotIn("-b", start.call_args.args[0])
        self.assertEqual(eboot.read_bytes(), original)
        self.assertTrue(self.service.library.get_game(game_id)["last_played"])

    def test_legacy_installation_cannot_be_installed_or_updated_and_keeps_user_data(self):
        self.service.register_manual(self.entry, self.folder)
        self.service.set_games_directory(self.entry, self.root / "Eigene Pakete")
        saved_settings = self.service.settings.path.read_bytes()
        saved_records = self.service.installed.copy()
        original_core = self.core.read_bytes()
        event = threading.Event()
        with patch.object(self.service.github, "latest") as latest, patch.object(self.service.policy, "get") as get:
            for operation in (
                lambda: self.service.prepare_install(self.entry),
                lambda: self.service.install(self.entry, Mock(), Mock(), event),
                lambda: self.service._install(self.entry, Mock(), Mock(), event, {}),
            ):
                with self.subTest(operation=operation), self.assertRaisesRegex(HubError, "Veraltet"):
                    operation()
            self.assertEqual(self.service.check_updates(Mock(), Mock(), event), {})
            result = self.service.update_all(Mock(), Mock(), event)
        self.assertEqual(result["updated"], [])
        self.assertIn("shadps4", result["skipped"])
        latest.assert_not_called()
        get.assert_not_called()
        self.assertEqual(self.service.installed, saved_records)
        self.assertEqual(self.service.settings.path.read_bytes(), saved_settings)
        self.assertEqual(self.core.read_bytes(), original_core)
        self.assert_start(self.core, ["-b"])
        self.assertEqual(list(self.service.emulator_dir.glob("_install_*")), [])
        self.assertEqual(list(self.service.emulator_dir.glob("_backup_*")), [])


if __name__ == "__main__":
    unittest.main()
