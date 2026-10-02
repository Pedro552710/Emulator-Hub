from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch
import json

from core.errors import HubError
from core.installer import HubService
from core.settings import SettingsStore
from core.systemcheck import assess, classify_gpu, detect_hardware, load_thresholds
from tests.helpers import TemporaryDirectory, make_catalog


class FoundationsTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_favorites_recent_and_parallel_settings_survive_reload(self):
        settings = SettingsStore(self.root)
        self.assertTrue(settings.toggle_favorite("alpha"))
        settings.touch_emulator("alpha")
        settings.touch_emulator("beta")
        settings.touch_emulator("alpha")
        threads = [threading.Thread(target=settings.set, args=(f"key{i}", i)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        reread = SettingsStore(self.root)
        self.assertEqual(reread.favorites, ["alpha"])
        self.assertEqual([r["id"] for r in reread.recent_emulators], ["alpha", "beta"])
        self.assertEqual([reread.get(f"key{i}") for i in range(8)], list(range(8)))
        self.assertFalse(reread.toggle_favorite("alpha"))

    def test_hardware_assessment_respects_thresholds_and_unknown_gpu(self):
        config = load_thresholds()
        entry = {"pc_anforderung": "Sehr hoch"}
        report = {"cpu_cores": 12, "ram_gb": 64, "gpu_score": 3}
        self.assertEqual(assess(entry, report, config)["status"], "Läuft gut")
        report["ram_gb"] = 8
        self.assertEqual(assess(entry, report, config)["status"], "Zu schwach")
        report.update(ram_gb=64, gpu_score=None)
        assessment = assess(entry, report, config)
        self.assertEqual(assessment["status"], "Grenzwertig")
        self.assertIn("Nicht zuverlässig erkannt", assessment["reason"])
        self.assertEqual(assess(entry, None, config)["status"], "Unbekannt")

    def test_failed_windows_gpu_query_returns_partial_report(self):
        config = load_thresholds()
        with patch("core.systemcheck.subprocess.run", side_effect=OSError("offline local WMI")):
            report = detect_hardware(Mock(), Mock(), threading.Event(), config)
        self.assertGreater(report["ram_gb"], 0)
        self.assertIsNone(report["gpu_score"])
        self.assertTrue(report["warnings"])
        self.assertEqual(classify_gpu("Microsoft Basic Display Adapter", config)[0], "unknown")

    def test_small_hardware_reserved_ram_and_invalid_cached_measurement(self):
        config = load_thresholds()
        entry = {"pc_anforderung": "Sehr hoch"}
        report = {"cpu_cores": 8, "ram_gb": 31.92, "gpu_score": 3}
        self.assertEqual(assess(entry, report, config)["status"], "Läuft gut")
        report["ram_gb"] = "invalid"
        self.assertEqual(assess(entry, report, config)["status"], "Grenzwertig")

    def service(self):
        catalog, entry = make_catalog(self.root)
        service = HubService(catalog, self.root / "data")
        def close():
            for handler in list(service.logger.handlers):
                handler.close()
                service.logger.removeHandler(handler)
        self.addCleanup(close)
        return service, entry

    def test_update_all_continues_after_one_failure_and_reports_total_progress(self):
        service, entry = self.service()
        second = {**entry, "id": "second", "emulator": "Zweiter Emulator"}
        service.catalog.items.append(second)
        service.installed = {e["id"]: {"version": "1.0", "managed": True} for e in (entry, second)}
        progress = Mock()
        with patch.object(service, "check_updates", return_value={entry["id"]: "2.0", "second": "2.0"}), patch.object(service, "install", side_effect=[HubError("Download fehlt"), {}]) as install:
            result = service.update_all(progress, Mock(), threading.Event())
        self.assertEqual(install.call_count, 2)
        self.assertEqual(result["updated"], ["second"])
        self.assertIn(entry["id"], result["failed"])
        self.assertEqual(progress.call_args.args[0], 100)

    def test_corrupt_settings_are_never_silently_replaced(self):
        path = self.root / "settings.json"
        path.write_text("broken", encoding="utf-8")
        with self.assertRaises(HubError):
            SettingsStore(self.root)
        self.assertEqual(path.read_text(), "broken")

    def test_systemcheck_persists_and_reads_editable_config(self):
        service, entry = self.service()
        report = {"cpu_cores": 4, "ram_gb": 8, "gpu_score": 1}
        with patch("core.installer.detect_hardware", return_value=report):
            self.assertEqual(service.systemcheck(Mock(), Mock(), threading.Event()), report)
        self.assertEqual(SettingsStore(service.data_dir).get("system_report"), report)
        self.assertTrue((service.data_dir / "configs" / "system_requirements.json").exists())


if __name__ == "__main__":
    unittest.main()
