import hashlib
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

from core.errors import Cancelled, HubError
from core.installer import HubService, verify_windows_executable
from core.storage import read_installed
from tests.helpers import Response, make_catalog, windows_executable


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.catalog, self.entry = make_catalog(self.root)
        self.service = HubService(self.catalog, self.root / "data")
        self.addCleanup(self.close_logger)
        self.progress = Mock()
        self.log = Mock()
        self.cancel = threading.Event()

    def close_logger(self):
        for handler in list(self.service.logger.handlers):
            handler.close()
            self.service.logger.removeHandler(handler)

    @staticmethod
    def package(files):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return output.getvalue()

    def release(self, body, version="v1.0", *, digest=None):
        asset = {
            "name": "emulator-win-x64.zip", "size": len(body),
            "browser_download_url": f"https://github.com/official/emulator/releases/download/{version}/emulator-win-x64.zip",
            "digest": "sha256:" + (digest or hashlib.sha256(body).hexdigest()),
        }
        return {"tag_name": version, "prerelease": False, "draft": False, "assets": [asset]}

    def install_package(self, *, files=None, version="v1.0", digest=None, progress=None):
        body = self.package(files or {"app/emulator.exe": windows_executable()})
        release = self.release(body, version, digest=digest)
        with patch.object(self.service.github, "latest", return_value=release), patch.object(
            self.service.policy, "get", return_value=Response(body, headers={"Content-Length": str(len(body))})
        ):
            return self.service.install(self.entry, progress or self.progress, self.log, self.cancel)

    def assert_clean_staging(self):
        self.assertEqual(list(self.service.emulator_dir.glob("_install_*")), [])
        self.assertEqual(list(self.service.emulator_dir.glob("_backup_*")), [])
        self.assertEqual(list(self.service.emulator_dir.glob("_remove_*")), [])

    def test_auto_install_updates_status_and_persists_complete_record(self):
        record = self.install_package()
        self.assertEqual(record["version"], "v1.0")
        self.assertTrue(record["managed"])
        self.assertEqual(Path(record["exe_path"]).read_bytes(), windows_executable())
        self.assertEqual(read_installed(self.service.installed_path), self.service.installed)
        self.assertTrue(self.service.is_installed(self.entry["id"]))
        self.assertEqual(self.service.status(self.entry["id"]), "installiert")
        self.assertTrue(any("SHA-256 erfolgreich" in str(call) for call in self.log.call_args_list))
        self.assertEqual(self.progress.call_args.args[0], 100)
        self.assert_clean_staging()

    def test_real_downloader_rejects_truncated_file_without_registering_install(self):
        body = self.package({"emulator.exe": windows_executable()})
        release = self.release(body)
        with patch.object(self.service.github, "latest", return_value=release), patch.object(
            self.service.policy, "get", return_value=Response(body[:-5], headers={"Content-Length": str(len(body))})
        ), self.assertRaises(HubError):
            self.service.install(self.entry, self.progress, self.log, self.cancel)
        self.assertFalse(self.service.is_installed(self.entry["id"]))
        self.assertFalse((self.service.emulator_dir / self.entry["id"]).exists())
        self.assert_clean_staging()

    def test_update_compares_semantic_versions_and_preserves_user_settings_and_files(self):
        record = self.install_package()
        folder = Path(record["path"])
        (folder / "app/settings.ini").write_bytes(b"user-settings")
        (folder / "personal.txt").write_bytes(b"personal")
        with patch.object(self.service.github, "latest", return_value={"tag_name": "v1.10"}) as latest:
            result = self.service.check_updates(self.progress, self.log, self.cancel)
        latest.assert_called_once_with("official/emulator", force=True)
        self.assertEqual(result, {self.entry["id"]: "v1.10"})
        self.assertEqual(self.service.status(self.entry["id"]), "Update verfügbar")
        updated = self.install_package(version="v1.10", files={
            "app/emulator.exe": windows_executable(b"version-two"), "app/settings.ini": b"new-default",
        })
        self.assertEqual(Path(updated["exe_path"]).read_bytes(), windows_executable(b"version-two"))
        self.assertEqual((folder / "app/settings.ini").read_bytes(), b"user-settings")
        self.assertEqual((folder / "personal.txt").read_bytes(), b"personal")
        self.assertEqual(self.service.status(self.entry["id"]), "installiert")
        self.assert_clean_staging()

    def test_failed_hash_or_unsafe_archive_preserves_previous_install_and_state(self):
        self.install_package()
        state = self.service.installed_path.read_bytes()
        folder = self.service.emulator_dir / self.entry["id"]
        executable = folder / "app/emulator.exe"
        for options in (
            {"digest": "0" * 64},
            {"files": {"app/emulator.exe": windows_executable(b"changed"), "../escape.exe": b"bad"}},
            {"files": {"app/emulator.exe": b"not an executable"}},
        ):
            with self.subTest(options=options), self.assertRaises(HubError):
                self.install_package(version="v2.0", **options)
            self.assertEqual(executable.read_bytes(), windows_executable())
            self.assertEqual(self.service.installed_path.read_bytes(), state)
            self.assertEqual(self.service.installed[self.entry["id"]]["version"], "v1.0")
            self.assertFalse((self.service.emulator_dir / "escape.exe").exists())
            self.assert_clean_staging()

    def test_storage_failure_after_folder_swap_rolls_back_binary_and_json(self):
        self.install_package()
        state = self.service.installed_path.read_bytes()
        with patch("core.storage.os.replace", side_effect=OSError("disk failure")), self.assertRaises(HubError):
            self.install_package(version="v2.0", files={"app/emulator.exe": windows_executable(b"changed")})
        self.assertEqual((self.service.emulator_dir / self.entry["id"] / "app/emulator.exe").read_bytes(), windows_executable())
        self.assertEqual(self.service.installed_path.read_bytes(), state)
        self.assertEqual(self.service.installed[self.entry["id"]]["version"], "v1.0")
        self.assert_clean_staging()

    def test_cancelling_update_before_extract_preserves_previous_install(self):
        self.install_package()
        state = self.service.installed_path.read_bytes()

        def progress(percent, message):
            if percent >= 86:
                self.cancel.set()

        with self.assertRaises(Cancelled):
            self.install_package(version="v2.0", progress=progress)
        self.assertEqual(self.service.installed_path.read_bytes(), state)
        self.assertTrue(self.service.is_installed(self.entry["id"]))
        self.assert_clean_staging()

    def test_manually_selected_folder_is_never_recursively_deleted(self):
        own_folder = self.root / "my-emulators"
        own_folder.mkdir()
        (own_folder / "emulator.exe").write_bytes(windows_executable())
        personal = own_folder / "personal.txt"
        personal.write_text("keep", encoding="utf-8")
        record = self.service.register_manual(self.entry, own_folder)
        self.assertFalse(record["managed"])
        self.assertEqual(self.service.status(self.entry["id"]), "installiert")
        with self.assertRaises(HubError):
            self.install_package()
        with patch("core.installer.remove_managed_tree") as remove:
            self.service.uninstall(self.entry, self.log, self.cancel)
            remove.assert_not_called()
        self.assertTrue((own_folder / "emulator.exe").is_file())
        self.assertEqual(personal.read_text(encoding="utf-8"), "keep")
        self.assertEqual(read_installed(self.service.installed_path), {})
        self.assertEqual(self.service.status(self.entry["id"]), "nicht installiert")

    def test_managed_install_cannot_be_reassigned_to_a_different_manual_folder(self):
        record = self.install_package()
        state = self.service.installed_path.read_bytes()
        self.assertIs(self.service.register_manual(self.entry, Path(record["path"])), record)
        own_folder = self.root / "another-emulator"
        own_folder.mkdir()
        (own_folder / "emulator.exe").write_bytes(windows_executable(b"personal-install"))
        with self.assertRaises(HubError):
            self.service.register_manual(self.entry, own_folder)
        self.assertEqual(self.service.installed_path.read_bytes(), state)
        self.assertTrue(self.service.installed[self.entry["id"]]["managed"])
        self.assertEqual(Path(record["exe_path"]).read_bytes(), windows_executable())
        self.assertTrue((own_folder / "emulator.exe").exists())

    def test_manual_registration_rejects_missing_and_ambiguous_executables(self):
        own_folder = self.root / "manual"
        own_folder.mkdir()
        with self.assertRaises(HubError):
            self.service.register_manual(self.entry, own_folder)
        for name in ("first", "second"):
            sub = own_folder / name
            sub.mkdir()
            (sub / "emulator.exe").write_bytes(windows_executable())
        with self.assertRaises(HubError):
            self.service.register_manual(self.entry, own_folder)
        self.assertEqual(self.service.installed, {})

    def test_existing_untracked_target_folder_is_preserved(self):
        target = self.service.emulator_dir / self.entry["id"]
        target.mkdir()
        (target / "keep.txt").write_bytes(b"keep")
        with self.assertRaises(HubError):
            self.install_package()
        self.assertEqual((target / "keep.txt").read_bytes(), b"keep")
        self.assertEqual(self.service.installed, {})

    def test_tampered_managed_external_path_is_not_removed(self):
        own_folder = self.root / "my-emulators"
        own_folder.mkdir()
        (own_folder / "emulator.exe").write_bytes(windows_executable())
        record = self.service.register_manual(self.entry, own_folder)
        record["managed"] = True
        self.service._save(dict(self.service.installed))
        state = self.service.installed_path.read_bytes()
        with patch("core.installer.remove_managed_tree") as remove, self.assertRaises(HubError):
            self.service.uninstall(self.entry, self.log, self.cancel)
        remove.assert_not_called()
        self.assertTrue((own_folder / "emulator.exe").exists())
        self.assertEqual(self.service.installed_path.read_bytes(), state)

    def test_managed_uninstall_removes_own_folder_and_record(self):
        record = self.install_package()
        self.service.uninstall(self.entry, self.log, self.cancel)
        self.assertFalse(Path(record["path"]).exists())
        self.assertEqual(read_installed(self.service.installed_path), {})
        self.assertEqual(self.service.installed, {})
        self.assert_clean_staging()

    def test_failed_uninstall_state_save_restores_folder(self):
        record = self.install_package()
        state = self.service.installed_path.read_bytes()
        with patch.object(self.service, "_save", side_effect=HubError("disk failure")), self.assertRaises(HubError):
            self.service.uninstall(self.entry, self.log, self.cancel)
        self.assertTrue(Path(record["exe_path"]).exists())
        self.assertEqual(self.service.installed_path.read_bytes(), state)
        self.assertTrue(self.service.is_installed(self.entry["id"]))
        self.assert_clean_staging()

    def test_start_validates_executable_then_launches_without_shell(self):
        record = self.install_package()
        with patch("core.installer.subprocess.Popen") as launch:
            self.service.start(self.entry)
        self.assertEqual(launch.call_args.args[0], [str(Path(record["exe_path"]).resolve())])
        self.assertIs(launch.call_args.kwargs["shell"], False)
        self.assertEqual(launch.call_args.kwargs["cwd"], Path(record["exe_path"]).parent)

    def test_published_checksum_sidecar_is_verified_before_installation(self):
        body = self.package({"emulator.exe": windows_executable()})
        release = self.release(body)
        release["assets"][0].pop("digest")
        checksum_url = "https://github.com/official/emulator/releases/download/v1.0/emulator-win-x64.zip.sha256"
        release["assets"].append({"name": "emulator-win-x64.zip.sha256", "browser_download_url": checksum_url})
        checksum = hashlib.sha256(body).hexdigest() + "  emulator-win-x64.zip\n"

        def get(url, **kwargs):
            return Response(checksum.encode()) if url == checksum_url else Response(body, headers={"Content-Length": str(len(body))})

        with patch.object(self.service.github, "latest", return_value=release), patch.object(self.service.policy, "get", side_effect=get) as request:
            record = self.service.install(self.entry, self.progress, self.log, self.cancel)
        self.assertTrue(Path(record["exe_path"]).exists())
        self.assertEqual(request.call_args_list[0].args[0], checksum_url)
        self.assert_clean_staging()

    def test_ambiguous_published_checksums_stop_installation_before_download(self):
        body = self.package({"emulator.exe": windows_executable()})
        release = self.release(body)
        release["assets"][0].pop("digest")
        for name in ("checksums.txt", "sha256sums.txt"):
            release["assets"].append({
                "name": name,
                "browser_download_url": "https://github.com/official/emulator/releases/download/v1.0/" + name,
            })
        with patch.object(self.service.github, "latest", return_value=release), patch.object(self.service.policy, "get") as request:
            with self.assertRaises(HubError):
                self.service.install(self.entry, self.progress, self.log, self.cancel)
        request.assert_not_called()
        self.assertFalse(self.service.is_installed(self.entry["id"]))
        self.assert_clean_staging()

    def test_file_specific_checksum_is_preferred_over_generic_checksum_lists(self):
        body = self.package({"emulator.exe": windows_executable()})
        release = self.release(body)
        release["assets"][0].pop("digest")
        for name in ("checksums.txt", "sha256sums.txt", "emulator-win-x64.zip.sha256"):
            release["assets"].append({
                "name": name,
                "browser_download_url": "https://github.com/official/emulator/releases/download/v1.0/" + name,
            })
        expected = hashlib.sha256(body).hexdigest()
        with patch.object(self.service.policy, "get", return_value=Response((expected + "\n").encode())) as request:
            self.assertEqual(self.service._checksum(self.entry, release, release["assets"][0]), expected)
        self.assertTrue(request.call_args.args[0].endswith("/emulator-win-x64.zip.sha256"))

    def test_corrupted_state_prevents_service_start_and_is_not_overwritten(self):
        self.close_logger()
        content = "{incomplete installed state"
        self.service.installed_path.write_text(content, encoding="utf-8")
        with self.assertRaises(HubError):
            HubService(self.catalog, self.service.data_dir)
        self.assertEqual(self.service.installed_path.read_text(encoding="utf-8"), content)

    def test_portable_auto_install_requires_x64_but_manual_supports_x86(self):
        own_folder = self.root / "x86-emulator"
        own_folder.mkdir()
        executable = own_folder / "emulator.exe"
        executable.write_bytes(windows_executable(machine=0x14c))
        with self.assertRaises(HubError):
            verify_windows_executable(executable)
        verify_windows_executable(executable, require_x64=False)
        self.assertFalse(self.service.register_manual(self.entry, own_folder)["managed"])


if __name__ == "__main__":
    unittest.main()
