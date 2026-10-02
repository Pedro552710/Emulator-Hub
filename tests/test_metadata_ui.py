"""Cover-Oberfläche ohne Accounts, Netzwerk oder Änderungen an Spiel-Dateien."""
from pathlib import Path
import threading
import time
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit, QPlainTextEdit

from core.catalog import Catalog
from core.installer import HubService
from ui.metadata import CandidateDialog, GameDetailsDialog
from ui.window import MainWindow
from tests.helpers import TemporaryDirectory


class MetadataUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog = Catalog()
        self.service = HubService(self.catalog, self.root / "data")
        self.service.settings.set("system_report", {"cpu_cores": 8, "ram_gb": 16, "gpu_score": 3})
        games = self.root / "Eigene Spiele"
        games.mkdir()
        self.original = b"eigene unveraenderte Testdatei"
        (games / "Alpha.nes").write_bytes(self.original)
        self.service.library.scan([games], Mock(), Mock(), threading.Event())
        self.game = self.service.library.games[0]
        self.cached = {}
        self.service.metadata = Mock()
        self.service.metadata.get.side_effect = lambda identifier: self.cached.get(identifier)
        self.window = MainWindow(self.service, self.catalog)
        self.window.show()
        self.window.select_page("library")
        self.app.processEvents()

    def tearDown(self):
        if self.window.worker is not None:
            self.window.worker.cancel()
            self.window.worker.wait(3000)
            self.app.processEvents()
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        for handler in list(self.service.logger.handlers):
            handler.close()
            self.service.logger.removeHandler(handler)
        self.temp.cleanup()

    def wait(self, condition):
        end = time.monotonic() + 4
        while time.monotonic() < end:
            self.app.processEvents()
            if condition():
                return
            QTest.qWait(5)
        self.fail("Hintergrundauftrag wurde nicht rechtzeitig beendet.")

    def test_cached_title_grid_details_and_source_work_without_requests(self):
        self.cached[self.game["id"]] = {"title": "Eigener bestätigter Titel", "year": 1990, "genres": ["Abenteuer"],
                                         "description": "<b>Text bleibt Text</b>", "source": "IGDB"}
        page = self.window.library_page
        page.search.setText("bestätigter")
        self.assertEqual(len(page.visible_games), 1)
        self.assertEqual(page.grid.count(), 1)
        page.view_mode.setCurrentIndex(1)
        page.grid.setCurrentRow(0)
        self.assertEqual(page.selected_game_id(), self.game["id"])
        self.assertFalse(page.grid.item(0).icon().isNull())
        dialog = GameDetailsDialog(self.service, self.game)
        self.assertIn("<b>", dialog.findChild(QPlainTextEdit).toPlainText())
        self.service.metadata.search.assert_not_called()
        self.assertEqual(Path(self.game["path"]).read_bytes(), self.original)

    def test_credentials_secrets_masked_and_saved_in_background_only_on_click(self):
        panel = self.window.settings_page.cover_panel
        panel.fields["igdb"]["client_id"].setText("eigene-id")
        panel.fields["igdb"]["client_secret"].setText("eigenes-test-secret")
        self.assertEqual(panel.fields["igdb"]["client_secret"].echoMode(), QLineEdit.EchoMode.Password)
        self.service.metadata.save_credentials.assert_not_called()
        entered = []
        self.service.metadata.save_credentials.side_effect = lambda *args: entered.append(threading.get_ident())
        panel.save_button.click()
        self.wait(lambda: self.window.worker is None)
        self.service.metadata.save_credentials.assert_called_once_with("igdb", {"client_id": "eigene-id", "client_secret": "eigenes-test-secret"})
        self.assertNotEqual(entered[0], threading.get_ident())
        self.assertNotIn("eigenes-test-secret", self.service.settings.path.read_text(encoding="utf-8"))
        self.assertFalse(any("eigenes-test-secret" in line for line in self.window._log_lines))

    def test_uncertain_candidate_requires_selection_and_skip_never_downloads_cover(self):
        candidate = {"id": "1", "title": "Alpha ähnlich", "source": "IGDB", "provider": "igdb", "requires_confirmation": True}
        self.service.metadata.search.return_value = [candidate]
        with patch("ui.window.CandidateDialog.exec", return_value=QDialog.DialogCode.Rejected) as dialog:
            self.window.load_game_metadata(self.game["id"])
            self.wait(lambda: self.window.worker is None and dialog.called)
        self.service.metadata.choose.assert_not_called()
        self.assertEqual(Path(self.game["path"]).read_bytes(), self.original)
        actual = CandidateDialog(self.game, [candidate])
        self.assertFalse(actual.choose_button.isEnabled())
        actual.results.setCurrentRow(0)
        self.assertTrue(actual.choose_button.isEnabled())
        self.assertEqual(actual.candidate, candidate)

    def test_safe_match_saved_then_cache_skips_further_requests(self):
        candidate = {"id": "1", "title": "Alpha", "source": "IGDB", "provider": "igdb", "requires_confirmation": False}
        self.service.metadata.search.return_value = [candidate]
        self.service.metadata.choose.side_effect = lambda identifier, selected, *args: self.cached.setdefault(identifier, selected)
        self.window.load_game_metadata()
        self.wait(lambda: self.window.worker is None)
        self.assertEqual(self.service.metadata.choose.call_count, 1)
        self.window.load_game_metadata()
        self.assertEqual(self.service.metadata.search.call_count, 1)
        self.assertEqual(Path(self.game["path"]).read_bytes(), self.original)

    def test_cache_clear_requires_confirmation_and_runs_in_worker(self):
        with patch("ui.window.QMessageBox.exec", return_value=0), patch("ui.window.QMessageBox.clickedButton", return_value=None):
            self.window.clear_metadata_cache()
        self.service.metadata.clear_cache.assert_not_called()
        with patch("ui.window.QMessageBox.exec", return_value=0), patch("ui.window.QMessageBox.clickedButton", new=lambda box: next(b for b in box.buttons() if b.text() == "Cache leeren")):
            self.window.clear_metadata_cache()
            self.wait(lambda: self.window.worker is None)
        self.service.metadata.clear_cache.assert_called_once()

    def test_connection_with_empty_form_uses_saved_credentials_and_never_deletes_them(self):
        panel = self.window.settings_page.cover_panel
        panel.test_button.click()
        self.wait(lambda: self.window.worker is None)
        self.service.metadata.save_credentials.assert_not_called()
        self.service.metadata.test_connection.assert_called_once()
        self.assertIn("erfolgreich", panel.result_label.text())

    def test_failed_initial_authentication_stops_batch_without_repeating_it_per_game(self):
        from core.errors import HubError
        self.service.metadata.test_connection.side_effect = HubError("Bitte Zugangsdaten eintragen.")
        with patch("ui.window.QMessageBox.exec", return_value=0):
            self.window.load_game_metadata()
            self.wait(lambda: self.window.worker is None)
        self.service.metadata.test_connection.assert_called_once()
        self.service.metadata.search.assert_not_called()
        self.assertIn("Zugangsdaten", self.window.notice_label.text())
