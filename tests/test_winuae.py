"""Official-page selection, portable installation and configuration-only launch."""
import io
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

import requests

from core.catalog import Catalog
from core.direct import MAX_PAGE_SIZE, WINUAE_PAGE, WINUAE_RELEASES, resolve_winuae, select_winuae_asset
from core.errors import Cancelled, HubError
from core.installer import HubService
from core.launch import build_launch_command
from core.library import AMIGA_CONSOLE, LibraryStore, WINUAE_CONFIG_STATUS, game_status
from core.security import URLPolicy
from tests.helpers import Response, TemporaryDirectory, windows_executable


def download_page(version="6.0.3", *, href=None, label="[zip-archive (64-bit)]"):
    digits = version.replace(".", "") + "0"
    url = href or f"{WINUAE_RELEASES}WinUAE{digits}_x64.zip"
    return (f'<p><strong>Download WinUAE {version}</strong></p><ul>'
            f'<li><a href="{WINUAE_RELEASES}InstallWinUAE{digits}_x64.msi">Installer (64-bit)</a></li>'
            f'<li><a href="{WINUAE_RELEASES}WinUAE{digits}.zip">zip-archive (32-bit)</a>'
            f'<a href="{url}">{label}</a></li></ul>'
            '<p><strong>Download WinUAE extension packages</strong></p>'
            f'<a href="{WINUAE_RELEASES}WinUAE3000_x64.zip">zip-archive (64-bit)</a>')


class WinUAESelectionTests(unittest.TestCase):
    def setUp(self):
        self.policy = URLPolicy(["https://www.winuae.net", WINUAE_RELEASES.rstrip("/")])
        self.entry = {"direct_url": WINUAE_PAGE}
        self.cancel = threading.Event()

    def test_stable_x64_zip_is_selected_from_actual_link_only(self):
        page = download_page() + ('<h2>Download WinUAE 6.1.0 beta</h2>'
                                  f'<a href="{WINUAE_RELEASES}WinUAE6100_x64.zip">zip-archive (64-bit)</a>')
        asset = select_winuae_asset(page, self.policy)
        self.assertEqual((asset.url, asset.name, asset.version),
                         (WINUAE_RELEASES + "WinUAE6030_x64.zip", "WinUAE6030_x64.zip", "6.0.3"))

    def test_missing_ambiguous_beta_or_mismatched_metadata_fails_closed(self):
        pages = [
            "<strong>Download WinUAE 6.0.3</strong>",
            download_page().replace("6.0.3</strong>", "6.0.3 beta</strong>"),
            download_page() + download_page("6.0.2"),
            download_page(href=WINUAE_RELEASES + "WinUAE6020_x64.zip"),
            download_page(href=WINUAE_RELEASES + "WinUAE6030_x64_beta.zip"),
            download_page(label="zip-archive (64-bit) preview"),
            download_page(label="Installer (64-bit)"),
            download_page(href=WINUAE_RELEASES + "WinUAE6030_x64.zip?beta=1"),
        ]
        for page in pages:
            with self.subTest(page=page), self.assertRaises(HubError):
                select_winuae_asset(page, self.policy)

    def test_whitelist_and_exact_official_linked_host_are_required(self):
        for href in (
            "https://other.example/WinUAE6030_x64.zip",
            "https://download.abime.net.evil.example/winuae/releases/WinUAE6030_x64.zip",
            "http://download.abime.net/winuae/releases/WinUAE6030_x64.zip",
            "https://download.abime.net/winuae/betas/WinUAE6030_x64.zip",
            "https://download.abime.net/winuae/releases/../WinUAE6030_x64.zip",
        ):
            with self.subTest(href=href), self.assertRaises(HubError):
                select_winuae_asset(download_page(href=href), self.policy)
        with self.assertRaisesRegex(HubError, "Whitelist"):
            select_winuae_asset(download_page(), URLPolicy(["https://www.winuae.net"]))

    def test_page_is_bounded_cancelable_and_never_loads_program_files(self):
        with patch.object(self.policy, "get", return_value=Response(download_page().encode())) as request:
            self.assertEqual(resolve_winuae(self.policy, self.entry, self.cancel).version, "6.0.3")
        request.assert_called_once_with(WINUAE_PAGE, stream=True)
        with patch.object(self.policy, "get", return_value=Response(b"x" * (MAX_PAGE_SIZE + 1))), self.assertRaises(HubError):
            resolve_winuae(self.policy, self.entry, self.cancel)
        self.cancel.set()
        with patch.object(self.policy, "get") as request, self.assertRaises(Cancelled):
            resolve_winuae(self.policy, self.entry, self.cancel)
        request.assert_not_called()
        self.cancel.clear()
        with patch.object(self.policy, "get") as request, self.assertRaises(HubError):
            resolve_winuae(self.policy, {"direct_url": "https://other.example/"}, self.cancel)
        request.assert_not_called()


class WinUAEIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog = Catalog()
        self.entry = self.catalog.by_id("winuae")
        self.service = HubService(self.catalog, self.root / "data")
        self.addCleanup(self.close_logger)
        self.cancel = threading.Event()
        self.progress, self.log = Mock(), Mock()

    def close_logger(self):
        for handler in list(self.service.logger.handlers):
            handler.close()
            self.service.logger.removeHandler(handler)

    def archive(self, *, name="winuae64.exe", content=None):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr(name, content or windows_executable())
        return output.getvalue()

    def install(self, version="6.0.3", body=None, shortcuts=None):
        package = self.archive() if body is None else body
        with patch.object(self.service.policy, "get", side_effect=[
                Response(download_page(version).encode()),
                Response(package, headers={"Content-Length": str(len(package))})]) as request:
            record = self.service.install(self.entry, self.progress, self.log, self.cancel, shortcuts=shortcuts)
        self.assertEqual(request.call_args_list[0].args[0], WINUAE_PAGE)
        self.assertEqual(request.call_args_list[1].args[0],
                         WINUAE_RELEASES + "WinUAE" + version.replace(".", "") + "0_x64.zip")
        return record

    def test_portable_install_executable_extraction_progress_and_optional_shortcut(self):
        with patch("core.installer.create_shortcuts", return_value=[]) as shortcuts:
            record = self.install(shortcuts={"desktop": True})
        self.assertEqual(record["version"], "6.0.3")
        self.assertEqual(record["method"], "auto_direct")
        self.assertEqual(Path(record["exe_path"]), self.service.emulator_dir / "winuae" / "winuae64.exe")
        self.assertTrue(self.service.is_installed("winuae"))
        shortcuts.assert_called_once()
        self.assertTrue(any("keine SHA-256" in str(call) for call in self.log.call_args_list))
        self.assertTrue(any(86 < call.args[0] < 95 for call in self.progress.call_args_list))
        self.assertEqual(list(self.service.emulator_dir.glob("_install_*")), [])

    def test_update_check_fetches_only_official_page_and_update_preserves_personal_files(self):
        record = self.install()
        folder = Path(record["path"])
        (folder / "Mein Profil.uae").write_text("eigene Konfiguration", encoding="utf-8")
        with patch.object(self.service.policy, "get", return_value=Response(download_page("6.0.4").encode())) as request:
            result = self.service.check_updates(self.progress, self.log, self.cancel)
        request.assert_called_once_with(WINUAE_PAGE, stream=True)
        self.assertEqual(result, {"winuae": "6.0.4"})
        self.assertEqual(self.service.status("winuae"), "Update verfügbar")
        updated = self.install("6.0.4", self.archive(content=windows_executable(b"version-two")))
        self.assertEqual(updated["version"], "6.0.4")
        self.assertEqual((folder / "Mein Profil.uae").read_text(encoding="utf-8"), "eigene Konfiguration")

    def test_invalid_page_never_downloads_and_failed_update_preserves_installation(self):
        self.install()
        state = self.service.installed_path.read_bytes()
        executable = Path(self.service.installed["winuae"]["exe_path"])
        original = executable.read_bytes()
        with patch.object(self.service.policy, "get", return_value=Response(download_page(label="64-bit beta ZIP").encode())) as request:
            with self.assertRaises(HubError):
                self.service.install(self.entry, self.progress, self.log, self.cancel)
        request.assert_called_once_with(WINUAE_PAGE, stream=True)
        with self.assertRaisesRegex(HubError, "Startdatei"):
            self.install("6.0.4", self.archive(name="unverified.exe"))
        self.assertEqual(executable.read_bytes(), original)
        self.assertEqual(self.service.installed_path.read_bytes(), state)

    def test_changed_page_reports_manual_update_check_and_clears_stale_result(self):
        self.install()
        self.service.latest_versions["winuae"] = "6.0.4"
        with patch.object(self.service.policy, "get", return_value=Response(b"changed layout")):
            self.assertEqual(self.service.check_updates(self.progress, self.log, self.cancel), {})
        self.assertNotIn("winuae", self.service.latest_versions)
        self.assertTrue(any("manuell prüfen" in str(call) for call in self.log.call_args_list))

    def test_page_stream_failure_does_not_abort_other_emulator_checks(self):
        class BrokenResponse(Response):
            def iter_content(self, chunk_size=8192):
                yield b"partial page"
                raise requests.exceptions.ChunkedEncodingError("synthetic interrupted response")

        self.install()
        other = next(entry for entry in self.catalog.items if entry["install_methode"] == "auto_github" and not entry.get("hidden"))
        self.catalog.items = [self.entry, other]
        self.service.installed[other["id"]] = {"version": "1.0"}
        self.service.latest_versions["winuae"] = "6.0.4"
        with patch.object(self.service.policy, "get", return_value=BrokenResponse()), patch.object(
                self.service.github, "latest", return_value={"tag_name": "2.0"}):
            result = self.service.check_updates(self.progress, self.log, self.cancel)
        self.assertEqual(result, {other["id"]: "2.0"})
        self.assertNotIn("winuae", self.service.latest_versions)
        self.assertTrue(any("manuell prüfen" in str(call) for call in self.log.call_args_list))

    def test_update_all_refuses_downgrade_when_official_page_changes_between_requests(self):
        self.install()
        saved = self.service.installed_path.read_bytes()
        with patch.object(self.service.policy, "get", side_effect=[
                Response(download_page("6.0.4").encode()),
                Response(download_page("6.0.2").encode())]) as request:
            result = self.service.update_all(self.progress, self.log, self.cancel)
        self.assertEqual(result["updated"], [])
        self.assertIn("winuae", result["failed"])
        self.assertEqual(request.call_count, 2)
        self.assertTrue(all(call.args[0] == WINUAE_PAGE for call in request.call_args_list))
        self.assertEqual(self.service.installed_path.read_bytes(), saved)
        self.assertNotIn("winuae", self.service.latest_versions)

    def test_configuration_launch_uses_literal_path_images_require_configuration(self):
        configuration = self.root / "Mein Profil & Zeichen.uae"
        configuration.write_text("eigene Konfiguration", encoding="utf-8")
        exe = self.root / "winuae64.exe"
        command = build_launch_command(self.entry, exe, configuration)
        self.assertEqual(command, [str(exe), "-f", str(configuration), "-s", "use_gui=no"])
        image = self.root / "Meine Disk.adf"
        image.write_bytes(b"synthetische eigene Testdatei")
        with self.assertRaisesRegex(HubError, "Konfiguration"):
            build_launch_command(self.entry, exe, image)
        self.assertEqual(game_status({"console": self.entry["konsole"], "path": str(image)}), WINUAE_CONFIG_STATUS)
        self.assertEqual(game_status({"console": self.entry["konsole"], "path": str(configuration)}), "Bereit")

    def test_amiga_images_and_configurations_scan_without_reading_or_downloading_content(self):
        folder = self.root / "Eigene Amiga-Dateien"
        folder.mkdir()
        for extension in (".adf", ".adz", ".dms", ".ipf", ".hdf", ".lha", ".uae", ".cue", ".iso"):
            (folder / ("Datei" + extension)).write_bytes(b"synthetische Testdatei")
        with patch.object(self.service.policy, "get") as request:
            self.service.library.scan([folder], self.progress, self.log, self.cancel)
        request.assert_not_called()
        games = self.service.library.games
        self.assertEqual(len(games), 9)
        for game in games:
            if Path(game["path"]).suffix in {".cue", ".iso"}:
                self.assertIsNone(game["console"])
                self.assertIn(self.entry["konsole"], game["candidates"])
            else:
                self.assertEqual(game["console"], self.entry["konsole"])

    def test_older_local_extension_defaults_gain_amiga_without_overwriting_customizations(self):
        path = self.service.data_dir / "configs/extensions.json"
        config = json.loads(path.read_text(encoding="utf-8"))
        legacy = {}
        for suffix, consoles in config["extensions"].items():
            if consoles == AMIGA_CONSOLE:
                continue
            legacy[suffix] = [console for console in consoles if console != AMIGA_CONSOLE] if isinstance(consoles, list) else consoles
        config["extensions"] = legacy
        path.write_text(json.dumps(config), encoding="utf-8")
        saved = path.read_bytes()
        library = LibraryStore(self.service.data_dir, self.catalog, self.service.settings)
        for suffix in (".adf", ".adz", ".dms", ".ipf", ".hdf", ".lha", ".uae"):
            self.assertEqual(library.extensions[suffix], [AMIGA_CONSOLE])
        for suffix in (".cue", ".iso"):
            self.assertIn(AMIGA_CONSOLE, library.extensions[suffix])
        self.assertEqual(path.read_bytes(), saved)
        config["extensions"].update({".adf": "Eigene Zuordnung", ".cue": ["Eigene CD-Zuordnung"]})
        path.write_text(json.dumps(config), encoding="utf-8")
        saved = path.read_bytes()
        customized = LibraryStore(self.service.data_dir, self.catalog, self.service.settings)
        self.assertEqual(customized.extensions[".adf"], ["Eigene Zuordnung"])
        self.assertEqual(customized.extensions[".cue"], ["Eigene CD-Zuordnung"])
        self.assertEqual(path.read_bytes(), saved)


if __name__ == "__main__":
    unittest.main()
