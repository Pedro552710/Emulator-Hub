"""Native Qt smoke regressions with no download or process launch."""

from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QEvent, QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog

from core.errors import HubError
from ui.window import MainWindow


class FakeService:
    def __init__(self, log_path):
        self.log_path = log_path
        self.installed = {
            "alpha": {"path": "C:/fake/alpha", "version": "v1", "managed": True},
            "beta": {"path": "C:/fake/missing", "version": "v1", "managed": True},
        }
        self.runnable = {"alpha"}
        self.latest_versions = {}

    def is_installed(self, identifier):
        return identifier in self.runnable

    def status(self, identifier):
        if identifier not in self.runnable:
            return "nicht installiert"
        return "Update verfügbar" if identifier in self.latest_versions else "installiert"


def fake_catalog():
    entries = [
        {"id": "alpha", "emulator": "Alpha DS", "konsole": "Nintendo DS", "kategorie": "Nintendo", "install_methode": "auto_github"},
        {"id": "beta", "emulator": "Beta Station", "konsole": "PlayStation 2", "kategorie": "Sony PlayStation", "install_methode": "auto_github"},
        {"id": "gamma", "emulator": "Gamma Advance", "konsole": "Game Boy Advance", "kategorie": "Nintendo", "install_methode": "manuell"},
    ]
    return SimpleNamespace(items=entries, categories=["Nintendo", "Sony PlayStation"])


class NativeWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Deliberately use the normal native platform instead of offscreen rendering.
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.catalog = fake_catalog()
        self.service = FakeService(Path(self.temp.name) / "hub.log")
        self.window = MainWindow(self.service, self.catalog)
        self.release = threading.Event()
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.release.set()
        worker = self.window.worker
        if worker is not None:
            worker.cancel()
            worker.wait(3000)
            self.app.processEvents()
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.temp.cleanup()

    def wait_until(self, condition, *, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if condition():
                return
            QTest.qWait(5)
        self.fail("Qt-Signal bzw. Oberflächenzustand wurde nicht rechtzeitig erreicht.")

    def visible_ids(self):
        return {entry["id"] for entry in self.window.visible_entries}

    def select_category(self, key):
        from PySide6.QtCore import Qt
        for row in range(self.window.navigation.count()):
            if self.window.navigation.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self.window.navigation.setCurrentRow(row)
                return
        self.fail(f"Kategorie fehlt: {key}")

    def test_search_combines_with_category_and_installed_filters(self):
        self.assertEqual(self.visible_ids(), {"alpha", "beta", "gamma"})
        self.select_category("Nintendo")
        self.assertEqual(self.visible_ids(), {"alpha", "gamma"})
        self.window.search.setText("GAME BOY")
        self.wait_until(lambda: self.visible_ids() == {"gamma"})
        self.assertEqual(self.window.results_label.text(), "1 Emulator · Suche: GAME BOY")
        self.select_category("Sony PlayStation")
        self.assertEqual(self.visible_ids(), set())
        self.assertTrue(self.window.empty_label.isVisible())
        self.window.search.clear()
        self.wait_until(lambda: self.visible_ids() == {"beta"})
        self.select_category("installed")
        self.assertEqual(self.visible_ids(), {"alpha"})
        self.assertEqual(self.window.installed_value.text(), "1")

    def test_missing_executable_keeps_uninstall_enabled_for_recorded_installation(self):
        card = self.window.cards["beta"]
        self.assertTrue(card.uninstall_button.isEnabled())
        self.assertTrue(card.install_button.isEnabled())
        self.assertFalse(card.start_button.isEnabled())
        self.assertEqual(card.status_label.text(), "Nicht installiert")
        self.service.installed.pop("beta")
        self.window.refresh()
        self.assertFalse(card.uninstall_button.isEnabled())

    def test_qthread_reports_progress_while_window_remains_responsive_and_releases_worker(self):
        entered = threading.Event()
        completion = Mock()
        thread_ids = []

        def operation(progress, log, cancel_event):
            thread_ids.append(threading.get_ident())
            progress(45, "Testdownload läuft")
            log("Hintergrundauftrag gestartet")
            entered.set()
            if not self.release.wait(3):
                raise RuntimeError("Test worker was not released")
            progress(100, "Testdownload abgeschlossen")
            return "done"

        self.window._run_job("Testauftrag", operation, completion)
        self.wait_until(lambda: entered.is_set() and self.window.progress_bar.value() == 45)
        self.assertNotEqual(thread_ids[0], threading.get_ident())
        self.assertIsInstance(self.window.worker, QThread)
        self.assertEqual(self.window.operation_label.text(), "Testdownload läuft")
        self.assertFalse(self.window.update_button.isEnabled())
        self.assertFalse(self.window.cards["alpha"].start_button.isEnabled())
        self.window.search.setText("beta")
        self.wait_until(lambda: self.visible_ids() == {"beta"})
        self.assertTrue(self.window.worker.isRunning())
        self.assertTrue(self.window.search.isEnabled())
        self.release.set()
        self.wait_until(lambda: self.window.worker is None)
        completion.assert_called_once_with("done")
        self.assertFalse(self.window.operation_frame.isVisible())
        self.assertTrue(self.window.update_button.isEnabled())
        self.assertTrue(self.window.cards["alpha"].start_button.isEnabled())
        self.assertTrue(any("Hintergrundauftrag gestartet" in line for line in self.window._log_lines))

    def test_worker_failure_displays_error_and_restores_controls_without_modal_blocking(self):
        def operation(progress, log, cancel_event):
            raise HubError("Testfehler ohne Internetzugriff")

        completion = Mock()
        with patch("ui.window.QMessageBox.exec", return_value=0):
            self.window._run_job("Fehlertest", operation, completion)
            self.wait_until(lambda: self.window.worker is None)
        completion.assert_not_called()
        self.assertTrue(self.window.notice.isVisible())
        self.assertEqual(self.window.notice_label.text(), "Testfehler ohne Internetzugriff")
        self.assertTrue(self.window.update_button.isEnabled())
        self.assertFalse(self.window.operation_frame.isVisible())

    def test_manual_install_button_opens_instruction_dialog_without_starting_worker(self):
        with patch("ui.window.ManualDialog.exec", return_value=QDialog.DialogCode.Rejected) as show:
            self.window.cards["gamma"].install_button.click()
        show.assert_called_once()
        self.assertIsNone(self.window.worker)


if __name__ == "__main__":
    unittest.main()
