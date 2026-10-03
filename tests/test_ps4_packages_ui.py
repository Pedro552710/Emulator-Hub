"""PS4-Pakete sind in allen Ansichten Hilfseinträge statt Spielstarts."""

from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication, QDialog

from core.catalog import Catalog, CatalogError
from core.errors import Cancelled
from core.installer import HubService
from core.library import PS4_PACKAGE_STATUS
from tests.helpers import TemporaryDirectory, windows_executable
from ui.couch import CouchDialog
from ui.dialogs import ShortcutDialog
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
        self.helper = self.catalog.by_id("ps4-pkg-tool")
        self.service = HubService(self.catalog, self.root / "data")
        self.service.settings.set("show_hidden", True)  # PS4-Funktionen bleiben ausdrücklich testbar.
        report = {"cpu_cores": 8, "ram_gb": 16, "gpu_score": 3}
        self.service.settings.set("system_report", report)
        self.service.system_report = report
        self.games = self.root / "Eigene Dateien & Zeichen; $(test)"
        self.games.mkdir()
        self.package = self.games / "Eigenes Update & Zeichen; $(test).PKG"
        self.package.write_bytes(b"synthetischer Platzhalter")
        self.service.library.scan([self.games], Mock(), Mock(), threading.Event())
        self.identifier = self.service.library.games[0]["id"]
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

    def select_package(self):
        page = self.window.library_page
        item = page.tree.topLevelItem(0).child(0)
        self.assertEqual(item.data(0, Qt.ItemDataRole.UserRole), self.identifier)
        page.tree.setCurrentItem(item)
        return item

    def test_list_and_grid_show_installation_status_and_disable_game_start(self):
        page = self.window.library_page
        item = self.select_package()
        self.assertEqual(item.text(4), PS4_PACKAGE_STATUS)
        self.assertFalse(page.launch_button.isEnabled())
        self.assertFalse(page.assign_button.isEnabled())
        self.assertTrue(page.package_install_button.isVisible())
        self.assertTrue(page.package_install_button.isEnabled())
        self.assertIn("PKG Viewer", page.package_help.text())
        self.assertIn("Hauptfenster", page.package_help.text())
        self.assertIn("Im PS4 PKG Tool installieren", page.package_help.text())
        self.assertIn("Nur eigene Spiele", page.package_help.text())
        self.assertNotIn("Game Install Directory", page.package_help.text())
        page.view_mode.setCurrentIndex(page.view_mode.findData("grid"))
        self.assertIn(PS4_PACKAGE_STATUS, page.grid.item(0).text())
        self.assertFalse(page.launch_button.isEnabled())

    def test_double_click_in_both_views_routes_only_to_package_action(self):
        page = self.window.library_page
        item = self.select_package()
        page.packageInstallRequested.disconnect(self.window.install_ps4_package)
        page.launchRequested.disconnect(self.window.launch_game)
        packages, launches = [], []
        page.packageInstallRequested.connect(packages.append)
        page.launchRequested.connect(launches.append)
        page._double_clicked(item, 0)
        page.view_mode.setCurrentIndex(page.view_mode.findData("grid"))
        page.grid.itemDoubleClicked.emit(page.grid.item(0))
        self.assertEqual(packages, [self.identifier, self.identifier])
        self.assertEqual(launches, [])
        with patch.object(self.window, "install_ps4_package") as install, patch.object(self.service, "launch_game") as launch:
            self.window.launch_game(self.identifier)
        install.assert_called_once_with(self.identifier)
        launch.assert_not_called()

    def test_couch_tile_shows_package_status_and_routes_to_package_action(self):
        dialog = CouchDialog(self.service, backend=Mock())
        try:
            dialog._show_games("PlayStation 4")
            packages, launches = [], []
            dialog.packageInstallRequested.connect(packages.append)
            dialog.launchRequested.connect(launches.append)
            self.assertEqual(dialog._tiles[0].subtitle, PS4_PACKAGE_STATUS)
            dialog._tiles[0].click()
            self.assertEqual(packages, [self.identifier])
            self.assertEqual(launches, [])
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_missing_tool_offers_installation_and_cancel_downloads_nothing(self):
        with patch("ui.window.QMessageBox.exec", return_value=0), patch(
            "ui.window.QMessageBox.clickedButton", return_value=None
        ), patch.object(self.window, "install") as install, patch.object(self.service, "prepare_install") as prepare:
            self.window.install_ps4_package(self.identifier)
        install.assert_not_called()
        prepare.assert_not_called()

        def clicked_install(box):
            return next(button for button in box.buttons() if button.text() == "PS4 PKG Tool installieren")

        with patch("ui.window.QMessageBox.exec", return_value=0), patch(
            "ui.window.QMessageBox.clickedButton", new=clicked_install
        ), patch.object(self.window, "install") as install:
            self.window.install_ps4_package(self.identifier)
        install.assert_called_once_with(self.helper)

    def test_older_catalog_without_helper_reports_a_readable_hint(self):
        with patch.object(self.catalog, "by_id", side_effect=CatalogError("fehlt")), patch.object(
            self.window, "_notify"
        ) as notify:
            self.window.install_ps4_package(self.identifier)
        self.assertIn("fehlt im Katalog", notify.call_args.args[0])

    def test_scan_works_with_only_an_explicit_ps4_folder_mapping(self):
        self.service.set_games_directory(self.catalog.by_id("shadps4"), self.games)
        self.assertEqual(self.window.settings_page.roots(), [])
        with patch.object(self.window, "_run_job") as job:
            self.window.scan_library()
        operation = job.call_args.args[1]
        result = operation(Mock(), Mock(), threading.Event())
        self.assertEqual(result["total"], 1)
        self.assertEqual(self.service.library.games[0]["path"], str(self.package))

    def test_release_preview_cancellation_never_opens_download_confirmation(self):
        with patch.object(self.window, "_run_job") as job:
            self.window.install(self.helper)
        operation, completion = job.call_args.args[1:3]
        event = threading.Event()
        event.set()
        with patch.object(self.service, "prepare_install") as prepare, self.assertRaises(Cancelled):
            operation(Mock(), Mock(), event)
        prepare.assert_not_called()
        event.clear()
        with patch.object(self.service, "prepare_install", side_effect=lambda entry: event.set()), self.assertRaises(Cancelled):
            operation(Mock(), Mock(), event)
        self.window.worker = Mock(cancel_event=event)
        try:
            completion(Mock())
            self.assertIsNone(self.window._after_job)
        finally:
            self.window.worker = None

    def test_helper_is_excluded_from_controller_emulator_selection(self):
        self.catalog.by_id("shadps4")["hidden"] = False  # Original deprecated-entry behavior.
        from ui.controllers import ControllerDialog
        dialog = ControllerDialog(self.service, backend=Mock(poll=Mock(return_value=[]), unavailable_reason=""))
        try:
            self.assertEqual(dialog.emulator_combo.findData("ps4-pkg-tool"), -1)
            self.assertEqual(dialog.emulator_combo.findData("shadps4"), -1)
        finally:
            dialog.close()
            dialog.deleteLater()

    def test_installed_tool_receives_exact_path_without_shell_and_keeps_history(self):
        folder = self.root / "Hilfsprogramm mit Leerzeichen"
        folder.mkdir()
        executable = folder / self.helper["exe"]
        executable.write_bytes(windows_executable())
        self.service.register_manual(self.helper, folder)
        before = self.service.library.get_game(self.identifier)
        with patch("core.launch.subprocess.Popen") as process:
            self.window.install_ps4_package(self.identifier)
        process.assert_called_once_with([str(executable), str(self.package)], cwd=folder, shell=False)
        self.assertEqual(self.service.library.get_game(self.identifier), before)

    def test_download_hint_is_shown_before_confirmed_install_and_cancel_is_safe(self):
        preview = Mock(notice="Drittprogramm\nQuelle: offizielle Quelle\nSHA-256: Testwert\nAntivirus")
        with patch("ui.window.ShortcutDialog") as dialog_type, patch.object(self.window, "_run_job") as job:
            dialog_type.return_value.exec.return_value = QDialog.DialogCode.Rejected
            self.window._confirm_utility_install(self.helper, preview)
        dialog_type.assert_called_once_with(self.helper, self.window, download_notice=preview.notice)
        job.assert_not_called()

        with patch("ui.window.ShortcutDialog") as dialog_type, patch.object(self.window, "_run_job") as job:
            dialog_type.return_value.exec.return_value = QDialog.DialogCode.Accepted
            dialog_type.return_value.shortcuts = {}
            self.window._confirm_utility_install(self.helper, preview)
            operation = job.call_args.args[1]
            with patch.object(self.service, "install") as install:
                progress, log, event = Mock(), Mock(), threading.Event()
                operation(progress, log, event)
        install.assert_called_once_with(self.helper, progress, log, event, shortcuts={}, preview=preview)

        dialog = ShortcutDialog(self.helper, download_notice=preview.notice)
        try:
            from PySide6.QtWidgets import QLabel
            self.assertTrue(any(widget.text() == preview.notice for widget in dialog.findChildren(QLabel)))
        finally:
            dialog.deleteLater()

    def test_ps4_setup_button_offers_confirmed_tool_install_then_starts_main_window(self):
        self.window.select_page("all")
        card = self.window.cards["ps4-pkg-tool"]
        self.assertTrue(card.start_button.isEnabled())
        self.assertEqual(card.start_button.text(), "PS4 einrichten")
        self.assertTrue(card.install_button.isHidden())
        self.assertEqual(card.setup_steps_label.text().splitlines(), [
            f"{number}) {step}" for number, step in enumerate(self.helper["ps4_setup_steps"], 1)
        ])
        with patch.object(self.window, "install") as install, patch("core.installer.subprocess.Popen") as process:
            card.start_button.click()
        install.assert_called_once_with(self.helper)
        process.assert_not_called()
        folder = self.root / "Tool & Sonderzeichen; $(test)"
        folder.mkdir()
        executable = folder / self.helper["exe"]
        executable.write_bytes(windows_executable())
        self.service.register_manual(self.helper, folder)
        self.window.refresh()
        with patch.object(self.window, "install") as install, patch("core.installer.subprocess.Popen") as process:
            card.start_button.click()
        install.assert_not_called()
        process.assert_called_once_with([str(executable)], cwd=folder, shell=False)
        self.assertEqual(self.service.settings.recent_emulators, [])

    def test_pkg_folder_button_opens_user_folder_and_scan_keeps_packages_only(self):
        self.window.select_page("all")
        card = self.window.cards["ps4-pkg-tool"]
        self.assertFalse(card.games_folder_button.isHidden())
        self.assertEqual(card.games_folder_button.text(), "Ordner für Spiele-PKGs öffnen")
        self.service.set_games_directory(self.helper, self.games)
        (self.games / "unrelated.nes").write_bytes(b"synthetic file")
        with patch("core.folders.open_directory") as open_folder:
            card.games_folder_button.click()
        open_folder.assert_called_once_with(self.games)
        with patch.object(self.window, "_run_job") as job:
            self.window.scan_library()
        result = job.call_args.args[1](Mock(), Mock(), threading.Event())
        self.assertEqual(result["total"], 1)
        self.assertEqual(self.service.library.games[0]["path"], str(self.package))
        self.assertEqual(self.package.read_bytes(), b"synthetischer Platzhalter")

    def test_shadps4_card_is_hidden_until_old_installation_and_remains_startable(self):
        # hidden=false restores the original deprecated-entry presentation.
        self.catalog.by_id("shadps4")["hidden"] = False
        self.window.refresh()
        self.window.select_page("all")
        legacy_card = self.window.cards["shadps4"]
        self.assertTrue(legacy_card.isHidden())
        self.assertNotIn("shadps4", [entry["id"] for entry in self.window.visible_entries])
        folder = self.root / "Vorhandene PS4-Installation"
        folder.mkdir()
        core = folder / "shadPS4.exe"
        core.write_bytes(windows_executable())
        old_entry = self.catalog.by_id("shadps4")
        self.service.register_manual(old_entry, folder)
        self.service.settings.toggle_favorite("shadps4")
        settings = self.service.settings.path.read_bytes()
        records = self.service.installed.copy()
        self.window.refresh()
        self.assertFalse(legacy_card.isHidden())
        self.assertTrue(legacy_card.install_button.isHidden())
        self.assertFalse(legacy_card.install_button.isEnabled())
        self.assertTrue(legacy_card.manual_button.isHidden())
        from PySide6.QtWidgets import QLabel
        texts = " ".join(widget.text() for widget in legacy_card.findChildren(QLabel))
        self.assertIn("Veraltet", texts)
        self.assertNotIn("-b", texts)
        self.assertNotIn("Version Manager", texts)
        self.assertEqual(self.service.settings.path.read_bytes(), settings)
        self.assertEqual(self.service.installed, records)
        with patch("core.installer.subprocess.Popen") as process:
            legacy_card.start_button.click()
        process.assert_called_once_with([str(core), "-b"], cwd=folder, shell=False)
        self.assertTrue(core.is_file())

    def test_native_ps4_file_without_legacy_installation_does_not_offer_shadps4_download(self):
        self.catalog.by_id("shadps4")["hidden"] = False
        native = self.games / "eboot.bin"
        native.write_bytes(b"synthetic native game placeholder")
        self.service.library.scan([self.games], Mock(), Mock(), threading.Event())
        identifier = next(game["id"] for game in self.service.library.games if Path(game["path"]) == native)
        self.service.library.set_console(identifier, "PlayStation 4")
        with patch("ui.window.QMessageBox.exec") as dialog, patch.object(self.window, "install") as install, patch.object(self.service, "launch_game") as launch:
            self.window.launch_game(identifier)
        dialog.assert_not_called()
        install.assert_not_called()
        launch.assert_not_called()
        self.assertEqual(self.window._category(), "Sony PlayStation")
        self.assertIn("PS4 PKG Tool", self.window.notice_label.text())
        self.assertNotIn("shadps4", [entry["id"] for entry in self.window.visible_entries])


if __name__ == "__main__":
    unittest.main()
