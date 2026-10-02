"""Controller-Assistent: echte Qt-Aufträge, Bestätigung und simulierte Hardware."""

from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

from core.installer import HubService
from tests.helpers import make_catalog, windows_executable
from ui.controllers import ControllerDialog


class FakeBackend:
    unavailable_reason = ""

    def __init__(self):
        self.states = [{"slot": 1, "name": "XInput-Controller 2", "type": "XInput-Gamepad",
                        "subtype": 1, "buttons": {"A", "UP"},
                        "axes": {"lx": 0.5, "ly": 0, "rx": 0, "ry": 0, "lt": 1, "rt": 0}}]

    def poll(self):
        return self.states


class ControllerUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog, original = make_catalog(self.root)
        self.entry = self.catalog.by_id(original["id"])
        self.entry.update(controller_config="auto", controller_adapter="dolphin_gc_xinput",
                          backup_paths=[{"label": "Einstellungen", "root": "emulator",
                                         "directory": "Config", "type": "directory"}])
        self.hub = HubService(self.catalog, self.root / "data")
        self.emulator = self.root / "emulator"
        self.emulator.mkdir()
        (self.emulator / self.entry["exe"]).write_bytes(windows_executable())
        self.hub.register_manual(self.entry, self.emulator)
        folder = self.emulator / "Config"
        folder.mkdir()
        (folder / "Dolphin.ini").write_bytes(b"[Core]\nSIDevice0 = 6\n")
        self.config = folder / "GCPadNew.ini"
        self.original = b"[GCPad1]\nDevice = Tastatur\nButtons/A = `X`\n[GCPad2]\nDevice = Unveraendert\n"
        self.config.write_bytes(self.original)
        self.backend = FakeBackend()
        self.dialog = ControllerDialog(self.hub, backend=self.backend)
        self.dialog.show()
        self.app.processEvents()

    def tearDown(self):
        if self.dialog.worker:
            self.dialog.worker.cancel()
            self.dialog.worker.wait(3000)
            self.app.processEvents()
        self.dialog.reject()
        self.dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        for handler in list(self.hub.logger.handlers):
            handler.close()
            self.hub.logger.removeHandler(handler)
        self.temp.cleanup()

    def wait_until(self, condition):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.app.processEvents()
            if condition():
                return
            QTest.qWait(5)
        self.fail("Controller-Auftrag wurde nicht rechtzeitig beendet.")

    def preview(self):
        self.dialog.preview_button.click()
        self.wait_until(lambda: self.dialog.worker is None)
        self.assertIsNotNone(self.dialog._preview)

    def test_live_test_shows_buttons_axes_and_detects_disconnect(self):
        self.assertIn("XInput-Controller 2", self.dialog.device_combo.currentText())
        self.assertIn("A", self.dialog.buttons_status.text())
        self.assertIn("Oben", self.dialog.buttons_status.text())
        self.assertIn("+0.50", self.dialog.axes_status.text())
        self.assertIn("100%", self.dialog.axes_status.text())
        self.assertTrue(self.dialog.preview_button.isEnabled())
        self.backend.states = []
        self.dialog._poll()
        self.assertIn("Kein XInput-Controller", self.dialog.device_combo.currentText())
        self.assertFalse(self.dialog.preview_button.isEnabled())
        self.assertFalse(self.dialog.apply_button.isEnabled())

    def test_preview_apply_and_undo_run_in_workers_require_user_confirmation(self):
        threads = []
        original_preview = self.dialog.controllers.preview
        original_apply = self.dialog.controllers.apply
        original_undo = self.dialog.controllers.undo

        def tracked(operation):
            def run(*args, **kwargs):
                threads.append(threading.get_ident())
                return operation(*args, **kwargs)
            return run

        with patch.object(self.dialog.controllers, "preview", side_effect=tracked(original_preview)), \
                patch.object(self.dialog.controllers, "apply", side_effect=tracked(original_apply)), \
                patch.object(self.dialog.controllers, "undo", side_effect=tracked(original_undo)):
            self.preview()
            self.assertEqual(self.config.read_bytes(), self.original)
            self.assertIn("XInput/1/Gamepad", self.dialog.preview_text.toPlainText())
            with patch("ui.controllers.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
                self.dialog.apply_button.click()
            self.assertEqual(self.config.read_bytes(), self.original)
            self.assertFalse(self.dialog.undo_button.isEnabled())
            with patch("ui.controllers.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
                self.dialog.apply_button.click()
            self.wait_until(lambda: self.dialog.worker is None)
            self.assertIn(b"XInput/1/Gamepad", self.config.read_bytes())
            self.assertTrue(self.dialog.undo_button.isEnabled())
            self.assertIn("Sicherung:", self.dialog.status.text())
            with patch("ui.controllers.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
                self.dialog.undo_button.click()
            self.assertIn(b"XInput/1/Gamepad", self.config.read_bytes())
            with patch("ui.controllers.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
                self.dialog.undo_button.click()
            self.wait_until(lambda: self.dialog.worker is None)
            self.assertEqual(self.config.read_bytes(), self.original)
        self.assertEqual(len(threads), 3)
        self.assertTrue(all(identifier != threading.get_ident() for identifier in threads))

    def test_manual_emulator_never_offers_automatic_writes(self):
        self.entry["controller_config"] = "manuell"
        self.dialog._emulator_changed()
        self.assertFalse(self.dialog.path_button.isEnabled())
        self.assertFalse(self.dialog.preview_button.isEnabled())
        self.assertFalse(self.dialog.apply_button.isEnabled())
        self.assertIn("Keine automatische Änderung", self.dialog.path_label.text())
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_different_xinput_type_does_not_offer_gamepad_autoconfiguration(self):
        self.backend.states[0].update(type="XInput-Lenkrad", subtype=2)
        self.dialog._poll()
        self.assertIn("Lenkrad", self.dialog.device_combo.currentText())
        self.assertFalse(self.dialog.preview_button.isEnabled())
        self.assertFalse(self.dialog.apply_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
