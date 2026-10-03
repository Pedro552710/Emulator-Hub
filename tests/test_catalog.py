import json
from pathlib import Path
import unittest

from core.catalog import Catalog, CatalogError, REQUIRED_TEXT_FIELDS
from core.security import URLPolicy
from tests.helpers import TemporaryDirectory, make_catalog


class CatalogSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.catalog, self.entry = make_catalog(self.temp.name)
        self.path = Path(self.temp.name) / "catalog.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def reject_changes(self, changes):
        self.data["emulators"][0].update(changes)
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        with self.assertRaises(CatalogError):
            Catalog(self.path)

    def test_path_traversal_id_is_rejected_before_it_can_become_installation_folder(self):
        self.reject_changes({"id": "../external"})

    def test_unapproved_source_and_executable_paths_are_rejected(self):
        for changes in (
            {"official_url": "http://github.com/official/emulator"},
            {"official_url": "https://github.com/official/emulator-malware"},
            {"github_repo": "unofficial/emulator"},
            {"exe": "../program.exe"},
            {"exe": "C:\\program.exe"},
            {"exe": "program.exe:stream"},
        ):
            self.data["emulators"][0] = dict(self.entry)
            with self.subTest(changes=changes):
                self.reject_changes(changes)

    def test_catalog_requires_legal_notice_and_unique_ids(self):
        self.reject_changes({"hinweis": ""})
        self.data["emulators"] = [dict(self.entry), dict(self.entry)]
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        with self.assertRaises(CatalogError):
            Catalog(self.path)


class PublishedCatalogTests(unittest.TestCase):
    PROJECT = Path(__file__).resolve().parents[1]

    def setUp(self):
        self.catalog = Catalog(self.PROJECT / "catalog.json")
        self.entry = self.catalog.by_id("winuae")

    def test_winuae_is_complete_and_uses_documented_stable_x64_configuration(self):
        for field in REQUIRED_TEXT_FIELDS:
            with self.subTest(field=field):
                self.assertTrue(self.entry[field].strip())
        self.assertEqual(len(self.catalog.items), 25)
        self.assertEqual(len(self.catalog.categories), 8)
        self.assertEqual(len([entry for entry in self.catalog.items if not entry.get("hidden", False)]), 23)
        self.assertEqual(self.entry["hersteller"], "Commodore / Amiga")
        self.assertEqual(self.entry["kategorie"], "Commodore / Amiga")
        self.assertEqual(self.entry["konsole"], "Amiga (A500, A1200, CD32 …)")
        self.assertEqual(self.entry["emulator"], "WinUAE")
        self.assertEqual(self.entry["plattformen"], "Windows")
        self.assertEqual(self.entry["pc_anforderung"], "Niedrig")
        self.assertEqual(self.entry["install_methode"], "auto_direct")
        self.assertEqual(self.entry["direct_resolver"], "winuae")
        self.assertEqual(self.entry["official_url"], "https://www.winuae.net/download/")
        self.assertEqual(self.entry["direct_url"], self.entry["official_url"])
        self.assertEqual(self.entry["archive_type"], "zip")
        self.assertEqual(self.entry["exe"], "winuae64.exe")
        self.assertEqual(self.entry["launch_args"], ["-f", "{game}", "-s", "use_gui=no"])
        self.assertEqual(self.entry["launch_extensions"], [".uae"])
        self.assertIn("über WinUAE-Konfiguration zu starten", self.entry["launch_note"])
        self.assertNotIn("github_repo", self.entry)
        self.assertNotIn("direct_version", self.entry)
        self.assertIsNone(self.entry["verified_asset_sha256"])
        self.assertNotIn("sha256", self.entry)
        self.assertEqual(self.entry["bios"], [])
        self.assertIn("Kickstart", self.entry["bios_note"])
        self.assertIn("lizenziert", self.entry["hinweis"])
        self.assertIn("kein Kickstart-ROM", self.entry["start_note"])
        for excluded_download in ("Kickstart-ROMs", "Spiele", "Workbench-Dateien"):
            self.assertIn(excluded_download, self.entry["hinweis"])

    def test_winuae_whitelist_keeps_exact_download_path_and_rejects_unrelated_files(self):
        policy = URLPolicy(self.catalog.official_sources)
        for source in ("https://www.winuae.net/", "https://download.abime.net/winuae/releases/"):
            self.assertIn(source, self.catalog.official_sources)
        self.assertTrue(policy.allows("https://download.abime.net/winuae/releases/WinUAE6030_x64.zip"))
        for unapproved in (
            "https://download.abime.net/roms/kickstart.rom",
            "https://download.abime.net/games/example.adf",
            "https://download.abime.net/winuae/releases-unrelated/WinUAE6030_x64.zip",
            "https://download.abime.net/winuae/betas/WinUAE6100_x64.zip",
            "https://www.winuae.net.evil.invalid/download/",
        ):
            with self.subTest(unapproved=unapproved):
                self.assertFalse(policy.allows(unapproved))
        for field in ("bios_url", "kickstart_url", "rom_url", "game_url", "workbench_url"):
            self.assertNotIn(field, self.entry)

    def test_excel_import_reproduces_entire_catalog_including_hidden_flags(self):
        from tools.import_catalog import import_workbook

        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "catalog.json"
            count = import_workbook(self.PROJECT / "docs/emulatoren_mit_downloadanleitungen.xlsx",
                                    output, self.PROJECT / "tools/catalog_enrichment.json")
            self.assertEqual(count, 25)
            self.assertEqual(output.read_bytes(), self.catalog.path.read_bytes())
        for identifier in ("shadps4", "ps4-pkg-tool"):
            self.assertIs(self.catalog.by_id(identifier)["hidden"], True)

    def test_amiga_endings_and_requirement_match_catalog(self):
        extensions = json.loads((self.PROJECT / "configs/extensions.json").read_text(encoding="utf-8"))["extensions"]
        for suffix in (".adf", ".adz", ".dms", ".ipf", ".hdf", ".lha", ".uae"):
            with self.subTest(suffix=suffix):
                self.assertEqual(extensions[suffix], self.entry["konsole"])
        for suffix in (".cue", ".iso"):
            self.assertIsInstance(extensions[suffix], list)
            self.assertIn(self.entry["konsole"], extensions[suffix])
        requirements = json.loads((self.PROJECT / "configs/system_requirements.json").read_text(encoding="utf-8"))
        self.assertIn(self.entry["pc_anforderung"], requirements["levels"])


if __name__ == "__main__":
    unittest.main()
