import json
import os
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from core.catalog import Catalog, CatalogError
from core.errors import Cancelled, HubError
from core.profiles import assert_not_game_file, check_bios, game_protection, profile_paths
from tests.helpers import TemporaryDirectory, make_catalog


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.emulator = self.root / "emulator" / "nested"
        self.emulator.mkdir(parents=True)
        self.record = {"path": str(self.root / "emulator"), "exe_path": str(self.emulator / "emulator.exe")}
        self.entry = {"id": "test-emulator", "bios": [{"label": "Regionaler BIOS-Dump", "root": "emulator", "directory": "bios",
                      "filenames": ["scph5500.bin", "scph5501.bin"], "any_of": True, "required": True}],
                      "backup_paths": [{"label": "Spielstände", "root": "emulator", "directory": "saves", "type": "directory"}]}

    def test_bios_alternatives_and_nonempty_check(self):
        rows = check_bios(self.entry, self.record, self.root)
        self.assertEqual(rows[0]["status"], "fehlt")
        (self.emulator / "bios").mkdir()
        bios = self.emulator / "bios" / "scph5501.bin"
        bios.write_bytes(b"")
        self.assertEqual(check_bios(self.entry, self.record, self.root)[0]["status"], "fehlt")
        bios.write_bytes(b"own-dump")
        self.assertEqual(check_bios(self.entry, self.record, self.root)[0]["status"], "vorhanden")

    def test_own_named_file_replaces_default_checks(self):
        own = self.root / "Mein eigener Dump.rom0"
        own.write_bytes(b"own")
        settings = {"bios_overrides": {"test-emulator": [{"path": str(own), "label": "Eigene PS2"}]}}
        rows = check_bios(self.entry, self.record, self.root, settings)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "Eigene PS2")
        self.assertEqual(rows[0]["status"], "vorhanden")
        settings["bios_overrides"]["test-emulator"][0]["path"] = "relative.bin"
        with self.assertRaises(HubError):
            check_bios(self.entry, self.record, self.root, settings)

    def test_cancelled_bios_check(self):
        event = threading.Event()
        event.set()
        with self.assertRaises(Cancelled):
            check_bios(self.entry, self.record, self.root, cancel_event=event)

    def test_nested_executable_root_and_environment_roots(self):
        self.assertEqual(profile_paths(self.entry, self.record, self.root)[0]["path"], self.emulator / "saves")
        self.entry["backup_paths"][0].update(root="roamingappdata", directory="OwnEmulator/settings")
        with patch.dict(os.environ, {"APPDATA": str(self.root / "roaming")}):
            self.assertEqual(profile_paths(self.entry, self.record, self.root)[0]["path"], self.root / "roaming/OwnEmulator/settings")

    def test_broad_and_overlapping_custom_paths_rejected(self):
        for paths in ([str(self.emulator)], [str(self.root / "saves"), str(self.root / "saves/subdir")]):
            settings = {"profile_overrides": {"test-emulator": {"backup_paths": paths}}}
            with self.subTest(paths=paths), self.assertRaises(HubError):
                profile_paths(self.entry, self.record, self.root, settings)

    def test_redirected_windows_documents_used(self):
        self.entry["backup_paths"][0].update(root="documents", directory="OwnEmulator/saves")
        redirected = self.root / "OneDrive" / "Dokumente"
        with patch("core.profiles._windows_documents", return_value=redirected):
            self.assertEqual(profile_paths(self.entry, self.record, self.root)[0]["path"], redirected / "OwnEmulator/saves")

    def test_existing_native_portable_marker_only(self):
        spec = self.entry["backup_paths"][0]
        spec.update(root="documents", directory="OwnEmulator/saves",
                    portable={"marker": "portable.txt", "directory": "User/saves"})
        before = set(self.emulator.iterdir())
        with patch("core.profiles._windows_documents", return_value=self.root / "documents"):
            self.assertEqual(profile_paths(self.entry, self.record, self.root)[0]["path"], self.root / "documents/OwnEmulator/saves")
        self.assertEqual(set(self.emulator.iterdir()), before)
        (self.emulator / "portable.txt").write_text("", encoding="utf-8")
        self.assertEqual(profile_paths(self.entry, self.record, self.root)[0]["path"], self.emulator / "User/saves")
        self.assertFalse((self.emulator / "User").exists())

    def test_pcsx2_native_marker_profile_path(self):
        self.entry["backup_paths"][0].update(root="documents", directory="PCSX2/memcards",
            portable={"markers": ["portable.txt", "portable.ini"], "directory": "memcards", "path_from_marker": True})
        (self.emulator / "portable.ini").write_bytes(b"")
        (self.emulator / "portable.txt").write_text("local-profile", encoding="utf-8")
        self.assertEqual(profile_paths(self.entry, self.record, self.root)[0]["path"], self.emulator / "local-profile/memcards")
        (self.emulator / "portable.txt").write_text(str(self.root / "own-profile"), encoding="utf-8")
        self.assertEqual(profile_paths(self.entry, self.record, self.root)[0]["path"], self.root / "own-profile/memcards")

    def test_native_directory_marker_and_duplicate_profile(self):
        self.entry["backup_paths"] = [
            {"label": "Aktuell", "root": "roamingappdata", "directory": "OwnEmulator/settings.ini", "type": "file",
             "portable": {"marker": "user", "marker_type": "directory", "directory": "user/settings.ini"}},
            {"label": "Portabel", "root": "emulator", "directory": "user/settings.ini", "type": "file"},
        ]
        (self.emulator / "user").mkdir()
        rows = profile_paths(self.entry, self.record, self.root)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["path"], self.emulator / "user/settings.ini")

    def test_save_inside_game_folder_allowed_but_game_folder_rejected(self):
        games = self.root / "Eigene Spiele"
        games.mkdir()
        save = games / "Titel.sav"
        save.write_bytes(b"Spielstand")
        settings = {"game_folders": [str(games)], "profile_overrides": {self.entry["id"]: {"backup_paths": [str(save)]}}}
        self.assertEqual(profile_paths(self.entry, self.record, self.root, settings)[0]["path"], save)
        settings["profile_overrides"][self.entry["id"]]["backup_paths"] = [str(games / "saves")]
        self.assertEqual(profile_paths(self.entry, self.record, self.root, settings)[0]["path"], games / "saves")
        settings["profile_overrides"][self.entry["id"]]["backup_paths"] = [str(games)]
        with self.assertRaisesRegex(HubError, "Spieleordner"):
            profile_paths(self.entry, self.record, self.root, settings)

    def test_known_library_game_and_obvious_extension_are_protected(self):
        game = self.emulator / "saves" / "Eigener Titel.bin"
        (self.root / "library.json").write_text(json.dumps({"schema_version": 1, "games": [{"path": str(game)}]}), encoding="utf-8")
        protection = game_protection(self.root)
        for path in (game, self.root / "Titel.nes"):
            with self.subTest(path=path), self.assertRaisesRegex(HubError, "Spiel-Datei"):
                assert_not_game_file(path, protection)
        assert_not_game_file(self.root / "prefs.bin", protection)
        assert_not_game_file(self.root / "Titel.srm", protection)
        with self.assertRaisesRegex(HubError, "Bibliothek"):
            profile_paths(self.entry, self.record, self.root)

    def test_malformed_own_settings_have_readable_errors(self):
        for settings in ({"bios_overrides": None}, {"profile_overrides": {self.entry["id"]: "broken"}}, {"game_folders": "relative"}):
            with self.subTest(settings=settings), self.assertRaises(HubError):
                profile_paths(self.entry, self.record, self.root, settings)

    def test_catalog_rejects_unsafe_optional_profile_fields(self):
        _, entry = make_catalog(self.root)
        path = self.root / "catalog.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for fields in (
            {"launch_args": "{game}"},
            {"launch_args": ["{game.__class__}"]},
            {"launch_profiles": {"../other.exe": ["{game}"]}},
            {"bios": [{"label": "BIOS", "root": "emulator", "directory": "../outside", "filenames": ["bios.bin"], "required": True}]},
            {"bios": [{"label": "BIOS", "root": "emulator", "directory": "bios", "filenames": ["../bios.bin"], "required": True}]},
            {"backup_paths": [{"label": "Alles", "root": "emulator", "directory": ".", "type": "directory"}]},
            {"backup_paths": [{"label": "Save", "root": "emulator", "directory": "saves", "portable": {"marker": "../outside", "directory": "saves"}}]},
            {"backup_paths": [{"label": "Save", "root": "emulator", "directory": "saves", "portable": {"marker": "portable.txt", "directory": "."}}]},
            {"backup_paths": [{"label": "Save", "root": "emulator", "directory": "saves", "portable": {"marker": "user", "markers": ["user"], "directory": "saves"}}]},
            {"backup_paths": [{"label": "Save", "root": "emulator", "directory": "saves", "portable": {"marker": "settings.json", "directory": "saves", "path_from_marker": True}}]},
        ):
            data = json.loads(json.dumps(original))
            data["emulators"][0].update(fields)
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.subTest(fields=fields), self.assertRaises(CatalogError):
                Catalog(path)


if __name__ == "__main__":
    unittest.main()
