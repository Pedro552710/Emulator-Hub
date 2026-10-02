"""Veröffentlichungsprüfung: Risiken erkennen, Inhalte niemals ausgeben."""
import json
from pathlib import Path
import unittest
import zipfile

from tools.audit_publication import audit, inspect_text
from tests.helpers import TemporaryDirectory


class PublicationAuditTests(unittest.TestCase):
    def test_unknown_secret_blocks_and_report_does_not_contain_value(self):
        value = "unrecognized-credential-value"
        findings = inspect_text("core/example.py", "client_secret = " + repr(value))
        self.assertTrue(findings[0]["blocking"])
        self.assertNotIn(value, json.dumps(findings))

    def test_known_mock_secret_is_allowed_only_as_test_fixture(self):
        text = 'client_secret = "TOP_SECRET"'
        self.assertFalse(inspect_text("tests/example.py", text)[0]["blocking"])
        self.assertTrue(inspect_text("core/example.py", text)[0]["blocking"])
        self.assertTrue(inspect_text("tests/example.py", 'client_secret = "unknown-value"')[0]["blocking"])

    def test_personal_path_is_redacted_and_ignored_path_does_not_block(self):
        # Constructed dummy path; no actual local user name in the source.
        path = "C:/" + "Users/" + "ExamplePerson" + "/private/config.json"
        findings = inspect_text("docs/example.md", path)
        self.assertTrue(findings[0]["blocking"])
        self.assertNotIn("ExamplePerson", json.dumps(findings))
        self.assertFalse(inspect_text("test-artifacts/example.log", path, ignored=True)[0]["blocking"])

    def test_gitignore_uses_git_semantics_without_initializing_workspace(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".gitignore").write_text("test-artifacts/\nsettings.json\n", encoding="utf-8")
            (root / "README.md").write_text("Beispiel", encoding="utf-8")
            (root / "settings.json").write_text('{"password": "unknown-value"}', encoding="utf-8")
            artifacts = root / "test-artifacts"
            artifacts.mkdir()
            (artifacts / "own.nes").write_bytes(b"synthetic test data")
            report = audit(root)
            self.assertEqual(report["publication_files"], [".gitignore", "README.md"])
            self.assertFalse(report["blocking_findings"])
            self.assertEqual(len(report["binary_findings"]), 1)
            self.assertFalse((root / ".git").exists())

    def test_workbook_xml_secret_and_embedded_game_are_examined(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".gitignore").write_text("", encoding="utf-8")
            with zipfile.ZipFile(root / "example.xlsx", "w") as archive:
                archive.writestr("xl/sharedStrings.xml", 'client_secret = "unknown-value"')
                archive.writestr("unexpected/game.nes", b"synthetic test data")
            report = audit(root)
            self.assertTrue(any("example.xlsx!xl/sharedStrings.xml" == row["path"] for row in report["blocking_findings"]))
            self.assertTrue(any(row["path"].endswith("!unexpected/game.nes") for row in report["binary_findings"]))
            self.assertNotIn("unknown-value", json.dumps(report))

    def test_unknown_binary_outside_ignored_folders_blocks(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".gitignore").write_text("", encoding="utf-8")
            (root / "emulator.exe").write_bytes(b"MZ" + b"fake fixture")
            report = audit(root)
            self.assertEqual(report["blocking_findings"][0]["path"], "emulator.exe")

    def test_renamed_binary_and_rom_signatures_block_without_ignoring_markdown(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".gitignore").write_text("", encoding="utf-8")
            (root / "README.md").write_text("# Emulator Hub\nEin normales Markdown-Dokument.", encoding="utf-8")
            assets = root / "assets"
            assets.mkdir()
            (assets / "renamed.dat").write_bytes(b"MZ" + b"synthetic test header")
            (assets / "renamed.png").write_bytes(b"NES\x1a" + b"synthetic test header")
            sega = bytearray(512)
            sega[0x100:0x104] = b"SEGA"
            (root / "renamed.md").write_bytes(sega)
            report = audit(root)
            blockers = {row["path"] for row in report["blocking_findings"]}
            self.assertEqual(blockers, {"assets/renamed.dat", "assets/renamed.png", "renamed.md"})
            self.assertIn("README.md", report["publication_files"])

    def test_dotenv_unquoted_secret_and_url_secret_are_redacted(self):
        value = "unrecognized-credential-value"
        for text in ("CLIENT_SECRET=" + value, "https://example.invalid/?password=" + value):
            with self.subTest(text_type=text.split("=", 1)[0]):
                findings = inspect_text("configuration.example", text)
                self.assertTrue(findings[0]["blocking"])
                self.assertNotIn(value, json.dumps(findings))
        # An ordinary Python variable expression is not a literal .env secret.
        self.assertFalse(inspect_text("core/example.py", "token = uuid.uuid4().hex"))

    def test_unknown_url_credentials_do_not_get_blanket_test_exemption(self):
        findings = inspect_text("tests/example.py", "https://example.invalid/?password=unknown-value")
        self.assertTrue(findings[0]["blocking"])


if __name__ == "__main__":
    unittest.main()
