import io
from pathlib import Path
import stat
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

from core.archives import extract_archive, remove_managed_tree, safe_member
from core.errors import Cancelled, HubError
from core.security import URLPolicy
from tests.helpers import Response


class URLPolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = URLPolicy(["https://github.com/official/emulator", "https://emulator.example/downloads"])

    def test_only_https_and_official_repository_are_accepted(self):
        self.assertTrue(self.policy.allows("https://github.com/official/emulator/releases/download/v1/win.zip"))
        self.assertTrue(self.policy.allows("https://api.github.com/repos/official/emulator/releases/latest"))
        for url in (
            "http://github.com/official/emulator/releases/latest",
            "https://name:password@github.com/official/emulator",
            "https://github.com:444/official/emulator",
            "https://github.com/unofficial/emulator/releases/latest",
            "https://api.github.com/repos/unofficial/emulator/releases/latest",
            "https://github.com/official/emulator-malware/releases/latest",
            "https://github.com.attacker.example/official/emulator",
            "https://emulator.example/downloads-evil/setup.zip",
            "https://emulator.example/downloads/%2e%2e/private.zip",
            "https://emulator.example/downloads/%5cprivate.zip",
        ):
            with self.subTest(url=url), self.assertRaises(HubError):
                self.policy.validate(url)

    def test_rejected_redirect_is_never_requested(self):
        for location in ("http://emulator.example/downloads/setup.zip", "https://attacker.example/payload.zip"):
            session = Mock()
            redirect = Response(status=302, headers={"Location": location})
            session.get.return_value = redirect
            with self.subTest(location=location), patch("core.security.requests.Session", return_value=session):
                with self.assertRaises(HubError):
                    self.policy.get("https://emulator.example/downloads/latest.zip")
                session.get.assert_called_once()
                self.assertTrue(redirect.closed)
                session.close.assert_called_once()

    def test_relative_official_redirect_is_requested_with_redirects_disabled(self):
        session = Mock()
        redirects = Response(status=302, headers={"Location": "./version.zip"})
        final = Response(b"archive")
        session.get.side_effect = [redirects, final]
        with patch("core.security.requests.Session", return_value=session):
            self.assertIs(self.policy.get("https://emulator.example/downloads/latest.zip"), final)
        self.assertEqual(session.get.call_args_list[1].args[0], "https://emulator.example/downloads/version.zip")
        self.assertTrue(all(call.kwargs["allow_redirects"] is False for call in session.get.call_args_list))

    def test_github_cdn_exception_is_limited_to_release_asset_downloads(self):
        for start, allowed in (
            ("https://github.com/official/emulator/releases/download/v1/win.zip", True),
            ("https://github.com/official/emulator", False),
        ):
            session = Mock()
            session.get.side_effect = [Response(status=302, headers={
                "Location": "https://release-assets.githubusercontent.com/github-production-release-asset/file"
            }), Response(b"archive")]
            with self.subTest(start=start), patch("core.security.requests.Session", return_value=session):
                if allowed:
                    self.assertEqual(self.policy.get(start).content, b"archive")
                    self.assertEqual(session.get.call_count, 2)
                else:
                    with self.assertRaises(HubError):
                        self.policy.get(start)
                    self.assertEqual(session.get.call_count, 1)

    def test_redirect_loop_has_a_finite_request_limit(self):
        session = Mock()
        session.get.return_value = Response(status=302, headers={"Location": "/downloads/latest.zip"})
        with patch("core.security.requests.Session", return_value=session), self.assertRaises(HubError):
            self.policy.get("https://emulator.example/downloads/latest.zip")
        self.assertEqual(session.get.call_count, 6)


class ArchiveSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.destination = self.root / "unpacked"
        self.cancel = threading.Event()

    def make_zip(self, members):
        archive = self.root / "download.zip"
        with zipfile.ZipFile(archive, "w") as handle:
            for name, body in members:
                handle.writestr(name, body)
        return archive

    def test_rejects_traversal_absolute_ads_and_windows_reserved_names(self):
        for name in (
            "../escape.exe", "safe/../../escape.exe", "safe\\..\\escape.exe",
            "/absolute.exe", "C:\\escape.exe", "file.exe:stream", "CON", "nul.txt",
            "nested/COM1.exe", "LPT9.ini", "trailing. ", "trailing.", "safe/./file.exe",
        ):
            with self.subTest(name=name), self.assertRaises(HubError):
                safe_member(name, self.destination)
        self.assertEqual(safe_member("folder/emulator.exe", self.destination), self.destination / "folder" / "emulator.exe")

    def test_zip_validates_every_member_before_writing_any_file(self):
        archive = self.make_zip([("safe.exe", b"safe"), ("../escaped.exe", b"bad")])
        with self.assertRaises(HubError):
            extract_archive(archive, self.destination, "zip", self.cancel)
        self.assertFalse((self.destination / "safe.exe").exists())
        self.assertFalse((self.root / "escaped.exe").exists())

    def test_zip_link_and_case_collisions_are_rejected(self):
        link = zipfile.ZipInfo("emulator.exe")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive = self.make_zip([(link, b"../../outside")])
        with self.assertRaises(HubError):
            extract_archive(archive, self.destination, "zip", self.cancel)
        duplicate = self.make_zip([("Emulator.exe", b"first"), ("emulator.exe", b"second")])
        with self.assertRaises(HubError):
            extract_archive(duplicate, self.destination, "zip", self.cancel)
        self.assertFalse((self.destination / "Emulator.exe").exists())

    def test_tar_links_and_device_files_are_rejected(self):
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.CHRTYPE):
            archive = self.root / "download.tar"
            with tarfile.open(archive, "w") as handle:
                safe = tarfile.TarInfo("safe.exe")
                safe.size = 4
                handle.addfile(safe, io.BytesIO(b"safe"))
                unsafe = tarfile.TarInfo("unsafe")
                unsafe.type = kind
                unsafe.linkname = "../../external"
                handle.addfile(unsafe)
            with self.subTest(kind=kind), self.assertRaises(HubError):
                extract_archive(archive, self.destination, "tar", self.cancel)
            self.assertFalse((self.destination / "safe.exe").exists())

    def test_valid_zip_extracts_and_cancelled_zip_does_not_write(self):
        archive = self.make_zip([("folder/emulator.exe", b"program")])
        extract_archive(archive, self.destination, "zip", self.cancel)
        self.assertEqual((self.destination / "folder/emulator.exe").read_bytes(), b"program")
        self.cancel.set()
        with self.assertRaises(Cancelled):
            extract_archive(archive, self.root / "cancelled", "zip", self.cancel)
        self.assertFalse((self.root / "cancelled" / "folder" / "emulator.exe").exists())

    def test_real_seven_zip_archive_extracts_nested_executable(self):
        import py7zr
        executable = self.root / "source.exe"
        executable.write_bytes(b"program")
        archive = self.root / "download.7z"
        with py7zr.SevenZipFile(archive, "w") as handle:
            handle.write(executable, arcname="folder/emulator.exe")
        extract_archive(archive, self.destination, "7z", self.cancel)
        self.assertEqual((self.destination / "folder/emulator.exe").read_bytes(), b"program")

    def test_expansion_limit_prevents_writes(self):
        archive = self.make_zip([("emulator.exe", b"too large")])
        with patch("core.archives.MAX_EXPANDED", 2), self.assertRaises(HubError):
            extract_archive(archive, self.destination, "zip", self.cancel)
        self.assertFalse((self.destination / "emulator.exe").exists())

    def test_recursive_removal_is_restricted_to_direct_managed_children(self):
        managed = self.root / "managed"
        child = managed / "emulator"
        child.mkdir(parents=True)
        (child / "emulator.exe").write_bytes(b"program")
        external = self.root / "external"
        external.mkdir()
        protected = external / "precious.txt"
        protected.write_text("keep", encoding="utf-8")
        for target in (managed, self.root, external, child / "nested"):
            with self.subTest(target=target), self.assertRaises(HubError):
                remove_managed_tree(target, managed)
        self.assertTrue(protected.exists())
        remove_managed_tree(child, managed)
        self.assertFalse(child.exists())
        self.assertTrue(protected.exists())

    def test_recursive_removal_never_calls_rmtree_when_tree_contains_reparse_point(self):
        managed = self.root / "managed"
        child = managed / "emulator"
        child.mkdir(parents=True)
        fake_stat = Mock(st_file_attributes=0x400, st_mode=stat.S_IFDIR)
        with patch("core.archives.Path.lstat", return_value=fake_stat), patch("core.archives.shutil.rmtree") as remove:
            with self.assertRaises(HubError):
                remove_managed_tree(child, managed)
            remove.assert_not_called()


if __name__ == "__main__":
    unittest.main()
