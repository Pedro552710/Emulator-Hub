from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from core.errors import HubError
from core.installer import HubService
from core.launch import build_launch_command, compatible_entries, launch_game
from tests.helpers import TemporaryDirectory, make_catalog, windows_executable


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog, self.entry = make_catalog(self.root)
        self.entry = self.catalog.by_id(self.entry["id"])
        self.entry["launch_args"] = ["{game}"]
        self.folder = self.root / "Emulator"
        self.folder.mkdir()
        self.exe = self.folder / "emulator.exe"
        self.exe.write_bytes(windows_executable())
        self.game = self.root / "Mein eigenes Spiel & Zeichen; $(test).nes"
        self.game.write_bytes(b"eigene Datei")
        self.service = HubService(self.catalog, self.root / "data")
        self.addCleanup(self.close_logger)
        self.service.register_manual(self.entry, self.folder)

    def close_logger(self):
        for handler in list(self.service.logger.handlers):
            handler.close()
            self.service.logger.removeHandler(handler)

    def test_path_with_spaces_and_metacharacters_is_one_literal_argument_without_shell(self):
        with patch("core.launch.subprocess.Popen") as start:
            process = launch_game(self.service, self.entry, self.game)
        start.assert_called_once_with([str(self.exe.resolve()), str(self.game.resolve())], cwd=self.folder, shell=False)
        self.assertIs(process, start.return_value)
        self.assertEqual(self.game.read_bytes(), b"eigene Datei")

    def test_profiles_are_selected_by_actual_executable_and_support_arcade_rompath(self):
        alternative = self.folder / "MAME.exe"
        self.entry["launch_profiles"] = {"mame.exe": ["-rompath", "{game_dir}", "{game_stem}"]}
        command = build_launch_command(self.entry, alternative, self.game)
        self.assertEqual(command, [str(alternative), "-rompath", str(self.game.parent), self.game.stem])

    def test_unknown_alternative_executable_does_not_reuse_primary_arguments(self):
        self.entry["launch_note"] = "Bitte einen eigenen Core auswählen."
        with self.assertRaisesRegex(HubError, "eigenen Core"):
            build_launch_command(self.entry, self.folder / "retroarch.exe", self.game)

    def test_bad_templates_or_no_game_placeholder_are_readable_errors(self):
        for args in (["{game.__class__}"], ["{game!r}"], ["{game:>20}"], ["{"], ["-v"], ["{game}\n"], "{game}", None):
            with self.subTest(args=args):
                self.entry["launch_args"] = args
                with self.assertRaises(HubError):
                    build_launch_command(self.entry, self.exe, self.game)

    def test_missing_game_uninstalled_or_outside_executable_does_not_spawn(self):
        with patch("core.launch.subprocess.Popen") as start:
            with self.assertRaisesRegex(HubError, "Spiel-Datei"):
                launch_game(self.service, self.entry, self.root / "fehlt.nes")
            record = self.service.installed.pop(self.entry["id"])
            with self.assertRaisesRegex(HubError, "installiert"):
                launch_game(self.service, self.entry, self.game)
            self.service.installed[self.entry["id"]] = record
            record["path"] = str(self.root / "anderer Ordner")
            with self.assertRaisesRegex(HubError, "außerhalb"):
                launch_game(self.service, self.entry, self.game)
        start.assert_not_called()

    def test_start_failure_is_readable_and_corrupt_executable_is_rejected(self):
        with patch("core.launch.subprocess.Popen", side_effect=OSError("Zugriff verweigert")), self.assertRaisesRegex(HubError, "Spiel konnte nicht gestartet"):
            launch_game(self.service, self.entry, self.game)
        self.exe.write_bytes(b"keine EXE")
        with patch("core.launch.subprocess.Popen") as start, self.assertRaisesRegex(HubError, "Windows-EXE"):
            launch_game(self.service, self.entry, self.game)
        start.assert_not_called()

    def test_catalog_formats_require_native_game_file_and_show_instructions(self):
        self.entry["launch_extensions"] = [".bin", ".elf", ".self"]
        self.entry["launch_note"] = "Bitte das entpackte eigene Spiel als EBOOT.BIN auswählen."
        with patch("core.launch.subprocess.Popen") as start, self.assertRaisesRegex(HubError, "EBOOT.BIN"):
            launch_game(self.service, self.entry, self.game)
        start.assert_not_called()
        native_game = self.root / "EBOOT.BIN"
        native_game.write_bytes(b"eigenes Spiel")
        self.assertEqual(build_launch_command(self.entry, self.exe, native_game), [str(self.exe), str(native_game)])

    def test_compatible_entries_use_catalog_console_or_explicit_supported_list(self):
        self.assertEqual(compatible_entries(self.catalog, "Testkonsole"), [self.entry])
        self.assertEqual(compatible_entries(self.catalog, "falsch"), [])
        self.entry["supported_consoles"] = ["Weitere Konsole"]
        self.assertEqual(compatible_entries(self.catalog, "Weitere Konsole"), [self.entry])


if __name__ == "__main__":
    unittest.main()
