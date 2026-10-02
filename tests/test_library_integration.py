"""Bibliothek und Hub-Service zusammen, ohne einen echten Prozess zu starten."""

from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

from core.catalog import Catalog
from core.errors import HubError
from core.installer import HubService
from core.library import LibraryStore
from tests.helpers import TemporaryDirectory, windows_executable


class LibraryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = Catalog()
        self.service = HubService(self.catalog, self.root / "data")
        self.addCleanup(self.close_logger)
        self.games = self.root / "Eigene Spiele"
        self.games.mkdir()
        self.game = self.games / "Mein Spiel.nes"
        self.game.write_bytes(b"eigene unveraenderte Datei")
        self.service.library.scan([self.games], Mock(), Mock(), threading.Event())
        self.game_id = self.service.library.games[0]["id"]

    def close_logger(self):
        for handler in list(self.service.logger.handlers):
            handler.close()
            self.service.logger.removeHandler(handler)

    def install_mesen(self):
        entry = self.catalog.by_id("mesen")
        entry["launch_args"] = ["{game}"]
        folder = self.root / "Eigener Emulator"
        folder.mkdir()
        exe = folder / entry["exe"]
        exe.write_bytes(windows_executable())
        self.service.register_manual(entry, folder)
        return exe

    def test_automatic_emulator_selection_records_actual_emulator_and_both_histories(self):
        exe = self.install_mesen()
        with patch("core.launch.subprocess.Popen") as launch:
            result = self.service.launch_game(self.game_id)
        launch.assert_called_once_with([str(exe), str(self.game)], cwd=exe.parent, shell=False)
        self.assertIs(result, launch.return_value)
        saved = LibraryStore(self.service.data_dir, self.catalog, self.service.settings).get_game(self.game_id)
        self.assertEqual(saved["emulator_id"], "mesen")
        self.assertTrue(saved["last_played"])
        self.assertEqual(self.service.settings.recent_emulators[0]["id"], "mesen")
        self.assertEqual(self.game.read_bytes(), b"eigene unveraenderte Datei")

    def test_wrong_console_emulator_is_rejected_before_process_or_metadata_change(self):
        self.install_mesen()
        with patch("core.launch.subprocess.Popen") as launch, self.assertRaisesRegex(HubError, "passt nicht"):
            self.service.launch_game(self.game_id, "mgba")
        launch.assert_not_called()
        self.assertEqual(self.service.library.get_game(self.game_id)["last_played"], "")
        self.assertEqual(self.service.settings.recent_emulators, [])

    def test_metadata_write_failure_after_success_reports_warning_and_keeps_process_result(self):
        self.install_mesen()
        with patch("core.launch.subprocess.Popen") as launch, patch(
            "core.library.write_json", side_effect=HubError("Datenträger ist voll")
        ), patch.object(self.service.logger, "warning") as warning:
            result = self.service.launch_game(self.game_id)
        launch.assert_called_once()
        self.assertIs(result, launch.return_value)
        self.assertIn("Spiel wurde gestartet", self.service.library.last_warning)
        self.assertIn("Datenträger ist voll", self.service.library.last_warning)
        self.assertEqual(self.service.library.get_game(self.game_id)["last_played"], "")
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
