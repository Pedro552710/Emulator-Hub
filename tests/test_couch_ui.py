"""Couch-Bedienung ohne echten Controller, Netzwerk oder Emulatorprozess."""

from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import time
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QEvent, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QInputDialog, QMessageBox, QPushButton

from ui.couch import CouchDialog, _cover_pixmap


def state(*buttons, lx=0.0, ly=0.0, slot=0):
    return {"slot": slot, "name": f"Test-Controller {slot}", "type": "XInput-Gamepad",
            "buttons": set(buttons), "axes": {"lx": lx, "ly": ly}}


class CouchUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.games = [
            {"id": "a", "name": "Alpha", "console": "Konsole A", "path": "C:/a.nes"},
            {"id": "b", "name": "Beta", "console": "Konsole A", "path": "C:/b.nes"},
            {"id": "c", "name": "Gamma", "console": "Konsole A", "path": "C:/c.nes"},
            {"id": "d", "name": "Delta", "console": "Konsole B", "path": "C:/d.gba"},
            {"id": "e", "name": "Epsilon", "console": None, "path": "C:/e.iso"},
        ]
        self.service = SimpleNamespace(library=SimpleNamespace(games=self.games))
        self.backend = Mock()
        self.backend.poll.return_value = []
        self.dialog = CouchDialog(self.service, backend=self.backend)
        self.modals = []
        self.dialog.resize(1024, 760)
        self.dialog.show()
        self.app.processEvents()
        self.dialog.timer.stop()

    def tearDown(self):
        for modal in self.modals:
            modal.close()
            modal.deleteLater()
        self.dialog.close()
        self.dialog.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()

    def press(self, key):
        target = self.dialog._tiles[self.dialog._selected] if self.dialog._tiles else self.dialog
        QTest.keyClick(target, key)
        self.app.processEvents()

    def show_modal(self, modal):
        self.modals.append(modal)
        modal.setModal(True)
        modal.show()
        modal.activateWindow()
        QTest.qWait(50)
        self.app.processEvents()
        return modal

    def poll(self, *buttons, **axes):
        self.backend.poll.return_value = [state(*buttons, **axes)]
        self.dialog._poll_controllers()
        self.app.processEvents()

    def test_keyboard_opens_console_and_emits_existing_game_launch_signal(self):
        self.assertEqual([tile.title for tile in self.dialog._tiles], ["Konsole A", "Konsole B", "Noch zuordnen"])
        launch = Mock()
        self.dialog.launchRequested.connect(launch)
        self.press(Qt.Key.Key_Return)
        self.assertEqual(self.dialog._page, "games")
        self.assertEqual(self.dialog._console, "Konsole A")
        self.press(Qt.Key.Key_Right)
        self.assertEqual(self.dialog._selected, 1)
        self.press(Qt.Key.Key_Return)
        launch.assert_called_once_with("b")
        self.assertTrue(self.dialog.isVisible())
        self.press(Qt.Key.Key_Backspace)
        self.assertEqual(self.dialog._page, "consoles")
        self.press(Qt.Key.Key_Escape)
        self.assertFalse(self.dialog.isVisible())
        self.assertFalse(self.dialog.timer.isActive())

    def test_grid_navigation_preserves_rows_and_tab_does_not_leave_tiles(self):
        self.dialog._show_games("Konsole A")
        self.dialog._columns = 2
        self.dialog._select(1)
        self.press(Qt.Key.Key_Right)
        self.assertEqual(self.dialog._selected, 1)
        self.press(Qt.Key.Key_Down)
        self.assertEqual(self.dialog._selected, 2)
        self.press(Qt.Key.Key_Up)
        self.assertEqual(self.dialog._selected, 0)
        self.press(Qt.Key.Key_Tab)
        self.assertEqual(self.dialog._selected, 1)
        self.assertTrue(self.dialog._tiles[1].hasFocus())
        self.press(Qt.Key.Key_Backtab)
        self.assertEqual(self.dialog._selected, 0)

    def test_menu_returns_to_selected_game_and_can_close_fullscreen(self):
        self.dialog._show_games("Konsole A")
        self.dialog._select(1)
        self.press(Qt.Key.Key_M)
        self.assertEqual(self.dialog._page, "menu")
        self.press(Qt.Key.Key_Backspace)
        self.assertEqual(self.dialog._page, "games")
        self.assertEqual(self.dialog._selected, 1)
        self.press(Qt.Key.Key_M)
        self.press(Qt.Key.Key_Down)
        self.press(Qt.Key.Key_Return)
        self.assertFalse(self.dialog.isVisible())

    def test_controller_requires_release_then_edges_repeat_and_back(self):
        launch = Mock()
        self.dialog.launchRequested.connect(launch)
        self.dialog._handle_controller(state("A"), 0)
        self.assertEqual(self.dialog._page, "consoles")
        self.dialog._handle_controller(state(), .1)
        self.dialog._handle_controller(state("A"), .2)
        self.assertEqual(self.dialog._page, "games")
        self.dialog._handle_controller(state("A"), .3)
        launch.assert_not_called()
        self.dialog._handle_controller(state(), .4)
        self.dialog._columns = 1
        self.dialog._handle_controller(state("DOWN"), .5)
        self.assertEqual(self.dialog._selected, 1)
        self.dialog._handle_controller(state("DOWN"), .6)
        self.assertEqual(self.dialog._selected, 1)
        self.dialog._handle_controller(state("DOWN"), .9)
        self.assertEqual(self.dialog._selected, 2)
        self.dialog._handle_controller(state(), 1.0)
        self.dialog._handle_controller(state("A"), 1.1)
        launch.assert_called_once_with("c")
        self.dialog._handle_controller(state(), 1.2)
        self.dialog._handle_controller(state("B"), 1.3)
        self.assertEqual(self.dialog._page, "consoles")

    def test_stick_start_menu_and_long_start_select_exit(self):
        self.dialog._handle_controller(state(), 0)
        self.dialog._handle_controller(state(lx=1), .1)
        self.assertEqual(self.dialog._selected, 1)
        self.dialog._handle_controller(state(), .2)
        self.dialog._handle_controller(state("START"), .3)
        self.assertEqual(self.dialog._page, "menu")
        self.dialog._handle_controller(state(), .4)
        self.dialog._handle_controller(state("START", "BACK"), 1.0)
        self.dialog._handle_controller(state("START", "BACK"), 2.1)
        self.assertTrue(self.dialog.isVisible())
        self.dialog._handle_controller(state("START", "BACK"), 2.21)
        self.assertFalse(self.dialog.isVisible())

    def test_poll_reconnect_cannot_accidentally_confirm_and_inactive_window_ignores_inputs(self):
        with patch.object(self.dialog, "isActiveWindow", return_value=True):
            self.backend.poll.return_value = [state("A")]
            self.dialog._poll_controllers()
            self.assertEqual(self.dialog._page, "consoles")
            self.backend.poll.return_value = [state()]
            self.dialog._poll_controllers()
            self.backend.poll.return_value = [state("A")]
            self.dialog._poll_controllers()
            self.assertEqual(self.dialog._page, "games")
            self.backend.poll.return_value = []
            self.dialog._poll_controllers()
            self.assertFalse(self.dialog._armed)
            self.assertIn("Kein XInput", self.dialog.controller_label.text())
        with patch.object(self.dialog, "isActiveWindow", return_value=False):
            self.backend.poll.reset_mock()
            self.dialog._poll_controllers()
            self.backend.poll.assert_called_once_with()
            self.assertEqual(self.dialog._page, "games")

    def test_gamepad_selects_native_combo_and_confirms_without_reusing_held_a(self):
        modal = QInputDialog(self.dialog)
        modal.setComboBoxItems(["Konsole A", "Konsole B", "Konsole C"])
        modal.setComboBoxEditable(False)
        self.show_modal(modal)
        combo = modal.findChild(QComboBox)
        combo.setFocus()
        self.app.processEvents()
        accepted = Mock()
        modal.accepted.connect(accepted)
        self.assertIs(self.dialog._controller_target(), modal)
        # Das A, das den Dialog geöffnet hat, bestätigt ihn nicht erneut.
        self.poll("A")
        accepted.assert_not_called()
        self.poll()
        self.poll("DOWN")
        self.assertEqual(combo.currentIndex(), 1)
        self.poll()
        self.poll(ly=-1)
        self.assertEqual(combo.currentIndex(), 2)
        self.poll()
        self.poll("RIGHT")
        self.assertIsInstance(modal.focusWidget(), QPushButton)
        self.poll()
        self.poll("A")
        accepted.assert_called_once_with()
        self.assertEqual(modal.textValue(), "Konsole C")
        self.poll("A")
        self.assertEqual(self.dialog._page, "consoles")
        self.poll()
        self.poll("A")
        self.assertEqual(self.dialog._page, "games")

    def test_message_box_buttons_can_be_focused_confirmed_and_rejected(self):
        box = QMessageBox(self.dialog)
        box.setText("Emulator installieren?")
        install = box.addButton("Installieren", QMessageBox.ButtonRole.AcceptRole)
        cancel = box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(install)
        install_clicked = Mock()
        install.clicked.connect(install_clicked)
        self.show_modal(box)
        install.setFocus()
        self.poll()
        self.poll("RIGHT")
        self.assertIs(box.focusWidget(), cancel)
        self.poll()
        self.poll("LB")
        self.assertIs(box.focusWidget(), install)
        self.poll()
        self.poll("A")
        install_clicked.assert_called_once()
        self.assertIs(box.clickedButton(), install)
        self.assertTrue(self.dialog.isVisible())

        second = QMessageBox(self.dialog)
        second.setText("Später einrichten?")
        second.addButton("Einrichten", QMessageBox.ButtonRole.AcceptRole)
        second.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        rejected = Mock()
        second.rejected.connect(rejected)
        self.show_modal(second)
        self.poll("A")
        self.assertTrue(second.isVisible())
        self.poll()
        self.poll("B")
        rejected.assert_called_once_with()
        self.assertIsNone(second.clickedButton())
        self.assertTrue(self.dialog.isVisible())

    def test_long_exit_combo_rejects_native_modal_then_closes_couch(self):
        modal = QInputDialog(self.dialog)
        modal.setComboBoxItems(["Emulator A", "Emulator B"])
        rejected, couch_rejected = Mock(), Mock()
        modal.rejected.connect(rejected)
        self.dialog.rejected.connect(couch_rejected)
        self.show_modal(modal)
        self.dialog._handle_controller(state(), 0, target=modal)
        self.dialog._handle_controller(state("START", "BACK"), 1, target=modal)
        self.dialog._handle_controller(state("START", "BACK"), 2.19, target=modal)
        self.assertTrue(modal.isVisible())
        self.dialog._handle_controller(state("START", "BACK"), 2.21, target=modal)
        rejected.assert_called_once_with()
        couch_rejected.assert_called_once_with()
        self.assertFalse(modal.isVisible())
        self.assertFalse(self.dialog.isVisible())

    def test_foreign_or_inactive_modal_never_receives_controller_events(self):
        foreign = QInputDialog()
        foreign.setComboBoxItems(["Andere Anwendung A", "Andere Anwendung B"])
        self.show_modal(foreign)
        self.backend.poll.return_value = [state("DOWN", "A")]
        self.backend.poll.reset_mock()
        with patch("ui.couch.QApplication.sendEvent") as dispatch:
            self.dialog._poll_controllers()
            dispatch.assert_not_called()
        self.backend.poll.assert_called_once_with()
        self.assertEqual(foreign.findChild(QComboBox).currentIndex(), 0)
        foreign.close()
        own = QInputDialog(self.dialog)
        own.setComboBoxItems(["Konsole A", "Konsole B"])
        self.show_modal(own)
        with patch.object(own, "isActiveWindow", return_value=False):
            self.backend.poll.reset_mock()
            self.dialog._poll_controllers()
            self.backend.poll.assert_called_once_with()
            self.assertEqual(own.findChild(QComboBox).currentIndex(), 0)

    def test_inactive_gamepad_only_exits_own_couch_after_release_and_long_combo(self):
        launch, rejected = Mock(), Mock()
        self.dialog.launchRequested.connect(launch)
        self.dialog.rejected.connect(rejected)
        foreign = QInputDialog()
        foreign.setComboBoxItems(["Andere Anwendung A", "Andere Anwendung B"])
        self.show_modal(foreign)
        with patch("ui.couch.time.monotonic") as clock, patch("ui.couch.QApplication.sendEvent") as dispatch:
            clock.return_value = 0
            self.poll("START", "BACK")
            clock.return_value = 2
            self.poll("START", "BACK")
            self.assertTrue(self.dialog.isVisible())
            clock.return_value = 3
            self.poll()
            clock.return_value = 3.1
            self.poll("A", "B", "DOWN", lx=1)
            self.assertEqual(self.dialog._page, "consoles")
            self.assertEqual(self.dialog._selected, 0)
            clock.return_value = 4
            self.poll("START", "BACK")
            clock.return_value = 5.19
            self.poll("START", "BACK")
            self.assertTrue(self.dialog.isVisible())
            clock.return_value = 5.21
            self.poll("START", "BACK")
            dispatch.assert_not_called()
        launch.assert_not_called()
        rejected.assert_called_once_with()
        self.assertFalse(self.dialog.isVisible())
        self.assertTrue(foreign.isVisible())
        self.assertEqual(foreign.findChild(QComboBox).currentIndex(), 0)

    def test_poll_timer_keeps_working_inside_game_launch_modal_exec(self):
        self.dialog._show_games("Konsole A")
        modal = QInputDialog(self.dialog)
        modal.setComboBoxItems(["Emulator A", "Emulator B"])
        self.modals.append(modal)
        results = []
        failsafe = QTimer(modal)
        failsafe.setSingleShot(True)
        failsafe.setInterval(900)
        failsafe.timeout.connect(modal.reject)

        def choose_emulator(_identifier):
            failsafe.start()
            results.append(modal.exec())
            failsafe.stop()
            self.dialog.timer.stop()

        frames = iter([state(), state("A"), state("A"), state(), state("DOWN"), state(), state("A")])
        self.backend.poll.side_effect = lambda: [next(frames, state())]
        self.dialog.launchRequested.connect(choose_emulator)
        self.dialog.activateWindow()
        self.app.processEvents()
        self.dialog.timer.start()
        deadline = time.monotonic() + 2
        while not results and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertEqual(results, [QInputDialog.DialogCode.Accepted])
        self.assertEqual(modal.textValue(), "Emulator B")
        self.assertTrue(self.dialog.isVisible())

    def test_offline_metadata_cover_and_invalid_image_placeholder(self):
        with tempfile.TemporaryDirectory() as directory:
            cover = Path(directory) / "cover.png"
            image = QImage(100, 150, QImage.Format.Format_ARGB32)
            image.fill(QColor("#dd5533"))
            self.assertTrue(image.save(str(cover)))
            self.service.metadata = SimpleNamespace(get=lambda identifier: {
                "title": "Cover-Titel", "year": 1993, "cover_path": str(cover),
            } if identifier == "a" else None)
            self.dialog._show_games("Konsole A")
            tile = next(tile for tile in self.dialog._tiles if tile.title == "Cover-Titel")
            deadline = time.monotonic() + 3
            while tile.cover.isNull() and time.monotonic() < deadline:
                self.app.processEvents()
                QTest.qWait(5)
            self.assertFalse(tile.cover.isNull())
            self.assertEqual(tile.subtitle, "1993")
            self.assertFalse(self.dialog.grab().isNull())
            cover.write_text("Kein Bild", encoding="utf-8")
            self.assertTrue(_cover_pixmap(cover).isNull())
            self.assertTrue(_cover_pixmap(Path(directory) / "missing.png").isNull())

    def test_empty_library_keeps_menu_and_keyboard_exit_available(self):
        self.service.library.games = []
        self.dialog._show_consoles()
        self.assertEqual(self.dialog._tiles, [])
        self.assertTrue(self.dialog.empty_label.isVisible())
        self.press(Qt.Key.Key_M)
        self.assertEqual(self.dialog._page, "menu")
        self.press(Qt.Key.Key_Escape)
        self.assertFalse(self.dialog.isVisible())

    def test_cover_io_stays_in_worker_and_stale_result_cannot_change_menu(self):
        entered, release = threading.Event(), threading.Event()
        thread_ids = []

        def delayed_image(path):
            thread_ids.append(threading.get_ident())
            entered.set()
            release.wait(3)
            image = QImage(20, 30, QImage.Format.Format_ARGB32)
            image.fill(QColor("#dd5533"))
            return image

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cover.png"
            path.write_bytes(b"Testdatei")
            self.service.metadata = SimpleNamespace(get=lambda identifier: {"cover_path": str(path)} if identifier == "a" else None)
            try:
                with patch("ui.couch._cover_image", side_effect=delayed_image):
                    self.dialog._show_games("Konsole A")
                    deadline = time.monotonic() + 3
                    while not entered.is_set() and time.monotonic() < deadline:
                        self.app.processEvents()
                        QTest.qWait(5)
                    self.assertTrue(entered.is_set())
                    self.assertNotEqual(thread_ids[0], threading.get_ident())
                    self.press(Qt.Key.Key_M)
                    self.assertEqual(self.dialog._page, "menu")
                    release.set()
                    self.assertTrue(self.dialog.cover_pool.waitForDone(3000))
                    self.app.processEvents()
                    self.assertTrue(all(tile.cover.isNull() for tile in self.dialog._tiles))
            finally:
                release.set()
                self.dialog.cover_pool.waitForDone(3000)


if __name__ == "__main__":
    unittest.main()
