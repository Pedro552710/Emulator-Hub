import hashlib
import io
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

from core.catalog import Catalog, CatalogError, LEGAL_NOTICE
from core.errors import HubError
from core.github import GitHubClient
from core.installer import HubService
from core.security import URLPolicy
from tests.helpers import TemporaryDirectory, Response, windows_executable


PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY = "pearlxcore/PS4PKGTool"
SOURCE = f"https://github.com/{REPOSITORY}"
WINUAE_SOURCES = {"https://www.winuae.net/", "https://download.abime.net/winuae/releases/"}
ASSET_NAME = "PS4-PKG-Tool-v1.8.0.zip"
TAG = "v1.8.0"
# Sources present before adding this helper, including the already reviewed QTLauncher.
EXISTING_SOURCES = {
    "https://www.mesen.ca/", "https://github.com/nesdev-org/MesenCE",
    "https://github.com/bsnes-emu/bsnes", "https://github.com/snes9xgit/snes9x",
    "https://sameboy.github.io/", "https://github.com/LIJI32/SameBoy",
    "https://mgba.io/", "https://github.com/mgba-emu/mgba",
    "https://www.mupen64plus.org/", "https://github.com/mupen64plus/mupen64plus-core",
    "https://dolphin-emu.org/", "https://dl.dolphin-emu.org/",
    "https://github.com/melonDS-emu/melonDS", "https://azahar-emu.org/",
    "https://github.com/azahar-emu/azahar", "https://cemu.info/",
    "https://github.com/cemu-project/Cemu", "https://www.duckstation.org/",
    "https://github.com/stenzek/duckstation", "https://pcsx2.net/",
    "https://github.com/PCSX2/pcsx2", "https://rpcs3.net/",
    "https://github.com/shadps4-emu/shadPS4", "https://shadps4.net/",
    "https://github.com/shadps4-emu/shadps4-qtlauncher", "https://www.ppsspp.org/",
    "https://github.com/hrydgard/ppsspp", "https://vita3k.org/",
    "https://github.com/Vita3K/Vita3K", "https://www.retrodev.com/blastem/",
    "https://github.com/ekeeke/Genesis-Plus-GX", "https://www.retroarch.com/",
    "https://mednafen.github.io/", "https://www.yabasanshiro.com/",
    "https://github.com/flyinghead/flycast", "https://xemu.app/",
    "https://github.com/xemu-project/xemu", "https://xenia.jp/",
    "https://github.com/xenia-canary/xenia-canary", "https://stella-emu.github.io/",
    "https://github.com/stella-emu/stella", "https://github.com/finalburnneo/FBNeo",
    "https://www.mamedev.org/",
}


def helper_entry():
    data = json.loads((PROJECT / "tools/catalog_enrichment.json").read_text(encoding="utf-8"))
    entry = dict(data["entries"]["Sony|PlayStation 4 (Hilfsprogramm)"])
    entry.update(kategorie="Sony PlayStation", hersteller="Sony", konsole="PlayStation 4 (Hilfsprogramm)",
                 plattformen="Windows x64", pc_anforderung="Niedrig")
    entry["hinweis"] = LEGAL_NOTICE + " " + entry["hinweis"]
    return entry


def release_fixture(*, assets=None, digest=None):
    asset = {"name": ASSET_NAME, "browser_download_url": f"{SOURCE}/releases/download/{TAG}/{ASSET_NAME}"}
    if digest:
        asset["digest"] = "sha256:" + digest
    return {"tag_name": TAG, "draft": False, "prerelease": False,
            "assets": [asset] if assets is None else assets}


class PS4ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.entry = helper_entry()
        self.path = self.root / "catalog.json"
        self.raw = {"schema_version": 1, "categories": ["Sony PlayStation"],
                    "official_sources": [SOURCE], "emulators": [self.entry]}
        self.path.write_text(json.dumps(self.raw), encoding="utf-8")
        self.catalog = Catalog(self.path)
        self.service = HubService(self.catalog, self.root / "data")
        self.service.settings.set("show_hidden", True)  # PS4-Funktionen bleiben ausdrücklich testbar.
        self.addCleanup(self.close_logger)
        self.progress = Mock()
        self.log = Mock()
        self.cancel = threading.Event()

    def close_logger(self):
        for handler in list(self.service.logger.handlers):
            handler.close()
            self.service.logger.removeHandler(handler)

    def archive(self):
        body = io.BytesIO()
        with zipfile.ZipFile(body, "w") as archive:
            archive.writestr("tool/PS4 PKG Tool.exe", windows_executable())
        return body.getvalue()

    def test_helper_metadata_and_whitelist_add_only_canonical_repository(self):
        catalog = Catalog(PROJECT / "catalog.json")
        enrichment = json.loads((PROJECT / "tools/catalog_enrichment.json").read_text(encoding="utf-8"))
        for sources in (catalog.official_sources, enrichment["official_sources"]):
            self.assertEqual(set(sources), EXISTING_SOURCES | {SOURCE} | WINUAE_SOURCES)
        entry = catalog.by_id("ps4-pkg-tool")
        self.assertEqual(entry["entry_type"], "utility")
        self.assertNotIn("launch_args", entry)
        self.assertEqual(entry["package_args"], ["{package}"])
        policy = URLPolicy(catalog.official_sources)
        self.assertTrue(policy.allows(SOURCE + "/releases"))
        self.assertFalse(policy.allows("https://github.com/pearlxcore/PS4-PKG-Tool"))
        self.assertFalse(policy.allows("https://github.com/pearlxcore/unrelated"))
        self.assertFalse(policy.allows(SOURCE + "-unsafe"))

    def test_tool_profiles_accept_only_documented_single_path(self):
        for changes in ({"entry_type": "unknown"}, {"launch_args": ["{game}"]},
                        {"package_args": ["--install", "{package}"]}, {"package_args": []}):
            with self.subTest(changes=changes):
                changed = json.loads(json.dumps(self.raw))
                changed["emulators"][0].update(changes)
                self.path.write_text(json.dumps(changed), encoding="utf-8")
                with self.assertRaises(CatalogError):
                    Catalog(self.path)

    def test_deprecation_and_setup_steps_are_validated_before_use(self):
        original = json.loads((PROJECT / "catalog.json").read_text(encoding="utf-8"))
        for identifier, changes in (
            ("shadps4", {"deprecated": "yes"}),
            ("shadps4", {"deprecated_note": ""}),
            ("shadps4", {"replacement_id": "shadps4"}),
            ("shadps4", {"replacement_id": "missing-tool"}),
            ("ps4-pkg-tool", {"ps4_setup_steps": ["Only one step"]}),
            ("ps4-pkg-tool", {"ps4_setup_steps": ["a", "b", "c", "d", ""]}),
        ):
            changed = json.loads(json.dumps(original))
            next(entry for entry in changed["emulators"] if entry["id"] == identifier).update(changes)
            self.path.write_text(json.dumps(changed), encoding="utf-8")
            with self.subTest(identifier=identifier, changes=changes), self.assertRaises(CatalogError):
                Catalog(self.path)

    def test_stable_asset_selection_with_simulated_api_response(self):
        release = release_fixture()
        release["assets"].extend([
            {"name": "PS4-PKG-Tool-v1.8.0-linux.zip"},
            {"name": "PS4-PKG-Tool-v1.8.0-arm64.zip"},
            {"name": "PS4-PKG-Tool-v1.8.0-source.zip"},
        ])
        with patch.object(self.service.policy, "get", return_value=Response(payload=release)) as get:
            resolved = self.service.github.latest(REPOSITORY)
        self.assertEqual(get.call_args.args[0], f"https://api.github.com/repos/{REPOSITORY}/releases/latest")
        self.assertEqual(self.service.github.asset(self.entry, resolved)["name"], ASSET_NAME)
        self.assertEqual(resolved["tag_name"], TAG)

    def test_prereleases_and_drafts_never_offer_download(self):
        for flags in ({"prerelease": True}, {"draft": True}):
            release = {**release_fixture(), **flags}
            with self.subTest(flags=flags), patch.object(self.service.policy, "get", return_value=Response(payload=release)), self.assertRaises(HubError):
                self.service.prepare_install(self.entry)
            with patch.object(self.service.github, "latest", return_value=release), self.assertRaises(HubError):
                self.service.prepare_install(self.entry)
        self.assertEqual(self.service._download_previews, {})

    def test_missing_ambiguous_or_foreign_assets_require_manual_instruction(self):
        asset = release_fixture()["assets"][0]
        foreign = {**asset, "browser_download_url": "https://github.com/shadps4-emu/shadPS4/releases/download/v1/tool.zip"}
        client = GitHubClient(URLPolicy([SOURCE, "https://github.com/shadps4-emu/shadPS4"]))
        for assets in ([], [asset, dict(asset)], [foreign]):
            with self.subTest(assets=assets), self.assertRaises(HubError):
                client.asset(self.entry, release_fixture(assets=assets))

    def test_no_download_without_explicit_preview_confirmation(self):
        with patch.object(self.service.github, "latest") as latest, patch.object(self.service, "_download") as download:
            with self.assertRaisesRegex(HubError, "Installationsklick"):
                self.service.install(self.entry, self.progress, self.log, self.cancel)
        latest.assert_not_called()
        download.assert_not_called()

    def test_preview_reports_source_hash_and_required_third_party_notice(self):
        digest = "a" * 64
        with patch.object(self.service.policy, "get", return_value=Response(payload=release_fixture(digest=digest))) as get:
            preview = self.service.prepare_install(self.entry)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(preview.sha256, digest)
        for text in (preview.source, digest, ASSET_NAME, "Drittprogramm", "Antivirus", "unsignierten"):
            self.assertIn(text, preview.notice)
        self.assertEqual(list(self.service.emulator_dir.iterdir()), [])

    def test_missing_published_checksum_requires_manual_instruction_without_download(self):
        with patch.object(self.service.policy, "get", return_value=Response(payload=release_fixture())), patch.object(
            self.service, "_download"
        ) as download, self.assertRaisesRegex(HubError, "keine SHA-256-Prüfsumme"):
            self.service.prepare_install(self.entry)
        download.assert_not_called()
        self.assertEqual(self.service._download_previews, {})

    def test_confirmed_download_is_bound_to_reviewed_release_and_checksum(self):
        body = self.archive()
        release = release_fixture(digest=hashlib.sha256(body).hexdigest())
        release["assets"][0]["size"] = len(body)
        with patch.object(self.service.github, "latest", return_value=release):
            preview = self.service.prepare_install(self.entry)
        with patch.object(self.service.github, "latest") as latest, patch.object(
                self.service.policy, "get", return_value=Response(body)) as get:
            record = self.service.install(self.entry, self.progress, self.log, self.cancel, preview=preview)
        latest.assert_not_called()
        self.assertEqual(get.call_args.args[0], preview.source)
        self.assertEqual(record["sha256"], preview.sha256)
        self.assertEqual(record["version"], preview.version)
        with patch.object(self.service, "_download") as download, self.assertRaises(HubError):
            self.service.install(self.entry, self.progress, self.log, self.cancel, preview=preview)
        download.assert_not_called()

    def test_confirmed_download_rejects_checksum_mismatch(self):
        body = self.archive()
        with patch.object(self.service.github, "latest", return_value=release_fixture(digest="a" * 64)):
            preview = self.service.prepare_install(self.entry)
        with patch.object(self.service.policy, "get", return_value=Response(body)), self.assertRaisesRegex(HubError, "Prüfsumme"):
            self.service.install(self.entry, self.progress, self.log, self.cancel, preview=preview)
        self.assertFalse(self.service.is_installed(self.entry["id"]))

    def test_confirmed_download_keeps_exact_asset_if_catalog_pattern_changes(self):
        body = self.archive()
        release = release_fixture(digest=hashlib.sha256(body).hexdigest())
        release["assets"].append({
            "name": "other.zip", "browser_download_url": f"{SOURCE}/releases/download/{TAG}/other.zip"
        })
        with patch.object(self.service.github, "latest", return_value=release):
            preview = self.service.prepare_install(self.entry)
        self.entry["download_muster"] = r"other\.zip"
        with patch.object(self.service.policy, "get", return_value=Response(body)) as get:
            self.service.install(self.entry, self.progress, self.log, self.cancel, preview=preview)
        self.assertEqual(get.call_args.args[0], preview.source)

    def test_update_all_never_installs_or_updates_helper(self):
        self.service.installed[self.entry["id"]] = {"version": "v1.0", "managed": True}
        with patch.object(self.service, "check_updates", return_value={self.entry["id"]: TAG}), patch.object(self.service, "install") as install:
            result = self.service.update_all(self.progress, self.log, self.cancel)
        install.assert_not_called()
        self.assertEqual(result["skipped"], [self.entry["id"]])


if __name__ == "__main__":
    unittest.main()
