"""Der alternative offizielle Direktdownload nutzt dieselben Sicherheitsregeln."""
import hashlib
import io
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile

from core.errors import HubError
from core.installer import HubService
from tests.helpers import TemporaryDirectory, make_catalog, Response, windows_executable


class DirectDownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.catalog, self.entry = make_catalog(self.temp.name)
        self.entry.update(install_methode="auto_direct", direct_url="https://github.com/official/emulator/releases/download/v1/emulator.zip", direct_version="1.0")
        self.service = HubService(self.catalog, Path(self.temp.name) / "data")
        self.addCleanup(self.close_logger)
        self.event = threading.Event()

    def close_logger(self):
        for handler in list(self.service.logger.handlers):
            handler.close()
            self.service.logger.removeHandler(handler)

    def archive(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as handle:
            handle.writestr("emulator.exe", windows_executable())
        return buffer.getvalue()

    def test_direct_archive_verifies_configured_hash_and_version(self):
        body = self.archive()
        self.entry["sha256"] = hashlib.sha256(body).hexdigest()
        with patch.object(self.service.policy, "get", return_value=Response(body)):
            record = self.service.install(self.entry, Mock(), Mock(), self.event)
        self.assertEqual(record["version"], "1.0")
        self.assertEqual(record["method"], "auto_direct")
        self.assertTrue(self.service.is_installed(self.entry["id"]))

    def test_direct_nonofficial_url_never_downloads(self):
        self.entry["direct_url"] = "https://portal.example/emulator.zip"
        with patch.object(self.service.policy, "get") as request:
            with self.assertRaises(HubError):
                self.service.install(self.entry, Mock(), Mock(), self.event)
        request.assert_not_called()

    def test_interactive_official_installer_launches_but_requires_manual_registration(self):
        body = windows_executable()
        self.entry.update(archive_type="installer", direct_url="https://github.com/official/emulator/releases/download/v1/setup.exe", sha256=hashlib.sha256(body).hexdigest())
        with patch.object(self.service.policy, "get", return_value=Response(body)), patch("core.installer.subprocess.Popen") as launch:
            with self.assertRaisesRegex(HubError, "Installer wurde gestartet"):
                self.service.install(self.entry, Mock(), Mock(), self.event)
        self.assertFalse(self.service.installed)
        path = Path(launch.call_args.args[0][0])
        self.assertTrue(path.is_file())
        self.assertTrue(path.is_relative_to(self.service.data_dir / "downloads"))
        self.assertFalse(launch.call_args.kwargs["shell"])


if __name__ == "__main__":
    unittest.main()
