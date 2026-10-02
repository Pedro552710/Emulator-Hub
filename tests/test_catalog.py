import json
from pathlib import Path
import unittest

from core.catalog import Catalog, CatalogError
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


if __name__ == "__main__":
    unittest.main()
