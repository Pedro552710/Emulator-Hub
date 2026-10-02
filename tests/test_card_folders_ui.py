"""Native Kartenaktionen ohne Explorer- oder Fremdprozess-Start prüfen."""

from pathlib import Path
import unittest
from unittest.mock import Mock, call, patch

from PySide6.QtCore import QCoreApplication, QEvent, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from core.catalog import Catalog
from core.errors import HubError
from core.installer import HubService
from tests.helpers import TemporaryDirectory, windows_executable
from ui.window import MainWindow


class CardFolderUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog = Catalog()
        self.service = HubService(self.catalog, self.root / "data")
        self.documents_patch = patch("core.folders._windows_documents", return_value=self.root / "Dokumente")
        self.documents_patch.start()
        report = {"cpu_cores": 8, "ram_gb": 32, "gpu_score": 3}
        self.service.settings.set("system_report", report)
        self.service.system_report = report
        self.entry = self.catalog.by_id("ppsspp")
        self.window = MainWindow(self.service, self.catalog)
        self.window.show()
        self.window.select_page("all")
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        for handler in list(self.service.logger.handlers):
            handler.close()
            self.service.logger.removeHandler(handler)
        self.temp.cleanup()
        self.documents_patch.stop()

    def test_folder_buttons_follow_installation_and_both_card_variants_emit_actions(self):
        card = self.window.cards[self.entry["id"]]
        recent = self.window.recent_cards[self.entry["id"]]
        self.assertFalse(card.emulator_folder_button.isEnabled())
        self.assertEqual(card.emulator_folder_button.toolTip(), "Noch nicht installiert")
        self.assertTrue(card.games_folder_button.isEnabled())
        self.assertEqual(card.games_folder_button.toolTip(), "Spiele-Ordner öffnen")
        self.assertFalse(card.games_folder_button.icon().isNull())
        own = self.root / "Eigener Emulator"
        own.mkdir()
        (own / self.entry["exe"]).write_bytes(windows_executable())
        self.service.register_manual(self.entry, own)
        self.window.refresh()
        for current in (card, recent):
            self.assertTrue(current.emulator_folder_button.isEnabled())
            self.assertEqual(current.emulator_folder_button.toolTip(), "Emulator-Ordner öffnen")
        games = self.root / "Eigene Spiele"
        self.service.set_games_directory(self.entry, games)
        with patch("core.folders.os.startfile") as explorer:
            card.emulator_folder_button.click()
            recent.emulator_folder_button.click()
            card.games_folder_button.click()
            recent.games_folder_button.click()
        self.assertEqual(explorer.call_args_list, [call(str(own)), call(str(own)), call(str(games)), call(str(games))])
        self.assertTrue(games.is_dir())
        self.assertEqual(list(games.iterdir()), [])
        self.window.resize(1194, 880)
        QTest.qWait(250)
        self.assertEqual(self.window._columns, 2)
        self.assertLessEqual(card.games_folder_button.geometry().right(), card.width() - 20)
        for button in (card.install_button, card.start_button, card.uninstall_button):
            self.assertGreaterEqual(button.width(), button.sizeHint().width())

    def test_context_menu_changes_persisted_folder_and_resets_without_creating_it(self):
        chosen = self.root / "Eigene PSP-Spiele"
        chosen.mkdir()
        original = self.service.games_directory(self.entry)

        change, reset = object(), object()
        menu = Mock()
        menu.addAction.side_effect = [change, reset]
        menu.exec.return_value = change
        # QMenu.exec is a native overloaded descriptor; patch the menu factory
        # rather than leaving its native event loop waiting for a real click.
        with patch("ui.window.QMenu", return_value=menu), patch(
            "ui.window.QFileDialog.getExistingDirectory", return_value=str(chosen)
        ) as folder_dialog:
            self.window.cards[self.entry["id"]].games_folder_button.customContextMenuRequested.emit(QPoint(4, 4))
        self.assertEqual([call.args[0] for call in menu.addAction.call_args_list], ["Spiele-Ordner ändern…", "Auf Standard zurücksetzen"])
        folder_dialog.assert_called_once_with(self.window, "Spiele-Ordner ändern", str(original))
        self.assertEqual(self.service.games_directory(self.entry), chosen)
        self.assertEqual(self.service.settings.get("games_dir")[self.entry["id"]], str(chosen))
        menu = Mock()
        menu.addAction.side_effect = [change, reset]
        menu.exec.return_value = reset
        with patch("ui.window.QMenu", return_value=menu):
            self.window.show_games_folder_menu(self.entry, QPoint(4, 4))
        self.assertEqual(self.service.games_directory(self.entry), original)
        self.assertNotIn(self.entry["id"], self.service.settings.get("games_dir", {}))

    def test_open_error_is_readable_and_cancelled_folder_dialog_keeps_settings(self):
        own = self.root / "Eigener Emulator"
        own.mkdir()
        (own / self.entry["exe"]).write_bytes(windows_executable())
        self.service.register_manual(self.entry, own)
        self.window.refresh()
        own.rename(self.root / "Emulator verschoben")
        with patch("core.folders.os.startfile") as explorer, patch.object(self.window, "_message") as message:
            self.window.cards[self.entry["id"]].emulator_folder_button.click()
        explorer.assert_not_called()
        self.assertEqual(message.call_args.args[0], "Emulator-Ordner konnte nicht geöffnet werden")
        self.assertIn("existiert nicht mehr", message.call_args.args[1])
        self.window.refresh()
        self.assertFalse(self.window.cards[self.entry["id"]].emulator_folder_button.isEnabled())
        with patch.object(self.service, "open_games_folder", side_effect=HubError("Der Ordner ist nicht erreichbar.")), patch.object(
            self.window, "_message"
        ) as message:
            self.window.cards[self.entry["id"]].games_folder_button.click()
        message.assert_called_once_with("Spiele-Ordner konnte nicht geöffnet werden", "Der Ordner ist nicht erreichbar.", error=True)
        with patch("ui.window.QFileDialog.getExistingDirectory", return_value=""), patch.object(
            self.service, "set_games_directory"
        ) as save:
            self.window.change_games_folder(self.entry)
        save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
