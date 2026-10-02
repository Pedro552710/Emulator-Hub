"""Native Bibliotheksabläufe mit echten lokalen Metadaten und simuliertem Start."""

from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication

from core.catalog import Catalog
from core.installer import HubService
from tests.helpers import windows_executable
from ui.window import MainWindow


class LibraryUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog = Catalog()
        self.service = HubService(self.catalog, self.root / "data")
        self.service.settings.set("system_report", {"cpu_cores": 8, "ram_gb": 16, "gpu_score": 3})
        self.service.system_report = self.service.settings.get("system_report")
        self.games = self.root / "Eigene Spiele"
        self.games.mkdir()
        for name in ("Alpha.nes", "Zeta.nes", "Handheld.gba", "Disc.iso"):
            (self.games / name).write_bytes(b"eigene unveraenderte Datei")
        self.service.library.scan([self.games], Mock(), Mock(), threading.Event())
        self.ids = {g["name"]: g["id"] for g in self.service.library.games}
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

    def selected_item(self, name):
        page = self.window.library_page
        for row in range(page.tree.topLevelItemCount()):
            group = page.tree.topLevelItem(row)
            for child in range(group.childCount()):
                item = group.child(child)
                if item.data(0, Qt.ItemDataRole.UserRole) == self.ids[name]:
                    page.tree.setCurrentItem(item)
                    return item
        self.fail(f"Spiel fehlt in der Ansicht: {name}")

    def test_grouped_games_search_console_filter_sort_and_star_follow_persisted_metadata(self):
        page = self.window.library_page
        self.assertEqual(page.tree.topLevelItemCount(), 3)
        page.console_filter.setCurrentIndex(page.console_filter.findData("NES"))
        self.assertEqual([g["name"] for g in page.visible_games], ["Alpha", "Zeta"])
        self.service.library.touch_game(self.ids["Zeta"], "mesen")
        page.sort_order.setCurrentIndex(page.sort_order.findData("last_played"))
        self.assertEqual([g["name"] for g in page.visible_games], ["Zeta", "Alpha"])
        item = self.selected_item("Alpha")
        page._clicked(item, 3)
        self.assertTrue(self.service.library.get_game(self.ids["Alpha"])["favorite"])
        page.favorites_only.setChecked(True)
        page.search.setText("ALPHA")
        self.assertEqual([g["name"] for g in page.visible_games], ["Alpha"])
        self.assertEqual(page.tree.topLevelItem(0).child(0).text(3), "★")
        page.search.setText("Zeta")
        self.assertEqual(page.visible_games, [])
        self.assertTrue(page.empty_label.isVisible())
        page.favorites_only.setChecked(False)
        self.assertEqual([g["name"] for g in page.visible_games], ["Zeta"])
        self.assertIn("Eigene Spiele", page.visible_games[0]["path"])

    def test_missing_emulator_offers_install_button_and_routes_selected_catalog_entry(self):
        def clicked_install(box):
            return next(button for button in box.buttons() if button.text() == "Installieren")

        with patch("ui.window.QMessageBox.exec", return_value=0), patch(
            "ui.window.QMessageBox.clickedButton", new=clicked_install
        ), patch.object(self.window, "install") as install, patch.object(self.service, "launch_game") as launch:
            self.window.launch_game(self.ids["Alpha"])
        install.assert_called_once_with(self.catalog.by_id("mesen"))
        launch.assert_not_called()
        self.assertEqual(self.service.library.get_game(self.ids["Alpha"])["last_played"], "")

    def test_ambiguous_iso_selection_assigns_console_and_double_click_starts_matching_emulator(self):
        entry = self.catalog.by_id("ppsspp")
        entry["launch_args"] = ["{game}"]
        emulator = self.root / "Eigener PSP Emulator"
        emulator.mkdir()
        exe = emulator / entry["exe"]
        exe.write_bytes(windows_executable())
        self.service.register_manual(entry, emulator)
        page = self.window.library_page
        item = self.selected_item("Disc")
        self.assertIsNone(self.service.library.get_game(self.ids["Disc"])["console"])
        with patch("ui.window.QInputDialog.getItem", return_value=("PSP", True)) as choice, patch(
            "core.launch.subprocess.Popen"
        ) as launch:
            page._double_clicked(item, 0)
        choice.assert_called_once()
        launch.assert_called_once_with([str(exe), str(self.games / "Disc.iso")], cwd=emulator, shell=False)
        game = self.service.library.get_game(self.ids["Disc"])
        self.assertEqual(game["console"], "PSP")
        self.assertEqual(game["emulator_id"], "ppsspp")
        self.assertTrue(game["last_played"])
        self.assertEqual((self.games / "Disc.iso").read_bytes(), b"eigene unveraenderte Datei")


if __name__ == "__main__":
    unittest.main()
