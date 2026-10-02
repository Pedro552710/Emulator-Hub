"""Native Profilabläufe mit echten lokalen Dateien und isolierten Datenordnern."""

from pathlib import Path
import threading
import time
import unittest
from unittest.mock import Mock, patch
import zipfile

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from core.installer import HubService
from tests.helpers import TemporaryDirectory, make_catalog, windows_executable
from ui.window import MainWindow


class ProfileUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog, original = make_catalog(self.root)
        self.entry = self.catalog.by_id(original["id"])
        self.entry["bios"] = [{"label": "Eigene Testfirmware", "root": "emulator", "directory": "firmware", "filenames": ["bios.bin"], "required": True}]
        self.entry["backup_paths"] = [{"label": "Spielstände und Einstellungen", "root": "emulator", "directory": "profile", "type": "directory"}]
        self.entry["bios_note"] = "Ausschließlich eigene lokale Dateien auswählen."
        self.service = HubService(self.catalog, self.root / "data")
        self.service.settings.set("system_report", {"cpu_cores": 8, "ram_gb": 16, "gpu_score": 3})
        self.service.system_report = self.service.settings.get("system_report")
        self.emulator = self.root / "Eigener Emulator"
        self.emulator.mkdir()
        (self.emulator / self.entry["exe"]).write_bytes(windows_executable())
        self.service.register_manual(self.entry, self.emulator)
        self.profile = self.emulator / "profile"
        self.profile.mkdir()
        self.save = self.profile / "spielstand.sav"
        self.save.write_bytes(b"gesicherter Spielstand")
        self.window = MainWindow(self.service, self.catalog)
        self.window.show()
        self.window.select_page("all")
        self.app.processEvents()
        self.release = threading.Event()

    def tearDown(self):
        self.release.set()
        if self.window.worker is not None:
            self.window.worker.cancel()
            self.window.worker.wait(3000)
            self.app.processEvents()
        if self.window._profile_dialog is not None:
            self.window._profile_dialog.reject()
            self.window._profile_dialog = None
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        for handler in list(self.service.logger.handlers):
            handler.close()
            self.service.logger.removeHandler(handler)
        self.temp.cleanup()

    def wait_until(self, condition, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if condition():
                return
            QTest.qWait(5)
        self.fail("Profilauftrag wurde nicht rechtzeitig abgeschlossen.")

    def in_profile_dialog(self, action):
        """Drive the actual native modal dialog after its first real worker finishes."""
        failures = []
        deadline = time.monotonic() + 10

        def ready():
            dialog = self.window._profile_dialog
            if dialog is None or self.window.worker is not None:
                if time.monotonic() < deadline:
                    QTimer.singleShot(10, ready)
                    return
                failures.append(AssertionError("Der BIOS-Dialog wurde nicht rechtzeitig bereit."))
            else:
                try:
                    action(dialog)
                except BaseException as exc:
                    failures.append(exc)
            if dialog is not None:
                dialog.reject()

        QTimer.singleShot(10, ready)
        self.window.cards[self.entry["id"]].profiles_button.click()
        if failures:
            raise failures[0]

    def archive(self):
        return self.service.backup(self.entry, self.root / "Sicherungen", Mock(), Mock(), threading.Event())

    def test_bios_checker_uses_background_thread_and_own_file_override_can_be_reset(self):
        own = self.root / "Meine eigene Firmware.bin"
        own.write_bytes(b"synthetische lokale Testdatei")
        threads = []
        original = self.service.check_bios

        def check(*args):
            threads.append(threading.get_ident())
            return original(*args)

        def action(dialog):
            self.assertIn("fehlt", dialog.bios_report.toPlainText())
            self.assertIn(str(self.emulator / "firmware" / "bios.bin"), dialog.bios_report.toPlainText())
            with patch("ui.window.QFileDialog.getOpenFileNames", return_value=([str(own)], "")):
                dialog.own_bios_button.click()
            self.wait_until(lambda: self.window.worker is None)
            self.assertIn("vorhanden", dialog.bios_report.toPlainText())
            self.assertIn(str(own), dialog.bios_report.toPlainText())
            self.assertEqual(self.service.settings.get("bios_overrides")[self.entry["id"]][0]["path"], str(own))
            dialog.default_bios_button.click()
            self.wait_until(lambda: self.window.worker is None)
            self.assertIn("fehlt", dialog.bios_report.toPlainText())
            self.assertNotIn(self.entry["id"], self.service.settings.get("bios_overrides"))

        with patch.object(self.service, "check_bios", side_effect=check):
            self.in_profile_dialog(action)
        self.assertEqual(len(threads), 3)
        self.assertTrue(all(identifier != threading.get_ident() for identifier in threads))
        self.assertEqual(own.read_bytes(), b"synthetische lokale Testdatei")

    def test_zip_backup_runs_in_worker_keeps_gui_responsive_and_saves_only_profiles(self):
        target = self.root / "Sicherungen"
        target.mkdir()
        entered = threading.Event()
        threads = []
        original = self.service.backup

        def backup(*args):
            threads.append(threading.get_ident())
            args[2](35, "Spielstände sichern · Hintergrundauftrag")
            entered.set()
            if not self.release.wait(3):
                raise RuntimeError("Der Testauftrag wurde nicht freigegeben.")
            return original(*args)

        def action(dialog):
            with patch("ui.window.QFileDialog.getExistingDirectory", return_value=str(target)):
                dialog.backup_button.click()
            self.wait_until(lambda: entered.is_set() and dialog.progress_bar.value() == 35)
            self.assertFalse(dialog.backup_button.isEnabled())
            self.assertFalse(dialog.restore_button.isEnabled())
            self.assertTrue(dialog.progress_bar.isVisible())
            self.assertEqual(dialog.operation_label.text(), "Spielstände sichern · Hintergrundauftrag")
            self.assertTrue(self.window.worker.isRunning())
            self.window.search.setText("Testemulator")
            self.app.processEvents()
            self.assertEqual(self.window.search.text(), "Testemulator")
            self.release.set()
            self.wait_until(lambda: self.window.worker is None)
            self.assertTrue(dialog.backup_button.isEnabled())
            self.assertIn("ZIP-Sicherung erstellt", dialog.result_label.text())

        with patch.object(self.service, "backup", side_effect=backup):
            self.in_profile_dialog(action)
        self.assertNotEqual(threads[0], threading.get_ident())
        archives = list(target.glob("*.zip"))
        self.assertEqual(len(archives), 1)
        with zipfile.ZipFile(archives[0]) as saved:
            self.assertTrue(any(name.endswith("spielstand.sav") for name in saved.namelist()))
            self.assertFalse(any(name.endswith(".exe") for name in saved.namelist()))
        self.assertEqual(self.save.read_bytes(), b"gesicherter Spielstand")

    def test_restore_cancel_keeps_current_files_and_never_starts_restore_worker(self):
        archive = self.archive()
        self.save.write_bytes(b"aktueller Spielstand")
        notices = []

        def show(box):
            notices.append((box.windowTitle(), box.informativeText(), box.defaultButton().text()))
            return 0

        def cancel(box):
            return next(button for button in box.buttons() if button.text() == "Abbrechen")

        def action(dialog):
            with patch("ui.window.QFileDialog.getOpenFileName", return_value=(str(archive), "")), patch("ui.window.QMessageBox.exec", new=show), patch("ui.window.QMessageBox.clickedButton", new=cancel), patch.object(self.service, "restore_backup", wraps=self.service.restore_backup) as restore:
                dialog.restore_button.click()
                restore.assert_not_called()
            self.assertIsNone(self.window.worker)

        self.in_profile_dialog(action)
        self.assertEqual(self.save.read_bytes(), b"aktueller Spielstand")
        self.assertEqual(notices[0][0], "Sicherung wiederherstellen")
        self.assertIn("zuerst als Sicherheitsbackup", notices[0][1])
        self.assertEqual(notices[0][2], "Abbrechen")

    def test_confirmed_restore_creates_safety_backup_before_overwriting_and_uses_worker(self):
        archive = self.archive()
        self.save.write_bytes(b"aktueller Spielstand vor Wiederherstellung")
        threads, results = [], []
        original = self.service.restore_backup

        def restore(*args):
            threads.append(threading.get_ident())
            result = original(*args)
            results.append(result)
            return result

        def accept(box):
            return next(button for button in box.buttons() if button.text() == "Sichern und wiederherstellen")

        def action(dialog):
            with patch("ui.window.QFileDialog.getOpenFileName", return_value=(str(archive), "")), patch("ui.window.QMessageBox.exec", return_value=0), patch("ui.window.QMessageBox.clickedButton", new=accept):
                dialog.restore_button.click()
            self.wait_until(lambda: self.window.worker is None)
            self.assertIn("Sicherheitsbackup", dialog.result_label.text())
            self.assertEqual(self.save.read_bytes(), b"gesicherter Spielstand")

        with patch.object(self.service, "restore_backup", side_effect=restore):
            self.in_profile_dialog(action)
        self.assertNotEqual(threads[0], threading.get_ident())
        self.assertEqual(results[0]["count"], 1)
        with zipfile.ZipFile(results[0]["safety_backup"]) as current:
            name = next(name for name in current.namelist() if name.endswith("spielstand.sav"))
            self.assertEqual(current.read(name), b"aktueller Spielstand vor Wiederherstellung")

    def test_unsafe_whole_emulator_profile_is_rejected_before_settings_are_changed(self):
        before = self.service.settings.get("profile_overrides", {})

        def action(dialog):
            with patch("ui.window.ProfilePathsDialog.exec", return_value=QDialog.DialogCode.Accepted), patch("ui.window.ProfilePathsDialog.selected_paths", return_value=[str(self.emulator)]), patch.object(self.window, "_message") as notice:
                dialog.paths_button.click()
            notice.assert_called_once()
            self.assertIn("gezielten", notice.call_args.args[1])
            self.assertEqual(self.service.settings.get("profile_overrides", {}), before)
            self.assertEqual(self.service.profile_paths(self.entry)[0]["path"], self.profile)

        self.in_profile_dialog(action)

    def test_cached_null_gpu_and_warning_lists_do_not_break_native_window_start(self):
        self.service.system_report = {"cpu_name": "Test-CPU", "cpu_cores": 8, "ram_gb": 16, "gpu_score": 3, "gpus": None, "warnings": None}
        self.window.close()
        self.window.deleteLater()
        self.window = MainWindow(self.service, self.catalog)
        self.window.show()
        self.app.processEvents()
        self.assertIn("Test-CPU", self.window.system_summary.text())
        self.assertIn("GPU unbekannt", self.window.system_summary.text())
        self.assertEqual(self.window.system_summary.toolTip(), "")


if __name__ == "__main__":
    unittest.main()
