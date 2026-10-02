import json
from pathlib import Path
import os
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from core.catalog import Catalog
from core.errors import Cancelled, HubError
from core.library import LibraryStore
from core.settings import SettingsStore


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root / "Eigene Spiele"
        self.folder.mkdir()
        self.data = self.root / "data"
        self.catalog = Catalog()
        self.settings = SettingsStore(self.data)
        self.library = LibraryStore(self.data, self.catalog, self.settings)
        self.progress = Mock()
        self.log = Mock()
        self.cancel = threading.Event()

    def scan(self, roots=None, progress=None):
        return self.library.scan(roots or [self.folder], progress or self.progress, self.log, self.cancel)

    def write_game(self, name, content=b"eigene Datei"):
        path = self.folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def test_scan_deduplicates_overlapping_roots_and_leaves_files_untouched(self):
        original = {self.write_game("Unterordner/Spiel.NES"): b"eigene Datei",
                    self.write_game("Disc.iso"): b"eigene Datei",
                    self.write_game("Archiv.zip"): b"eigene Datei"}
        self.write_game("Text.txt")
        result = self.scan([self.folder, self.folder / "Unterordner", self.folder])
        self.assertEqual(result, {"added": 3, "total": 3, "ambiguous": 2, "missing": 0, "errors": []})
        games = {Path(g["path"]).name: g for g in self.library.games}
        self.assertEqual(games["Spiel.NES"]["console"], "NES")
        self.assertIsNone(games["Disc.iso"]["console"])
        self.assertIsNone(games["Archiv.zip"]["console"])
        for path, content in original.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(self.progress.call_args.args[0], 100)
        self.assertEqual(list(self.data.glob("*.tmp")), [])

    def test_manual_assignment_favorites_and_last_played_survive_scan_and_missing_file(self):
        disc = self.write_game("Mein Spiel.iso")
        self.scan()
        game = self.library.games[0]
        self.library.set_console(game["id"], "PSP")
        self.assertTrue(self.library.toggle_favorite(game["id"]))
        self.library.touch_game(game["id"], "ppsspp")
        previous = self.library.get_game(game["id"])
        self.assertEqual(self.scan()["added"], 0)
        self.assertEqual(self.library.get_game(game["id"]), previous)
        disc.unlink()
        result = self.scan()
        self.assertEqual(result["missing"], 1)
        reloaded = LibraryStore(self.data, self.catalog, self.settings).get_game(game["id"])
        self.assertTrue(reloaded["missing"])
        self.assertTrue(reloaded["favorite"])
        self.assertEqual(reloaded["last_played"], previous["last_played"])
        self.assertEqual(reloaded["console"], "PSP")
        self.assertEqual(reloaded["emulator_id"], "ppsspp")

    def test_cancellation_keeps_previous_library_and_does_not_commit_partial_scan(self):
        self.write_game("Alt.nes")
        self.scan()
        saved = self.library.path.read_bytes()
        games = self.library.games
        self.write_game("Neu.gba")
        self.cancel.set()
        with self.assertRaises(Cancelled):
            self.scan()
        self.assertEqual(self.library.path.read_bytes(), saved)
        self.assertEqual(self.library.games, games)

    def test_missing_folder_does_not_abort_other_roots(self):
        self.write_game("Spiel.nds")
        result = self.scan([self.root / "fehlt", self.folder])
        self.assertEqual(result["added"], 1)
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("Spielordner", result["errors"][0])

    def test_junction_or_symlink_cannot_scan_outside_selected_root(self):
        outside = self.root / "Nicht gewählt"
        outside.mkdir()
        private = outside / "Privat.nes"
        private.write_bytes(b"unveraendert")
        link = self.folder / "Verknuepfung"
        if os.name == "nt":
            result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                                    capture_output=True, text=True, shell=False)
            if result.returncode:
                self.skipTest("NTFS-Junction konnte nicht angelegt werden.")
        else:
            link.symlink_to(outside, target_is_directory=True)
        self.write_game("Sichtbar.nes")
        result = self.scan()
        self.assertEqual(result["total"], 1)
        self.assertEqual(self.library.games[0]["name"], "Sichtbar")
        self.assertEqual(private.read_bytes(), b"unveraendert")
        # Auch die direkte Auswahl einer Verknüpfung wird abgelehnt.
        self.assertEqual(len(self.scan([link])["errors"]), 1)

    def test_data_directory_is_not_catalogued_as_games(self):
        self.data.mkdir(exist_ok=True)
        (self.data / "backup.zip").write_bytes(b"eigene Sicherung")
        result = self.scan([self.root])
        self.assertEqual(result["total"], 0)
        self.assertTrue((self.data / "backup.zip").is_file())

    def test_local_extension_configuration_and_folder_settings(self):
        config = self.data / "configs/extensions.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"schema_version": 1, "extensions": {".spiel": "NES"}}), encoding="utf-8")
        self.library = LibraryStore(self.data, self.catalog, self.settings)
        self.write_game("Eigene.spiel")
        self.write_game("Nicht konfiguriert.nes")
        self.library.set_roots([self.folder, self.folder])
        self.assertEqual(self.settings.get("game_folders"), [str(self.folder)])
        self.assertEqual(self.scan()["added"], 1)
        self.assertEqual(self.library.games[0]["console"], "NES")

    def test_mutation_during_scan_is_preserved_and_game_snapshots_cannot_mutate_store(self):
        self.write_game("Spiel.nes")
        self.scan()
        game_id = self.library.games[0]["id"]
        changed = False

        def progress(value, message):
            nonlocal changed
            if not changed:
                changed = True
                self.library.toggle_favorite(game_id)

        self.scan(progress=progress)
        snapshot = self.library.games
        self.assertTrue(snapshot[0]["favorite"])
        snapshot[0]["favorite"] = False
        self.assertTrue(self.library.get_game(game_id)["favorite"])

    def test_corrupt_library_is_never_overwritten_and_failed_write_preserves_memory(self):
        self.write_game("Spiel.nes")
        self.scan()
        game_id = self.library.games[0]["id"]
        with patch("core.library.write_json", side_effect=HubError("Speicher voll")), self.assertRaises(HubError):
            self.library.toggle_favorite(game_id)
        self.assertFalse(self.library.get_game(game_id)["favorite"])
        self.library.path.write_text("{kaputt", encoding="utf-8")
        with self.assertRaises(HubError):
            LibraryStore(self.data, self.catalog, self.settings)
        self.assertEqual(self.library.path.read_text(encoding="utf-8"), "{kaputt")

    def test_launch_touches_only_successful_games_and_requires_console(self):
        self.write_game("Spiel.iso")
        self.scan()
        game_id = self.library.games[0]["id"]
        self.library.launcher = Mock()
        with self.assertRaises(HubError):
            self.library.launch_game(game_id)
        self.library.launcher.assert_not_called()
        self.library.set_console(game_id, "PSP")
        self.library.launcher.side_effect = HubError("Nicht installiert")
        with self.assertRaises(HubError):
            self.library.launch_game(game_id, "ppsspp")
        self.assertEqual(self.library.get_game(game_id)["last_played"], "")
        self.library.launcher.side_effect = None
        self.library.launch_game(game_id, "ppsspp")
        self.assertTrue(self.library.get_game(game_id)["last_played"])
        self.assertEqual(self.library.get_game(game_id)["emulator_id"], "ppsspp")


if __name__ == "__main__":
    unittest.main()
