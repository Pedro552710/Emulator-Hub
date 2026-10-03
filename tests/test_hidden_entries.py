"""Hidden is a presentation filter; saved data and explicit installation remain available."""

from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtWidgets import QApplication

from core.catalog import Catalog, CatalogError
from core.errors import HubError
from core.installer import HubService
from core.settings import SettingsStore
from tests.helpers import TemporaryDirectory, Response, make_catalog, windows_executable
from ui.controllers import ControllerDialog
from ui.couch import CouchDialog
from ui.window import MainWindow


class HiddenCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog, self.entry = make_catalog(self.root)

    def test_optional_hidden_defaults_to_visible_and_hides_empty_categories_without_removal(self):
        self.assertEqual(self.catalog.visible_items(), self.catalog.items)
        self.entry["hidden"] = True
        self.catalog.items[0]["hidden"] = True
        self.assertEqual(self.catalog.visible_items(), [])
        self.assertEqual(self.catalog.visible_categories(), [])
        self.assertEqual(self.catalog.visible_items(show_hidden=True), self.catalog.items)
        self.assertEqual(self.catalog.visible_categories(show_hidden=True), ["Nintendo"])
        self.assertEqual(self.catalog.by_id(self.entry["id"])["id"], self.entry["id"])

    def test_hidden_requires_a_boolean_and_existing_settings_default_to_off(self):
        raw = json.loads(self.catalog.path.read_text(encoding="utf-8"))
        for value in (1, "true", None, []):
            with self.subTest(value=value):
                raw["emulators"][0]["hidden"] = value
                self.catalog.path.write_text(json.dumps(raw), encoding="utf-8")
                with self.assertRaises(CatalogError):
                    Catalog(self.catalog.path)
        settings = SettingsStore(self.root / "data")
        self.assertIs(settings.get("show_hidden"), False)
        settings.set("show_hidden", True)
        self.assertIs(SettingsStore(self.root / "data").get("show_hidden"), True)
        with self.assertRaises(HubError):
            settings.set("show_hidden", "true")

    def test_explicit_install_of_hidden_entry_preserves_download_policy_and_installation(self):
        self.catalog.items[0]["hidden"] = True
        self.entry["hidden"] = True
        sources = list(self.catalog.official_sources)
        service = HubService(self.catalog, self.root / "data")
        self.addCleanup(self.close_logger, service)
        self.assertEqual(list(service.policy.prefixes), sources)
        self.assertTrue(service.policy.allows(self.entry["official_url"]))
        with self.assertRaises(HubError):
            service.policy.validate("https://github.com/unofficial/emulator/releases/download/v1/emulator-win-x64.zip")
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("app/emulator.exe", windows_executable())
        body = output.getvalue()
        release = {"tag_name": "v1.0", "prerelease": False, "draft": False, "assets": [{
            "name": "emulator-win-x64.zip", "size": len(body),
            "browser_download_url": "https://github.com/official/emulator/releases/download/v1.0/emulator-win-x64.zip",
            "digest": "sha256:" + hashlib.sha256(body).hexdigest(),
        }]}
        with patch.object(service.github, "latest", return_value=release), patch.object(
            service.policy, "get", return_value=Response(body, headers={"Content-Length": str(len(body))})
        ):
            record = service.install(self.entry, Mock(), Mock(), threading.Event())
        self.assertTrue(service.is_installed(self.entry["id"]))
        self.assertEqual(Path(record["exe_path"]).read_bytes(), windows_executable())
        self.assertEqual(self.catalog.official_sources, sources)
        with patch.object(service.github, "latest") as latest, patch.object(service, "install") as install:
            self.assertEqual(service.check_updates(Mock(), Mock(), threading.Event()), {})
            result = service.update_all(Mock(), Mock(), threading.Event())
        latest.assert_not_called()
        install.assert_not_called()
        self.assertEqual(result["updated"], [])
        self.assertEqual(service.installed[self.entry["id"]], record)

    @staticmethod
    def close_logger(service):
        for handler in list(service.logger.handlers):
            handler.close()
            service.logger.removeHandler(handler)


class HiddenUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        original = Catalog()
        raw = json.loads(original.path.read_text(encoding="utf-8"))
        raw["categories"].append("Verborgene PS4")
        for entry in raw["emulators"]:
            if entry["id"] in {"shadps4", "ps4-pkg-tool"}:
                entry.update(hidden=True, kategorie="Verborgene PS4")
        path = self.root / "catalog.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        self.catalog = Catalog(path)
        self.service = HubService(self.catalog, self.root / "data")
        self.service.settings.set("system_report", {"cpu_cores": 8, "ram_gb": 16, "gpu_score": 3})
        self.service.system_report = self.service.settings.get("system_report")
        folder = self.root / "Eigene Spiele"
        folder.mkdir()
        for name in ("Eigenes.pkg", "Sichtbares.nes", "Eigenes ELF.elf"):
            (folder / name).write_bytes(b"synthetische eigene Datei")
        # Simulate previously saved PS4 games and settings before hiding the entries.
        self.service.settings.set("show_hidden", True)
        self.service.library.scan([folder], Mock(), Mock(), threading.Event())
        native_game = next(game for game in self.service.library.games if Path(game["path"]).suffix == ".elf")
        self.service.library.set_console(native_game["id"], "PlayStation 4")
        self.service.settings.set("favorites", ["shadps4", "ps4-pkg-tool"])
        self.service.settings.touch_emulator("shadps4")
        self.service.set_games_directory(self.catalog.by_id("shadps4"), folder)
        self.service.settings.set("show_hidden", False)
        self.saved_library = self.service.library.path.read_bytes()
        self.saved_games = self.service.library.games
        self.saved_folders = self.service.settings.get("games_dir")
        self.window = MainWindow(self.service, self.catalog)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        HiddenCatalogTests.close_logger(self.service)
        self.temp.cleanup()

    def category_item(self, key):
        return next(self.window.navigation.item(row) for row in range(self.window.navigation.count())
                    if self.window.navigation.item(row).data(Qt.ItemDataRole.UserRole) == key)

    def test_hidden_ps4_never_appears_in_cards_search_home_library_couch_or_controller_list(self):
        self.assertTrue(self.category_item("Verborgene PS4").isHidden())
        self.assertEqual(self.window.visible_entries, [])  # All saved home selections are hidden.
        self.assertTrue(self.window.cards["shadps4"].isHidden())
        self.assertTrue(self.window.recent_cards["shadps4"].isHidden())
        self.window.select_page("all")
        self.window.search.setText("PS4")
        self.window._filter_cards()
        self.assertEqual(self.window.visible_entries, [])
        page = self.window.library_page
        self.assertEqual([game["name"] for game in page.visible_games], ["Sichtbares"])
        self.assertEqual(page.console_filter.findData("PlayStation 4"), -1)
        self.assertNotIn("PS4", page.usage_hint.text())
        with patch.object(self.service, "compatibility", wraps=self.service.compatibility) as assess:
            self.window.refresh()
        self.assertFalse(any(call.args[0]["id"] in {"shadps4", "ps4-pkg-tool"} for call in assess.call_args_list))
        couch = CouchDialog(self.service, backend=Mock())
        controller = ControllerDialog(self.service, backend=Mock(poll=Mock(return_value=[]), unavailable_reason=""))
        try:
            self.assertNotIn("PlayStation 4", [tile.title for tile in couch._tiles])
            ids = [controller.emulator_combo.itemData(index) for index in range(controller.emulator_combo.count())]
            self.assertNotIn("shadps4", ids)
            self.assertNotIn("ps4-pkg-tool", ids)
        finally:
            couch.reject()
            controller.reject()
        self.assertEqual(self.service.library.games, self.saved_games)
        self.assertEqual(self.service.library.path.read_bytes(), self.saved_library)
        self.assertEqual(self.service.settings.get("games_dir"), self.saved_folders)

    def test_settings_option_restores_both_ps4_entries_saved_games_and_category_immediately(self):
        self.assertFalse(self.window.settings_page.show_hidden.isChecked())
        self.window.settings_page.show_hidden.setChecked(True)
        self.assertTrue(self.service.settings.get("show_hidden"))
        self.assertFalse(self.category_item("Verborgene PS4").isHidden())
        self.window.search.clear()
        self.window.select_page("Verborgene PS4")
        self.assertEqual({entry["id"] for entry in self.window.visible_entries}, {"shadps4", "ps4-pkg-tool"})
        self.assertEqual(len(self.window.library_page.visible_games), 3)
        self.assertGreaterEqual(self.window.library_page.console_filter.findData("PlayStation 4"), 0)
        controller = ControllerDialog(self.service, backend=Mock(poll=Mock(return_value=[]), unavailable_reason=""))
        try:
            self.assertGreaterEqual(controller.emulator_combo.findData("shadps4"), 0)
            self.assertEqual(controller.emulator_combo.findData("ps4-pkg-tool"), -1)
        finally:
            controller.reject()
        self.window.settings_page.show_hidden.setChecked(False)
        self.assertTrue(self.category_item("Verborgene PS4").isHidden())
        self.assertEqual(self.window._category(), "all")
        self.assertEqual(self.service.library.games, self.saved_games)
        self.assertEqual(self.service.library.path.read_bytes(), self.saved_library)
        self.assertEqual(self.service.settings.favorites, ["shadps4", "ps4-pkg-tool"])
        self.assertEqual(self.service.settings.recent_emulators[0]["id"], "shadps4")

    def test_hidden_folder_scan_does_not_rewrite_saved_ps4_metadata(self):
        before = deepcopy([game for game in self.service.library.games if game["console"] == "PlayStation 4"])
        self.service.library.scan([], Mock(), Mock(), threading.Event())
        after = [game for game in self.service.library.games if game["console"] == "PlayStation 4"]
        self.assertEqual(after, before)
        self.assertEqual(self.service.settings.get("games_dir"), self.saved_folders)


class WinUAEUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog = Catalog()
        self.entry = self.catalog.by_id("winuae")
        self.service = HubService(self.catalog, self.root / "data")
        self.service.settings.set("system_report", {"cpu_cores": 8, "ram_gb": 16, "gpu_score": 3})
        self.service.system_report = self.service.settings.get("system_report")
        folder = self.root / "Eigene Amiga-Dateien"
        folder.mkdir()
        for name in ("Eigene Disk.adf", "Eigene Konfiguration.uae"):
            (folder / name).write_bytes(b"synthetische eigene Datei")
        self.service.library.scan([folder], Mock(), Mock(), threading.Event())
        emulator = self.root / "WinUAE"
        emulator.mkdir()
        (emulator / self.entry["exe"]).write_bytes(windows_executable())
        self.service.register_manual(self.entry, emulator)
        self.window = MainWindow(self.service, self.catalog)
        self.window.show()
        self.window.select_page("library")
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        HiddenCatalogTests.close_logger(self.service)
        self.temp.cleanup()

    def test_images_show_configuration_status_and_safe_start_hint_while_uae_stays_ready(self):
        from core.library import WINUAE_CONFIG_STATUS
        self.assertIn("kein Kickstart-ROM", self.window.cards["winuae"].start_note_label.text())
        page = self.window.library_page
        group = page.tree.topLevelItem(0)
        items = {group.child(index).text(0): group.child(index) for index in range(group.childCount())}
        image, config = items["Eigene Disk"], items["Eigene Konfiguration"]
        self.assertEqual(image.text(4), WINUAE_CONFIG_STATUS)
        self.assertEqual(image.toolTip(4), WINUAE_CONFIG_STATUS)
        self.assertEqual(config.text(4), "Bereit")
        self.assertTrue(any(WINUAE_CONFIG_STATUS in page.grid.item(index).text() for index in range(page.grid.count())))
        image_id = image.data(0, Qt.ItemDataRole.UserRole)
        config_id = config.data(0, Qt.ItemDataRole.UserRole)
        with patch.object(self.service, "launch_game") as launch:
            self.window.launch_game(image_id)
        launch.assert_not_called()
        self.assertIn(WINUAE_CONFIG_STATUS, self.window.notice_label.text())
        self.assertIn(".uae", self.window.notice_label.text())
        with patch.object(self.service, "launch_game") as launch:
            self.window.launch_game(config_id)
        launch.assert_called_once_with(config_id, "winuae")
        couch = CouchDialog(self.service, backend=Mock())
        try:
            couch._show_games(self.entry["konsole"])
            self.assertTrue(any(tile.subtitle == WINUAE_CONFIG_STATUS for tile in couch._tiles))
        finally:
            couch.reject()

    def test_cd_image_assigned_to_amiga_shows_configuration_hint_before_launch(self):
        image = self.root / "Eigene Amiga-Dateien" / "Eigene CD.cue"
        image.write_bytes(b"synthetische eigene Datei")
        self.service.library.scan([image.parent], Mock(), Mock(), threading.Event())
        game = next(game for game in self.service.library.games if Path(game["path"]).suffix == ".cue")
        self.assertIsNone(game["console"])

        def assign(identifier):
            self.service.library.set_console(identifier, self.entry["konsole"])
            self.window.refresh()
            return True

        with patch.object(self.window, "assign_game_console", side_effect=assign), patch.object(self.service, "launch_game") as launch:
            self.window.launch_game(game["id"])
        launch.assert_not_called()
        self.assertIn("Über WinUAE-Konfiguration zu starten", self.window.notice_label.text())


if __name__ == "__main__":
    unittest.main()
