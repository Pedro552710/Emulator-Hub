import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from core.errors import HubError
from core.github import GitHubClient
from core.security import URLPolicy
from core.storage import read_installed, write_installed
from tests.helpers import Response


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "installed.json"
        self.record = {"emulator": {"path": "C:/managed/emulator", "exe_path": "C:/managed/emulator/program.exe", "version": "v1.0", "date": "2026-10-01"}}

    def test_missing_file_and_unicode_round_trip(self):
        self.assertEqual(read_installed(self.path), {})
        self.record["emulator"]["path"] = "C:/Nutzer/Müller/emulator"
        write_installed(self.path, self.record)
        self.assertEqual(read_installed(self.path), self.record)
        self.assertEqual(list(self.path.parent.glob("installed-*.tmp")), [])

    def test_malformed_or_wrong_shape_state_is_rejected_without_modification(self):
        for content in ("{truncated", "[]", '{"e": 1}', '{"e": {"path": "C:/x"}}', '{"e": {"path": "p", "exe_path": "p/e.exe", "version": 4, "date": "today"}}'):
            self.path.write_text(content, encoding="utf-8")
            with self.subTest(content=content), self.assertRaises(HubError):
                read_installed(self.path)
            self.assertEqual(self.path.read_text(encoding="utf-8"), content)

    def test_failed_atomic_replace_preserves_original_and_cleans_temporary_file(self):
        write_installed(self.path, self.record)
        original = self.path.read_bytes()
        replacement = json.loads(json.dumps(self.record))
        replacement["emulator"]["version"] = "v2.0"
        with patch("core.storage.os.replace", side_effect=OSError("file locked")), self.assertRaises(HubError):
            write_installed(self.path, replacement)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob("installed-*.tmp")), [])


class GitHubTests(unittest.TestCase):
    def setUp(self):
        self.policy = URLPolicy(["https://github.com/official/emulator", "https://github.com/official/other"])
        self.client = GitHubClient(self.policy)
        self.entry = {"github_repo": "official/emulator", "download_muster": r"emulator-win-x64\.zip"}
        self.asset = {"name": "emulator-win-x64.zip", "browser_download_url": "https://github.com/official/emulator/releases/download/v1/emulator-win-x64.zip"}
        self.release = {"tag_name": "v1", "draft": False, "prerelease": False, "assets": [self.asset]}

    def test_latest_release_is_cached_and_force_refreshes(self):
        with patch.object(self.policy, "get", return_value=Response(payload=self.release)) as get:
            self.assertEqual(self.client.latest("official/emulator"), self.release)
            self.client.latest("official/emulator")
            self.assertEqual(get.call_count, 1)
            self.client.latest("official/emulator", force=True)
            self.assertEqual(get.call_count, 2)
        self.assertEqual(self.client.asset(self.entry, self.release), self.asset)

    def test_prerelease_draft_and_incomplete_release_never_become_stable(self):
        for release in (
            {**self.release, "prerelease": True}, {**self.release, "draft": True},
            {**self.release, "tag_name": ""}, {**self.release, "assets": {}}, [],
        ):
            with self.subTest(release=release), patch.object(self.policy, "get", return_value=Response(payload=release)), self.assertRaises(HubError):
                self.client.latest("official/emulator", force=True)
        self.assertEqual(self.client._cache, {})

    def test_ambiguous_missing_or_foreign_assets_are_rejected(self):
        foreign = {**self.asset, "browser_download_url": "https://github.com/official/other/releases/download/v1/emulator-win-x64.zip"}
        for assets in ([], [self.asset, dict(self.asset)], [foreign], [{**self.asset, "name": "emulator-linux-x64.zip"}]):
            with self.subTest(assets=assets), self.assertRaises(HubError):
                self.client.asset(self.entry, {**self.release, "assets": assets})

    def test_invalid_repository_is_rejected_before_network_call(self):
        for repo in ("https://github.com/official/emulator", "official/emulator/extra", "../emulator", "", None):
            with self.subTest(repo=repo), patch.object(self.policy, "get") as get, self.assertRaises(HubError):
                self.client.latest(repo)
            get.assert_not_called()


if __name__ == "__main__":
    unittest.main()
