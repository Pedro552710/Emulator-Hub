"""Neue native Seiten bleiben mit der vorhandenen Startlogik verbunden."""
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from core.catalog import Catalog
from core.installer import HubService
from tests.helpers import TemporaryDirectory, windows_executable
from ui.window import MainWindow


class ComfortIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.service = HubService(Catalog(), self.root / "data")
        self.service.settings.set("system_report", {"cpu_cores": 8, "ram_gb": 16, "gpu_score": 3})
        games = self.root / "Spiele"
        games.mkdir()
        (games / "Alpha.nes").write_bytes(b"eigene Datei")
        self.service.library.scan([games], Mock(), Mock(), threading.Event())
        self.game = self.service.library.games[0]
        entry = self.service.catalog.by_id("mesen")
        emulator = self.root / "Emulator"
        emulator.mkdir()
        (emulator / entry["exe"]).write_bytes(windows_executable())
        self.service.register_manual(entry, emulator)
        self.window = MainWindow(self.service, self.service.catalog)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        if self.window._couch_dialog:
            self.window._couch_dialog.reject()
            self.app.processEvents()
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        for handler in list(self.service.logger.handlers):
            handler.close()
            self.service.logger.removeHandler(handler)
        self.temp.cleanup()

    def test_fullscreen_button_keyboard_launch_reuses_existing_service_and_escape_restores_window(self):
        with patch.object(self.service, "launch_game") as launch:
            self.window.couch_button.click()
            couch = self.window._couch_dialog
            self.app.processEvents()
            self.assertTrue(couch.isFullScreen())
            QTest.keyClick(couch._tiles[0], Qt.Key.Key_Return)
            self.app.processEvents()
            self.assertEqual(couch._page, "games")
            QTest.keyClick(couch._tiles[0], Qt.Key.Key_Return)
            self.app.processEvents()
            launch.assert_called_once_with(self.game["id"], "mesen")
            QTest.keyClick(couch, Qt.Key.Key_Escape)
            self.app.processEvents()
        self.assertIsNone(self.window._couch_dialog)
        self.assertTrue(self.window.isVisible())
        self.assertEqual(Path(self.game["path"]).read_bytes(), b"eigene Datei")

    def test_controller_button_opens_assistant_without_background_jobs_or_config_writes(self):
        with patch("ui.window.ControllerDialog.exec", return_value=QDialog.DialogCode.Rejected) as show:
            self.window.controller_button.click()
        show.assert_called_once()
        self.assertIsNone(self.window.worker)
        self.assertFalse((self.service.data_dir / "controller-backups").exists())

    def test_closing_main_window_closes_couch_and_does_not_reopen_normal_window(self):
        self.window.show_couch()
        self.app.processEvents()
        self.window.close()
        self.app.processEvents()
        self.assertIsNone(self.window._couch_dialog)
        self.assertFalse(self.window.isVisible())

    def test_catalog_controller_modes_and_excel_enrichment_stay_reproducible(self):
        from tools.import_catalog import import_workbook
        from core.controllers import CONTROLLER_GUIDES
        self.assertEqual(len(CONTROLLER_GUIDES), len(self.service.catalog.items))
        for entry in self.service.catalog.items:
            self.assertEqual(entry["controller_config"], "auto" if entry["id"] == "dolphin" else "manuell")
            self.assertTrue(entry["controller_manual"])
        project = Path(__file__).resolve().parents[1]
        output = self.root / "fresh-catalog.json"
        import_workbook(project / "docs/emulatoren_mit_downloadanleitungen.xlsx", output, project / "tools/catalog_enrichment.json")
        self.assertEqual(Catalog(output).items, self.service.catalog.items)
