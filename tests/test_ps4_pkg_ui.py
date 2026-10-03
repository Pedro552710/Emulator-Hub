"""PS4-Pakethilfe: native Aktionen ohne echte Downloads oder Fremdprozesse."""

from pathlib import Path
import threading
import time
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLabel

from core.catalog import Catalog
from core.installer import HubService
from core.library import PS4_PACKAGE_STATUS
from tests.helpers import TemporaryDirectory, windows_executable
from ui.window import MainWindow


class PS4PackageUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog = Catalog()
        self.entry = self.catalog.by_id("ps4-pkg-tool")
        self.service = HubService(self.catalog, self.root / "data")
        self.service.settings.set("show_hidden", True)  # PS4-Funktionen bleiben ausdrücklich testbar.
        self.service.settings.set("system_report", {"cpu_cores": 8, "ram_gb": 16, "gpu_score": 3})
        self.service.system_report = self.service.settings.get("system_report")
        self.network = patch.object(self.service.policy, "get", side_effect=AssertionError("Kein Netzwerk im UI-Test."))
        self.http = self.network.start()
        games = self.root / "Eigene Spiele & Ordner; $(test)"
        games.mkdir()
        self.package = games / "Eigenes Paket & Zeichen; $(test).pkg"
        self.package.write_bytes(b"synthetische unveraenderte Testdatei, kein echtes PKG")
        (games / "Alpha.nes").write_bytes(b"synthetische eigene Testdatei")
        self.service.library.scan([games], Mock(), Mock(), threading.Event())
        self.package_id = next(game["id"] for game in self.service.library.games if Path(game["path"]) == self.package)
        self.nes_id = next(game["id"] for game in self.service.library.games if game["name"] == "Alpha")
        self.window = MainWindow(self.service, self.catalog)
        self.window.show()
        self.window.select_page("library")
        self.app.processEvents()

    def tearDown(self):
        if self.window._couch_dialog is not None:
            self.window._couch_dialog.reject()
            self.app.processEvents()
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
        self.network.stop()
        self.temp.cleanup()

    def wait(self, condition):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            self.app.processEvents()
            if condition():
                return
            QTest.qWait(5)
        self.fail("Der Hintergrundauftrag wurde nicht rechtzeitig beendet.")

    def select_game(self, identifier):
        page = self.window.library_page
        for row in range(page.tree.topLevelItemCount()):
            group = page.tree.topLevelItem(row)
            for child in range(group.childCount()):
                item = group.child(child)
                if item.data(0, Qt.ItemDataRole.UserRole) == identifier:
                    page.tree.setCurrentItem(item)
                    return item
        self.fail("Die eigene Datei fehlt in der Bibliotheksansicht.")

    def release(self):
        name = "PS4-PKG-Tool-v1.8.0.zip"
        return {"tag_name": "v1.8.0", "prerelease": False, "draft": False,
                "assets": [{"name": name, "size": 512, "digest": "sha256:" + "a" * 64,
                            "browser_download_url": "https://github.com/pearlxcore/PS4PKGTool/releases/download/v1.8.0/" + name}]}

    def test_list_grid_context_and_double_click_offer_package_help_without_game_start(self):
        page = self.window.library_page
        page.launchRequested.disconnect()
        page.packageInstallRequested.disconnect()
        game_start, package_open = Mock(), Mock()
        page.launchRequested.connect(game_start)
        page.packageInstallRequested.connect(package_open)
        item = self.select_game(self.package_id)
        self.assertEqual(item.text(4), PS4_PACKAGE_STATUS)
        self.assertNotIn("Bereit", item.text(4))
        self.assertFalse(page.launch_button.isEnabled())
        self.assertTrue(page.package_install_button.isVisible())
        self.assertTrue(page.package_install_button.isEnabled())
        self.assertIn("PKG Viewer", page.package_help.text())
        self.assertIn("Hauptfenster", page.package_help.text())
        page.package_install_button.click()
        page.tree.itemDoubleClicked.emit(item, 0)
        page.view_mode.setCurrentIndex(page.view_mode.findData("grid"))
        tile = page.grid.currentItem()
        self.assertEqual(tile.data(Qt.ItemDataRole.UserRole), self.package_id)
        self.assertIn(PS4_PACKAGE_STATUS, tile.text())
        self.assertNotIn("Bereit", tile.toolTip())
        self.assertFalse(page.launch_button.isEnabled())
        page.grid.itemDoubleClicked.emit(tile)
        menu = Mock()
        with patch("ui.library.QMenu", return_value=menu):
            page._context_menu(page.grid, page.grid.visualItemRect(tile).center())
        actions = {call.args[0]: call.args[1] for call in menu.addAction.call_args_list}
        self.assertNotIn("Spiel starten", actions)
        actions["Im PS4 PKG Tool installieren"]()
        self.assertEqual(package_open.call_count, 4)
        self.assertTrue(all(call.args == (self.package_id,) for call in package_open.call_args_list))
        game_start.assert_not_called()
        page.set_busy(True)
        page.grid.itemDoubleClicked.emit(tile)
        self.assertFalse(page.package_install_button.isEnabled())
        self.assertEqual(package_open.call_count, 4)

    def test_scanning_and_declining_missing_tool_never_prepare_or_download_it(self):
        self.http.assert_not_called()
        self.assertNotIn(self.entry["id"], self.service.installed)
        self.assertFalse((self.service.emulator_dir / self.entry["id"]).exists())
        item = self.select_game(self.package_id)
        self.assertEqual(item.text(4), PS4_PACKAGE_STATUS)

        def cancel(box):
            return next(button for button in box.buttons() if button.text() == "Abbrechen")

        with patch("ui.window.QMessageBox.exec", return_value=0), patch(
            "ui.window.QMessageBox.clickedButton", new=cancel
        ), patch.object(self.service, "prepare_install") as prepare, patch.object(
            self.service, "install"
        ) as install, patch.object(self.service, "_download") as download:
            self.window.library_page.package_install_button.click()
        prepare.assert_not_called()
        install.assert_not_called()
        download.assert_not_called()
        self.http.assert_not_called()
        self.assertEqual(self.service.library.get_game(self.package_id)["last_played"], "")

    def test_accepting_missing_tool_routes_only_explicit_install_action(self):
        def choose_install(box):
            return next(button for button in box.buttons() if button.text() == "PS4 PKG Tool installieren")

        with patch("ui.window.QMessageBox.exec", return_value=0), patch(
            "ui.window.QMessageBox.clickedButton", new=choose_install
        ), patch.object(self.window, "install") as install, patch("core.launch.subprocess.Popen") as process:
            self.window.install_ps4_package(self.package_id)
        install.assert_called_once_with(self.entry)
        process.assert_not_called()
        self.http.assert_not_called()

    def test_installed_tool_receives_one_literal_package_path_without_shell_or_game_history(self):
        folder = self.root / "Eigenes Hilfsprogramm & Ordner"
        folder.mkdir()
        executable = folder / self.entry["exe"]
        executable.write_bytes(windows_executable())
        self.service.register_manual(self.entry, folder)
        history = self.service.settings.get("recent_emulators", [])
        with patch("core.launch.subprocess.Popen") as start, patch.object(self.service, "launch_game") as game_start:
            self.window.install_ps4_package(self.package_id)
        start.assert_called_once_with([str(executable), str(self.package)], cwd=folder, shell=False)
        game_start.assert_not_called()
        self.assertEqual(self.service.library.get_game(self.package_id)["last_played"], "")
        self.assertEqual(self.service.settings.get("recent_emulators", []), history)
        self.assertEqual(self.package.read_bytes(), b"synthetische unveraenderte Testdatei, kein echtes PKG")
        self.assertIn("PKG Viewer", self.window.notice_label.text())
        self.assertIn("Hauptfenster", self.window.notice_label.text())

    def test_rejected_download_notice_shows_reviewed_source_and_checksum_without_download(self):
        reviewed, worker_threads = [], []
        original_prepare = self.service.prepare_install

        def prepare(entry):
            worker_threads.append(threading.get_ident())
            return original_prepare(entry)

        def reject(dialog):
            reviewed.append("\n".join(label.text() for label in dialog.findChildren(QLabel)))
            return QDialog.DialogCode.Rejected

        with patch.object(self.service.github, "latest", return_value=self.release()), patch.object(
            self.service, "prepare_install", side_effect=prepare
        ) as prepare_call, patch.object(self.service, "install") as install, patch.object(
            self.service, "_download"
        ) as download, patch("ui.window.ShortcutDialog.exec", new=reject):
            self.window.install(self.entry)
            self.wait(lambda: self.window.worker is None and bool(reviewed))
        prepare_call.assert_called_once_with(self.entry)
        self.assertNotEqual(worker_threads[0], threading.get_ident())
        self.assertIn(self.release()["assets"][0]["browser_download_url"], reviewed[0])
        self.assertIn("SHA-256", reviewed[0])
        self.assertIn("a" * 64, reviewed[0])
        self.assertIn("Drittprogramm", reviewed[0])
        self.assertIn("Antivirus", reviewed[0])
        self.assertIn("unsignierten", reviewed[0])
        install.assert_not_called()
        download.assert_not_called()
        self.http.assert_not_called()

    def test_confirmed_download_passes_exact_reviewed_preview_to_background_installer(self):
        previews, reviewed = [], []
        original_prepare = self.service.prepare_install

        def prepare(entry):
            preview = original_prepare(entry)
            previews.append(preview)
            return preview

        def accept(dialog):
            reviewed.append("\n".join(label.text() for label in dialog.findChildren(QLabel)))
            return QDialog.DialogCode.Accepted

        with patch.object(self.service.github, "latest", return_value=self.release()), patch.object(
            self.service, "prepare_install", side_effect=prepare
        ), patch.object(self.service, "install", return_value={}) as install, patch.object(
            self.service, "_download"
        ) as download, patch("ui.window.ShortcutDialog.exec", new=accept):
            self.window.install(self.entry)
            self.wait(lambda: self.window.worker is None and install.called)
        install.assert_called_once()
        self.assertIs(install.call_args.args[0], self.entry)
        self.assertIs(install.call_args.kwargs["preview"], previews[0])
        self.assertEqual(install.call_args.kwargs["shortcuts"], {"desktop": False, "startmenu": True})
        self.assertIn(previews[0].source, reviewed[0])
        self.assertIn(previews[0].sha256, reviewed[0])
        download.assert_not_called()  # Der Installer ist hier simuliert; kein Binärdownload im UI-Test.
        self.http.assert_not_called()

    def test_utility_card_is_distinct_and_existing_game_actions_remain_available(self):
        self.window.select_page("all")
        card = self.window.cards[self.entry["id"]]
        texts = " ".join(label.text() for label in card.findChildren(QLabel))
        self.assertIn("Hilfsprogramm", texts)
        self.assertIn("kein Emulator", texts)
        self.assertIn("ausdrücklichem Klick", texts)
        self.assertFalse(card.games_folder_button.isHidden())
        self.assertEqual(card.games_folder_button.text(), "Ordner für Spiele-PKGs öffnen")
        self.assertEqual(card.start_button.text(), "PS4 einrichten")
        self.assertTrue(card.install_button.isHidden())
        self.assertEqual(len(card.setup_steps_label.text().splitlines()), 5)
        self.assertTrue(card.profiles_button.isHidden())
        legacy = self.window.cards["mesen"]
        self.assertFalse(legacy.games_folder_button.isHidden())
        self.assertFalse(legacy.profiles_button.isHidden())
        self.assertEqual(legacy.games_folder_button.toolTip(), "Spiele-Ordner öffnen")
        self.window.select_page("library")
        page = self.window.library_page
        item = self.select_game(self.nes_id)
        self.assertEqual(item.text(4), "Bereit")
        self.assertTrue(page.launch_button.isEnabled())
        self.assertFalse(page.package_install_button.isVisible())
        page.launchRequested.disconnect()
        page.packageInstallRequested.disconnect()
        launch, package = Mock(), Mock()
        page.launchRequested.connect(launch)
        page.packageInstallRequested.connect(package)
        page.tree.itemDoubleClicked.emit(item, 0)
        launch.assert_called_once_with(self.nes_id)
        package.assert_not_called()

    def test_couch_package_tile_explains_installation_and_never_emits_game_start(self):
        self.window.show_couch()
        couch = self.window._couch_dialog
        couch.launchRequested.disconnect()
        couch.packageInstallRequested.disconnect()
        launch, package = Mock(), Mock()
        couch.launchRequested.connect(launch)
        couch.packageInstallRequested.connect(package)
        couch._show_games("PlayStation 4")
        self.app.processEvents()
        self.assertEqual(len(couch._tiles), 1)
        self.assertIn(PS4_PACKAGE_STATUS, couch._tiles[0].toolTip())
        QTest.keyClick(couch._tiles[0], Qt.Key.Key_Return)
        self.app.processEvents()
        package.assert_called_once_with(self.package_id)
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
