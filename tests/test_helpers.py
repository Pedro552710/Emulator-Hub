"""Temporäre Testordner bleiben bei Windows-Kurznamen eindeutig und aufräumbar."""

from pathlib import Path
import unittest

from tests.helpers import TemporaryDirectory


class TemporaryDirectoryTests(unittest.TestCase):
    def test_name_is_resolved_and_explicit_cleanup_removes_contents(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.assertEqual(root, root.resolve())
        self.assertTrue(root.is_dir())
        (root / "test.txt").write_text("Test", encoding="utf-8")

        temporary.cleanup()
        self.assertFalse(root.exists())

    def test_context_manager_resolves_path_and_preserves_directory_arguments(self):
        with TemporaryDirectory() as parent:
            with TemporaryDirectory(dir=parent, prefix="hub-", suffix="-test") as name:
                root = Path(name)
                self.assertEqual(root, root.resolve())
                self.assertEqual(root.parent, Path(parent))
                self.assertTrue(root.name.startswith("hub-"))
                self.assertTrue(root.name.endswith("-test"))
                (root / "test.txt").write_text("Test", encoding="utf-8")
            self.assertFalse(root.exists())
        self.assertFalse(Path(parent).exists())
