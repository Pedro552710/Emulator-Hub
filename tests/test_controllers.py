"""Native Eingabedaten sowie bestätigte Controller-Schreibvorgänge isoliert prüfen."""

import ctypes
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch

from core.controllers import (
    ControllerService, XInputBackend, XINPUT_CAPABILITIES, XINPUT_STATE,
)
from core.errors import Cancelled, HubError
from core.installer import HubService
from tests.helpers import TemporaryDirectory, make_catalog, windows_executable


class FakeXInput:
    def __init__(self):
        self.states = {}
        self.calls = []
        self.XInputGetState = Mock(side_effect=self._state)
        self.XInputGetCapabilities = Mock(side_effect=self._caps)

    def _state(self, slot, target):
        self.calls.append(slot)
        if slot not in self.states:
            return 1167
        state = ctypes.cast(target, ctypes.POINTER(XINPUT_STATE)).contents
        pad = state.Gamepad
        for key, value in self.states[slot].items():
            if key != "subtype":
                setattr(pad, key, value)
        return 0

    def _caps(self, slot, flags, target):
        caps = ctypes.cast(target, ctypes.POINTER(XINPUT_CAPABILITIES)).contents
        caps.Type = 1
        caps.SubType = self.states[slot].get("subtype", 1)
        return 0


class XInputTests(unittest.TestCase):
    def test_native_layout_buttons_triggers_and_stick_deadzones(self):
        self.assertEqual(ctypes.sizeof(XINPUT_STATE), 16)
        self.assertEqual(ctypes.sizeof(XINPUT_CAPABILITIES), 20)
        dll = FakeXInput()
        dll.states[2] = {"wButtons": 0x1001 | 0x0020, "sThumbLX": 200,
                         "sThumbLY": -400, "sThumbRX": -32768,
                         "bLeftTrigger": 255, "bRightTrigger": 20}
        states = XInputBackend(dll).poll()
        self.assertEqual(len(states), 1)
        state = states[0]
        self.assertEqual(state["slot"], 2)
        self.assertEqual(state["name"], "XInput-Controller 3")
        self.assertEqual(state["type"], "XInput-Gamepad")
        self.assertEqual(state["buttons"], {"A", "UP", "BACK", "LT"})
        self.assertEqual(state["axes"]["lx"], 0)
        self.assertEqual(state["axes"]["ly"], 0)
        self.assertEqual(state["axes"]["rx"], -1)
        self.assertEqual(state["axes"]["lt"], 1)
        self.assertEqual(state["axes"]["rt"], 0)

    def test_disconnected_slots_are_throttled_and_hotplug_is_detected(self):
        dll = FakeXInput()
        now = [10.0]
        backend = XInputBackend(dll, clock=lambda: now[0])
        self.assertEqual(backend.poll(), [])
        self.assertEqual(dll.calls, [0, 1, 2, 3])
        dll.states[0] = {"wButtons": 0x2000, "subtype": 2}
        now[0] = 11
        self.assertEqual(backend.poll(), [])
        self.assertEqual(len(dll.calls), 4)
        now[0] = 12
        self.assertEqual(backend.poll()[0]["type"], "XInput-Lenkrad")
        now[0] = 12.05
        self.assertEqual(backend.poll()[0]["buttons"], {"B"})
        self.assertEqual(dll.calls[-1], 0)
        del dll.states[0]
        self.assertEqual(backend.poll(), [])


class ControllerConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.catalog, original = make_catalog(self.root)
        self.entry = self.catalog.by_id(original["id"])
        self.entry.update(controller_config="auto", controller_adapter="dolphin_gc_xinput",
                          backup_paths=[{"label": "Einstellungen", "root": "emulator",
                                         "directory": "Config", "type": "directory"}])
        self.hub = HubService(self.catalog, self.root / "data")
        self.emulator = self.root / "emulator"
        self.emulator.mkdir()
        (self.emulator / self.entry["exe"]).write_bytes(windows_executable())
        self.hub.register_manual(self.entry, self.emulator)
        self.folder = self.emulator / "Config"
        self.folder.mkdir()
        self.config = self.folder / "GCPadNew.ini"
        self.original = b"\xef\xbb\xbf; eigene Notiz\r\n[GCPad1]\r\nDevice = DInput/0/Keyboard Mouse\r\nButtons/A = `X`\r\nButtons/A/Range = 30\r\nMain Stick/Dead Zone = 12\r\n\r\n[GCPad2]\r\nDevice = Unveraendert\r\nButtons/A = `Button 9`\r\n"
        self.config.write_bytes(self.original)
        self.main_ini = self.folder / "Dolphin.ini"
        self.main_ini.write_bytes(b"[Core]\r\nSIDevice0 = 6\r\n")
        self.controllers = ControllerService(self.hub)

    def tearDown(self):
        for handler in list(self.hub.logger.handlers):
            handler.close()
            self.hub.logger.removeHandler(handler)
        self.temp.cleanup()

    def test_preview_is_read_only_preserves_other_ports_and_uses_native_names(self):
        preview = self.controllers.preview(self.entry["id"], 2)
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertFalse(self.controllers.backup_dir.exists())
        text = preview["text"]
        self.assertIn("Device = XInput/2/Gamepad", text)
        self.assertIn("Buttons/A = `Button A`", text)
        self.assertIn("Buttons/Z = `Shoulder R`", text)
        self.assertIn("Main Stick/Up = `Left Y+`", text)
        self.assertIn("Triggers/L-Analog = `Trigger L`", text)
        self.assertIn("Buttons/A/Range = 100", text)
        self.assertIn("Main Stick/Dead Zone = 12", text)
        self.assertTrue(text.endswith("[GCPad2]\r\nDevice = Unveraendert\r\nButtons/A = `Button 9`\r\n"))

    def test_apply_requires_confirmation_makes_exact_backup_and_undo_is_safe(self):
        preview = self.controllers.preview(self.entry["id"], 0)
        with self.assertRaisesRegex(HubError, "nicht bestätigt"):
            self.controllers.apply(preview)
        self.assertEqual(self.config.read_bytes(), self.original)
        applied = self.controllers.apply(preview, confirmed=True)
        self.assertEqual(Path(applied["backup"]).read_bytes(), self.original)
        changed = self.config.read_bytes()
        self.assertTrue(changed.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"XInput/0/Gamepad", changed)
        fresh = ControllerService(self.hub)
        self.assertIsNotNone(fresh.last_change(self.entry["id"]))
        with self.assertRaisesRegex(HubError, "nicht bestätigt"):
            fresh.undo(self.entry["id"])
        reverted = fresh.undo(self.entry["id"], confirmed=True)
        self.assertEqual(Path(reverted["backup"]).read_bytes(), changed)
        self.assertEqual(self.config.read_bytes(), self.original)
        self.assertIsNone(fresh.last_change(self.entry["id"]))

    def test_changed_file_or_profile_after_preview_is_not_overwritten(self):
        preview = self.controllers.preview(self.entry["id"], 0)
        self.config.write_bytes(self.original + b"; spaetere Aenderung\r\n")
        with self.assertRaisesRegex(HubError, "seit der Vorschau geändert"):
            self.controllers.apply(preview, confirmed=True)
        self.assertTrue(self.config.read_bytes().endswith(b"spaetere Aenderung\r\n"))
        self.assertFalse(self.controllers.backup_dir.exists())

    def test_native_port_change_after_preview_is_not_overwritten(self):
        preview = self.controllers.preview(self.entry["id"], 0)
        self.main_ini.write_bytes(b"[Core]\nSIDevice0 = 0\n")
        with self.assertRaisesRegex(HubError, "Dolphin.ini wurde seit der Vorschau"):
            self.controllers.apply(preview, confirmed=True)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_undo_protects_external_changes_and_corrupted_backup(self):
        preview = self.controllers.preview(self.entry["id"], 0)
        applied = self.controllers.apply(preview, confirmed=True)
        changed = self.config.read_bytes()
        self.config.write_bytes(changed + b"; neu\r\n")
        with self.assertRaisesRegex(HubError, "außerhalb des Hubs geändert"):
            self.controllers.undo(self.entry["id"], confirmed=True)
        self.config.write_bytes(changed)
        Path(applied["backup"]).write_bytes(b"beschaedigte Sicherung")
        with self.assertRaisesRegex(HubError, "Sicherung ist beschädigt"):
            self.controllers.undo(self.entry["id"], confirmed=True)
        self.assertEqual(self.config.read_bytes(), changed)

    def test_cancelled_apply_and_backup_failure_do_not_change_config(self):
        preview = self.controllers.preview(self.entry["id"], 0)
        event = threading.Event()
        event.set()
        with self.assertRaises(Cancelled):
            self.controllers.apply(preview, confirmed=True, cancel_event=event)
        with patch.object(self.controllers, "_backup", side_effect=HubError("Sicherung fehlgeschlagen")):
            with self.assertRaisesRegex(HubError, "Sicherung fehlgeschlagen"):
                self.controllers.apply(preview, confirmed=True)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_failed_write_preserves_original_and_reliable_undo_history(self):
        applied = self.controllers.apply(self.controllers.preview(self.entry["id"], 0), confirmed=True)
        previous = self.controllers.last_change(self.entry["id"])
        preview = self.controllers.preview(self.entry["id"], 1)
        with patch.object(self.controllers, "_write", side_effect=HubError("Schreiben fehlgeschlagen")):
            with self.assertRaisesRegex(HubError, "Schreiben fehlgeschlagen"):
                self.controllers.apply(preview, confirmed=True)
        self.assertIn(b"XInput/0/Gamepad", self.config.read_bytes())
        self.assertEqual(self.controllers.last_change(self.entry["id"])["id"], previous["id"])
        self.assertEqual(Path(applied["backup"]).read_bytes(), self.original)
        self.controllers.undo(self.entry["id"], confirmed=True)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_missing_file_wrong_port_or_duplicate_section_requires_manual_setup(self):
        self.main_ini.write_bytes(b"[Core]\nSIDevice0 = 12\n")
        with self.assertRaisesRegex(HubError, "nicht als Standard-Controller"):
            self.controllers.preview(self.entry["id"], 0)
        self.main_ini.write_bytes(b"[Core]\nSIDevice0 = 6\n")
        self.config.write_bytes(b"[GCPad1]\n[GCPad1]\n")
        with self.assertRaisesRegex(HubError, "genau einen Abschnitt"):
            self.controllers.preview(self.entry["id"], 0)
        self.config.unlink()
        with self.assertRaisesRegex(HubError, "vorhandene Konfigdatei"):
            self.controllers.preview(self.entry["id"], 0)

    def test_library_game_paths_and_reparse_points_are_not_written(self):
        from core.state import write_json
        write_json(self.hub.data_dir / "library.json", {"schema_version": 1, "games": [{"path": str(self.config)}]})
        with self.assertRaisesRegex(HubError, "Spiel-Datei"):
            self.controllers.preview(self.entry["id"], 0)
        write_json(self.hub.data_dir / "library.json", {"schema_version": 1, "games": []})
        from types import SimpleNamespace
        original_lstat = Path.lstat

        def reparse(path):
            return SimpleNamespace(st_file_attributes=0x400, st_mode=0) if path == self.folder else original_lstat(path)

        with patch("pathlib.Path.lstat", reparse):
            with self.assertRaisesRegex(HubError, "Junctions"):
                self.controllers.preview(self.entry["id"], 0)
        self.assertEqual(self.config.read_bytes(), self.original)

    def test_preview_cannot_be_changed_into_an_arbitrary_file_write(self):
        preview = self.controllers.preview(self.entry["id"], 0)
        other = self.root / "anderes.ini"
        other.write_bytes(b"unveraendert")
        preview.update(path=str(other), text="unerwuenscht")
        self.controllers.apply(preview, confirmed=True)
        self.assertEqual(other.read_bytes(), b"unveraendert")
        self.assertIn(b"XInput/0/Gamepad", self.config.read_bytes())

    def test_own_existing_config_selection_and_manual_adapter(self):
        self.controllers.set_config_path(self.entry["id"], self.config)
        self.assertEqual(self.controllers.config_path(self.entry["id"]), self.config)
        with self.assertRaisesRegex(HubError, "GCPadNew.ini"):
            self.controllers.set_config_path(self.entry["id"], self.main_ini)
        self.entry["controller_config"] = "manuell"
        self.assertFalse(self.controllers.can_auto(self.entry["id"]))
        self.assertIn("Controller", self.controllers.manual_guide(self.entry["id"]))
        with self.assertRaisesRegex(HubError, "manuelle Controller"):
            self.controllers.preview(self.entry["id"], 0)


if __name__ == "__main__":
    unittest.main()
