"""shadPS4: geprüfte Quellen, stabile Releases und sichere native Spielstarts."""
import json
from copy import deepcopy
from pathlib import Path
import re
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

from core.catalog import Catalog, CatalogError, LEGAL_NOTICE, REQUIRED_TEXT_FIELDS
from core.errors import HubError
from core.github import GitHubClient
from core.launch import build_launch_command
from core.library import LibraryStore
from core.security import URLPolicy
from core.settings import SettingsStore
from tests.helpers import Response, TemporaryDirectory, windows_executable


PROJECT = Path(__file__).resolve().parents[1]
REPOSITORY = "shadps4-emu/shadPS4"
LAUNCHER_REPOSITORY = "shadps4-emu/shadps4-qtlauncher"
RELEASE_TAG = "v.0.19.0"
# Namen aus /repos/shadps4-emu/shadPS4/releases/latest, geprüft am 03.10.2026.
STABLE_ASSET_NAMES = (
    "shadps4-win64-sdl-0.19.0.zip",
    "shadps4-linux-sdl-0.19.0.zip",
    "shadps4-macos-sdl-0.19.0.zip",
)
NIGHTLY_TAG = "Pre-release-shadPS4-2026-10-02-ead912cf951fc5f27768e64330ee22beb67663bf"
NIGHTLY_ASSET_NAME = "shadps4-win64-sdl-2026-10-02-ead912c.zip"
LAUNCHER_NIGHTLY_TAG = "shadPS4QtLauncher-2026-10-02-4c4e1090ea53dc1ec956fa9954acbf143d104b2e"
LAUNCHER_NIGHTLY_ASSET = "shadPS4QtLauncher-win64-qt-2026-10-02-4c4e109.zip"


def release_fixture(tag=RELEASE_TAG, *, prerelease=False, draft=False, names=STABLE_ASSET_NAMES):
    return {
        "tag_name": tag, "prerelease": prerelease, "draft": draft,
        "assets": [{"name": name, "browser_download_url":
                    f"https://github.com/{REPOSITORY}/releases/download/{tag}/{name}"}
                   for name in names],
    }


class ShadPS4CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog(PROJECT / "catalog.json")
        self.entry = self.catalog.by_id("shadps4")
        self.policy = URLPolicy(self.catalog.official_sources)
        self.client = GitHubClient(self.policy)

    def test_sony_ps4_entry_is_complete_and_uses_configured_very_high_requirement(self):
        self.assertEqual(len(self.catalog.items), 25)
        self.assertEqual(len([item for item in self.catalog.items
                              if item["konsole"] == "PlayStation 4" and item.get("entry_type") != "utility"]), 1)
        for field in REQUIRED_TEXT_FIELDS:
            with self.subTest(field=field):
                self.assertTrue(self.entry[field].strip())
        self.assertEqual(self.entry["emulator"], "shadPS4")
        self.assertEqual(self.entry["hersteller"], "Sony")
        self.assertEqual(self.entry["kategorie"], "Sony PlayStation")
        self.assertEqual(self.entry["pc_anforderung"], "Sehr hoch")
        for platform in ("Windows", "Linux", "macOS", "x64"):
            self.assertIn(platform, self.entry["plattformen"])
        self.assertEqual(self.entry["install_methode"], "auto_github")
        self.assertEqual(self.entry["github_repo"], REPOSITORY)
        self.assertEqual(self.entry["archive_type"], "zip")
        self.assertIn(LEGAL_NOTICE, self.entry["hinweis"])
        self.assertIn("früh", self.entry["hinweis"].casefold())
        self.assertIn("kompatib", self.entry["hinweis"].casefold())
        self.assertIn("eigene", self.entry["hinweis"].casefold())
        self.assertIs(self.entry["deprecated"], True)
        self.assertEqual(self.entry["replacement_id"], "ps4-pkg-tool")
        self.assertIn("startbar", self.entry["deprecated_note"])
        self.assertIn("nicht direkt", self.entry["hinweis"].casefold())
        self.assertGreaterEqual(len(self.entry["manuelle_schritte"]), 4)
        self.assertIn("shadPS4.exe", " ".join(self.entry["manuelle_schritte"]))
        self.assertEqual(self.entry["controller_config"], "manuell")
        self.assertTrue(self.entry["controller_manual"].strip())
        requirements = json.loads((PROJECT / "configs/system_requirements.json").read_text(encoding="utf-8"))
        self.assertIn(self.entry["pc_anforderung"], requirements["levels"])

    def test_shadps4_links_are_whitelisted_official_project_or_exact_repositories(self):
        self.assertIn(f"https://github.com/{REPOSITORY}", self.catalog.official_sources)
        self.assertIn(f"https://github.com/{LAUNCHER_REPOSITORY}", self.catalog.official_sources)
        self.assertIn("https://shadps4.net/", self.catalog.official_sources)
        shad_sources = {source for source in self.catalog.official_sources
                        if "shadps4" in source.casefold()}
        self.assertEqual(shad_sources, {f"https://github.com/{REPOSITORY}",
                                       f"https://github.com/{LAUNCHER_REPOSITORY}",
                                       "https://shadps4.net/"})
        def texts(value):
            if isinstance(value, str):
                yield value
            elif isinstance(value, dict):
                for child in value.values():
                    yield from texts(child)
            elif isinstance(value, list):
                for child in value:
                    yield from texts(child)

        links = re.findall(r'https?://[^\s<>"\)\]]+', "\n".join(texts(self.entry)))
        self.assertTrue(links)
        for link in links:
            link = link.rstrip(".,;")
            with self.subTest(link=link):
                self.assertEqual(self.policy.validate(link), link)
                parts = urlsplit(link)
                self.assertTrue(parts.hostname == "shadps4.net" or
                                (parts.hostname == "github.com" and
                                 any(parts.path == f"/{repo}" or parts.path.startswith(f"/{repo}/")
                                     for repo in (REPOSITORY, LAUNCHER_REPOSITORY))))
        self.assertFalse(self.policy.allows("https://github.com/unofficial/shadPS4/releases"))
        self.assertFalse(self.policy.allows("https://github.com/shadps4-emu/other-project/releases"))
        self.assertFalse(self.policy.allows("https://github.com/shadps4-emu/shadps4-qtlauncher-unsafe/releases"))
        self.assertFalse(self.policy.allows("https://shadps4.net.example.invalid/download"))

    def test_launcher_metadata_is_manual_and_documents_verified_downloads_and_big_picture(self):
        self.assertEqual(self.entry["start_args"], ["-b"])
        self.assertIn("QTLauncher", self.entry["start_note"])
        self.assertIn("-b", self.entry["start_note"])
        launcher = self.entry["launcher"]
        self.assertEqual(launcher["install_methode"], "manuell")
        self.assertEqual(launcher["github_repo"], LAUNCHER_REPOSITORY)
        self.assertEqual(launcher["official_url"], f"https://github.com/{LAUNCHER_REPOSITORY}/releases")
        self.assertEqual(launcher["archive_type"], "zip")
        self.assertEqual(launcher["exe"], "shadPS4QtLauncher.exe")
        self.assertEqual(launcher["directory"], "qtlauncher")
        self.assertEqual(launcher["args"], [])
        self.assertTrue(launcher["verified_prerelease"])
        self.assertEqual(launcher["verified_release"], LAUNCHER_NIGHTLY_TAG)
        self.assertEqual(launcher["verified_asset"], LAUNCHER_NIGHTLY_ASSET)
        self.assertRegex(launcher["verified_asset_sha256"], r"^[0-9a-f]{64}$")
        self.assertIn("Pre-Release", launcher["note"])
        self.assertIsNotNone(re.fullmatch(launcher["download_muster"], LAUNCHER_NIGHTLY_ASSET, re.IGNORECASE))
        for other_asset in (LAUNCHER_NIGHTLY_ASSET.replace("win64", "linux"),
                            LAUNCHER_NIGHTLY_ASSET.replace("win64", "macos")):
            self.assertIsNone(re.fullmatch(launcher["download_muster"], other_asset, re.IGNORECASE))
        instructions = " ".join(self.entry["manuelle_schritte"])
        self.assertIn("PS4 PKG Tool", instructions)
        self.assertIn("shadPS4 Manager", instructions)
        self.assertNotIn("herunterladen", instructions)

    def test_start_arguments_and_launcher_metadata_reject_unsafe_catalog_values(self):
        changes = [
            {"start_args": "-b"}, {"start_args": [17]},
            {"start_args": ["-b\n"]}, {"start_args": ["{game}"]},
        ]
        for field, value in (("github_repo", "unofficial/qtlauncher"),
                             ("official_url", "https://github.com/shadps4-emu/other-project/releases"),
                             ("exe", "../shadPS4QtLauncher.exe"),
                             ("exe", "shadPS4.exe"),
                             ("directory", "../external"),
                             ("directory", "C:/external"),
                             ("args", ["{game}"]), ("args", ["--gui\n"])):
            changes.append({"launcher": {**self.entry["launcher"], field: value}})
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "catalog.json"
            original = json.loads(self.catalog.path.read_text(encoding="utf-8"))
            for changed in changes:
                raw = deepcopy(original)
                entry = next(item for item in raw["emulators"] if item["id"] == "shadps4")
                entry.update(changed)
                output.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
                with self.subTest(changed=changed), self.assertRaises(CatalogError):
                    Catalog(output)

    def test_fraud_name_and_domain_are_absent_from_catalog_and_url_whitelist(self):
        catalog_text = (PROJECT / "catalog.json").read_text(encoding="utf-8").casefold()
        enrichment = json.loads((PROJECT / "tools/catalog_enrichment.json").read_text(encoding="utf-8"))
        whitelist_text = json.dumps({
            "runtime": self.policy.prefixes,
            "import": enrichment["official_sources"],
            "release_redirects": sorted(URLPolicy.GITHUB_CDN),
        }).casefold()
        prohibited_name = "pcsx" + str(4)
        for prohibited in (prohibited_name, prohibited_name + ".com"):
            with self.subTest(prohibited=prohibited):
                self.assertNotIn(prohibited, catalog_text)
                self.assertNotIn(prohibited, whitelist_text)
        self.assertFalse(self.policy.allows("https://" + prohibited_name + ".com/"))

    def test_simulated_official_stable_api_selects_exactly_one_windows_x64_asset(self):
        release = release_fixture()
        with patch.object(self.policy, "get", return_value=Response(payload=release)) as get:
            selected_release = self.client.latest(REPOSITORY)
        self.assertEqual(get.call_args.args[0], f"https://api.github.com/repos/{REPOSITORY}/releases/latest")
        selected_asset = self.client.asset(self.entry, selected_release)
        self.assertEqual(selected_asset["name"], STABLE_ASSET_NAMES[0])
        self.assertEqual(self.entry["verified_asset"], selected_asset["name"])
        self.assertEqual(self.entry["verified_release"], RELEASE_TAG)
        matches = [asset for asset in release["assets"]
                   if re.fullmatch(self.entry["download_muster"], asset["name"], re.IGNORECASE)]
        self.assertEqual(matches, [selected_asset])
        self.assertIsNone(re.fullmatch(self.entry["download_muster"], NIGHTLY_ASSET_NAME, re.IGNORECASE))

    def test_nightly_is_ignored_using_stable_latest_endpoint(self):
        stable = release_fixture()
        nightly = release_fixture(NIGHTLY_TAG, prerelease=True, names=(NIGHTLY_ASSET_NAME,))
        def api_response(url, **_kwargs):
            # Die GitHub-Liste beginnt mit dem neueren Nightly; /latest liefert das stabile Release.
            payload = stable if url.endswith("/releases/latest") else [nightly, stable]
            return Response(payload=payload)
        with patch.object(self.policy, "get", side_effect=api_response) as get:
            selected_release = self.client.latest(REPOSITORY)
        self.assertFalse(selected_release["prerelease"])
        self.assertFalse(selected_release["draft"])
        self.assertEqual(selected_release["tag_name"], RELEASE_TAG)
        self.assertEqual(self.client.asset(self.entry, selected_release)["name"], STABLE_ASSET_NAMES[0])
        get.assert_called_once()
        self.assertTrue(get.call_args.args[0].endswith("/releases/latest"))

    def test_prerelease_or_draft_returned_by_latest_is_never_installed_or_cached(self):
        for release in (release_fixture(NIGHTLY_TAG, prerelease=True, names=(NIGHTLY_ASSET_NAME,)),
                        release_fixture(draft=True)):
            with self.subTest(tag=release["tag_name"], draft=release["draft"]):
                with patch.object(self.policy, "get", return_value=Response(payload=release)), self.assertRaises(HubError):
                    self.client.latest(REPOSITORY, force=True)
                self.assertNotIn(REPOSITORY, self.client._cache)

    def test_qtlauncher_nightly_is_not_accepted_even_with_matching_windows_asset(self):
        names = [LAUNCHER_NIGHTLY_ASSET.replace("win64", "linux"),
                 LAUNCHER_NIGHTLY_ASSET.replace("win64", "macos"), LAUNCHER_NIGHTLY_ASSET]
        for prerelease, draft in ((True, False), (False, True)):
            release = {
                "tag_name": LAUNCHER_NIGHTLY_TAG, "prerelease": prerelease, "draft": draft,
                "assets": [{"name": name, "browser_download_url":
                            f"https://github.com/{LAUNCHER_REPOSITORY}/releases/download/"
                            f"{LAUNCHER_NIGHTLY_TAG}/{name}"} for name in names],
            }
            matches = [asset for asset in release["assets"]
                       if re.fullmatch(self.entry["launcher"]["download_muster"], asset["name"], re.IGNORECASE)]
            self.assertEqual([asset["name"] for asset in matches], [LAUNCHER_NIGHTLY_ASSET])
            with self.subTest(prerelease=prerelease, draft=draft), patch.object(
                self.policy, "get", return_value=Response(payload=release)
            ) as get, self.assertRaisesRegex(HubError, "stabiles Release"):
                self.client.latest(LAUNCHER_REPOSITORY, force=True)
            self.assertEqual(get.call_args.args[0],
                             f"https://api.github.com/repos/{LAUNCHER_REPOSITORY}/releases/latest")
            self.assertNotIn(LAUNCHER_REPOSITORY, self.client._cache)

    def test_missing_duplicate_or_other_repository_asset_requires_manual_fallback(self):
        windows_asset = release_fixture()["assets"][0]
        foreign_asset = {**windows_asset, "browser_download_url":
                         f"https://github.com/melonDS-emu/melonDS/releases/download/{RELEASE_TAG}/{windows_asset['name']}"}
        for assets in ([], [windows_asset, dict(windows_asset)], [foreign_asset]):
            with self.subTest(assets=assets), self.assertRaises(HubError):
                self.client.asset(self.entry, {**release_fixture(), "assets": assets})

    def test_workbook_and_enrichment_reproduce_ps4_entry_and_whitelist(self):
        from tools.import_catalog import import_workbook
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "imported-catalog.json"
            count = import_workbook(PROJECT / "docs/emulatoren_mit_downloadanleitungen.xlsx",
                                    output, PROJECT / "tools/catalog_enrichment.json")
            imported = Catalog(output)
        self.assertEqual(count, 25)
        self.assertEqual(imported.by_id("shadps4"), self.entry)
        self.assertEqual(imported.official_sources, self.catalog.official_sources)

    def test_native_eboot_uses_documented_literal_game_argument_and_pkg_is_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "shadPS4.exe"
            executable.write_bytes(windows_executable())
            game_folder = root / "Eigenes PS4-Spiel & Zeichen; $(test)"
            game_folder.mkdir()
            game = game_folder / "eboot.bin"
            game.write_bytes(b"synthetische eigene Testdatei")
            self.assertEqual(self.entry["exe"], "shadPS4.exe")
            self.assertEqual(self.entry["launch_args"], ["-g", "{game}"])
            self.assertEqual(self.entry["launch_extensions"], [".bin"])
            self.assertEqual(build_launch_command(self.entry, executable, game),
                             [str(executable), "-g", str(game)])
            package = root / "synthetisches.pkg"
            package.write_bytes(b"kein echtes Spielpaket")
            with self.assertRaisesRegex(HubError, "PKG"):
                build_launch_command(self.entry, executable, package)
            with self.assertRaisesRegex(HubError, "Spiel-Datei"):
                build_launch_command(self.entry, executable, game_folder)
            self.assertEqual(game.read_bytes(), b"synthetische eigene Testdatei")
            self.assertEqual(package.read_bytes(), b"kein echtes Spielpaket")

    def test_library_keeps_bin_ambiguous_offers_ps4_and_records_pkg_as_nonlaunchable(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            games = root / "Eigene Dateien"
            games.mkdir()
            eboot = games / "eboot.bin"
            eboot.write_bytes(b"synthetische eigene Testdatei")
            package = games / "synthetisches.pkg"
            package.write_bytes(b"kein echtes Spielpaket")
            settings = SettingsStore(data)
            settings.set("show_hidden", True)
            library = LibraryStore(data, self.catalog, settings,
                                   config_path=PROJECT / "configs/extensions.json")
            self.assertEqual(library.extensions[".pkg"], ["PlayStation 4"])
            library.scan([games], Mock(), Mock(), threading.Event())
            self.assertEqual(len(library.games), 2)
            game = next(game for game in library.games if Path(game["path"]) == eboot)
            self.assertEqual(Path(game["path"]), eboot)
            self.assertIsNone(game["console"])
            self.assertIn("PlayStation 4", game["candidates"])
            library.set_console(game["id"], "PlayStation 4")
            self.assertEqual(library.get_game(game["id"])["console"], "PlayStation 4")
            pkg_entry = next(game for game in library.games if Path(game["path"]) == package)
            self.assertFalse(pkg_entry["launchable"])
            with self.assertRaisesRegex(HubError, "Im PS4 PKG Tool installieren"):
                library.launch_game(pkg_entry["id"])
            self.assertEqual(eboot.read_bytes(), b"synthetische eigene Testdatei")
            self.assertEqual(package.read_bytes(), b"kein echtes Spielpaket")


if __name__ == "__main__":
    unittest.main()
