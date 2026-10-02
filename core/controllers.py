"""XInput-Livetest und bestätigte, gesicherte Controller-Konfiguration.

Die einzige automatische Zuordnung ist ein vorhandenes Dolphin-GameCube-Profil
für Port 1. Wii, andere Eingabebackends und andere Emulatoren bleiben manuell.
"""

from __future__ import annotations

import configparser
import copy
import ctypes
from datetime import datetime, timezone
import hashlib
import math
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

from .errors import Cancelled, HubError
from .profiles import assert_not_game_file, game_protection


CONTROLLER_GUIDES = {
    "mesen": "Mesen öffnen → Einstellungen/Settings → Eingabe/Input. Controller für Spieler 1 wählen, jede Taste zuordnen und speichern.",
    "bsnes": "bsnes: Settings → Input; Snes9x: Input → Input Configuration. Controller für Spieler 1 auswählen, Tasten und Steuerkreuz zuordnen und speichern. Die beiden Programme verwenden unterschiedliche Konfigformate.",
    "sameboy": "SameBoy öffnen und in den Einstellungen den Bereich für Controller/Steuerung wählen. Das angeschlossene Gamepad auswählen, die Game-Boy-Tasten zuordnen und speichern.",
    "mgba": "mGBA öffnen → Werkzeuge/Tools → Einstellungen/Settings → Controller. Gamepad wählen, Tasten zuordnen und mit Übernehmen speichern.",
    "mupen64plus": "Mupen64Plus verwendet je nach Oberfläche ein anderes Eingabemenü und Plugin. In deiner Oberfläche die Eingabeeinstellungen von Input-SDL für Spieler 1 öffnen, Gamepad wählen und zuordnen. Keine automatische Plugin-Konfiguration durch den Hub.",
    "dolphin": "Dolphin schließen. Zuvor in Controller → GameCube-Port 1 „Standard-Controller“ wählen, Konfigurieren öffnen und speichern. Danach die aktive GCPadNew.ini im Assistenten auswählen. Automatik gilt nur für GameCube-Port 1 mit XInput-Gamepad; Wii-Fernbedienung und Erweiterungen separat in Dolphin einstellen.",
    "melonds": "melonDS öffnen → Config → Input and hotkeys. Gamepad für Spieler 1 wählen, Tasten und gegebenenfalls Touchscreen-Ersatz zuordnen und speichern.",
    "azahar": "Azahar öffnen → Emulation → Konfigurieren → Steuerung. Eingabegerät wählen, Tasten und Sticks zuordnen und speichern. Touchscreen bleibt gesondert einzurichten.",
    "cemu": "Cemu öffnen → Options → Input settings. Controller 1 und emulierten Controllertyp wählen, API/Gamepad auswählen, Tasten zuordnen und ein Profil speichern.",
    "duckstation": "DuckStation öffnen → Einstellungen → Controller. Globales Profil oder Spielprofil und Port 1 wählen, Gamepad automatisch im Emulator zuordnen oder die Tasten einzeln setzen und speichern.",
    "pcsx2": "PCSX2 öffnen → Einstellungen → Controller. Eingabequelle aktivieren, Controller-Port 1 wählen und im Emulator automatisch zuordnen oder jede Taste setzen. Spielprofile können globale Einstellungen übersteuern.",
    "rpcs3": "RPCS3 öffnen → Pads. Für Spieler 1 den passenden Handler (z. B. XInput) und Controller wählen, Tasten testen und das Profil speichern. Spielbezogene Pad-Profile gesondert prüfen.",
    "ppsspp": "PPSSPP öffnen → Einstellungen → Steuerung → Tastenbelegung. Gamepad-Tasten und Analogstick zuordnen. Änderungen werden von PPSSPP gespeichert.",
    "vita3k": "Vita3K öffnen und in den Einstellungen den Bereich für Controller/Eingabe wählen. Gamepad und Tasten zuordnen; Touch- und Rückseitenfunktionen gesondert einstellen. Der genaue Menüname hängt von der Version ab.",
    "blastem-genesis-plus-gx": "BlastEm: Eingabeeinstellungen in der verwendeten Oberfläche öffnen und das Gamepad zuordnen. Genesis Plus GX ist ein Core: Controller in der verwendeten Host-Anwendung (z. B. RetroArch) konfigurieren. Daher keine gemeinsame automatische Konfigdatei.",
    "mednafen-saturn": "Mednafen mit einem eigenen Spiel starten und Alt+Shift+1 für die interaktive Zuordnung von Port 1 verwenden; jede angeforderte Richtung/Taste betätigen. Mednafen speichert die Belegung selbst. Bei Yaba Sanshiro die Controller-Einstellungen der jeweiligen Oberfläche verwenden.",
    "flycast": "Flycast öffnen → Settings → Controls. Gamepad und Port A auswählen, Map öffnen und Tasten zuordnen. Spezielle Spiel- oder Arcade-Belegungen bei Bedarf separat anpassen.",
    "xemu": "xemu öffnen → Input. Für Port 1 das angeschlossene Gamepad auswählen. Falls der Controller nicht angeboten wird, den passenden Treiber bzw. einen XInput-kompatiblen Modus verwenden.",
    "xenia-canary": "Xenia verwendet unter Windows vor allem XInput-kompatible Controller. Gamepad anschließen, den XInput-Modus des Geräts aktivieren und im Spiel testen. Der Hub ändert keine buildabhängigen Xenia-Konfigurationen.",
    "stella": "Stella öffnen → Options → Input Settings. Joystick für Spieler 1 und Tasten zuordnen; Paddles und andere Controllertypen benötigen eine eigene Zuordnung.",
    "mednafen-pcengine": "Mednafen mit einem eigenen Spiel starten und Alt+Shift+1 für die interaktive Zuordnung von Port 1 verwenden; jede angeforderte Richtung/Taste betätigen. Mednafen speichert die Belegung selbst.",
    "finalburn-neo-mame": "FinalBurn Neo: Input → Map game inputs öffnen und Tasten für das laufende Spiel setzen. MAME: Tab → Eingabeeinstellungen öffnen und allgemeine oder spielbezogene Eingabe zuordnen. Standalone-Programme und Cores verwenden unterschiedliche Formate.",
}

CONTROLLER_SOURCES = {
    "xinput": "https://learn.microsoft.com/en-us/windows/win32/xinput/getting-started-with-xinput",
    "dolphin_xinput": "https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/InputCommon/ControllerInterface/XInput/XInput.cpp",
    "dolphin_profile": "https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/InputCommon/ControllerEmu/ControlGroup/ControlGroup.cpp",
    "dolphin_device": "https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/InputCommon/ControllerEmu/ControllerEmu.cpp",
    "dolphin_port": "https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/Core/HW/SI/SI_Device.h",
}


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [("wButtons", ctypes.c_uint16), ("bLeftTrigger", ctypes.c_uint8),
                ("bRightTrigger", ctypes.c_uint8), ("sThumbLX", ctypes.c_int16),
                ("sThumbLY", ctypes.c_int16), ("sThumbRX", ctypes.c_int16),
                ("sThumbRY", ctypes.c_int16)]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint32), ("Gamepad", XINPUT_GAMEPAD)]


class XINPUT_VIBRATION(ctypes.Structure):
    _fields_ = [("wLeftMotorSpeed", ctypes.c_uint16), ("wRightMotorSpeed", ctypes.c_uint16)]


class XINPUT_CAPABILITIES(ctypes.Structure):
    _fields_ = [("Type", ctypes.c_uint8), ("SubType", ctypes.c_uint8),
                ("Flags", ctypes.c_uint16), ("Gamepad", XINPUT_GAMEPAD),
                ("Vibration", XINPUT_VIBRATION)]


BUTTON_BITS = {"UP": 0x0001, "DOWN": 0x0002, "LEFT": 0x0004, "RIGHT": 0x0008,
               "START": 0x0010, "BACK": 0x0020, "LS": 0x0040, "RS": 0x0080,
               "LB": 0x0100, "RB": 0x0200, "A": 0x1000, "B": 0x2000,
               "X": 0x4000, "Y": 0x8000}
SUBTYPES = {1: "Gamepad", 2: "Lenkrad", 3: "Arcade-Stick", 4: "Flugstick",
            5: "Tanzmatte", 6: "Gitarre", 7: "Gitarre", 8: "Schlagzeug",
            11: "Bassgitarre", 19: "Arcade-Pad"}


def _stick(x, y, deadzone):
    magnitude = math.hypot(x, y)
    if magnitude <= deadzone:
        return 0.0, 0.0
    strength = min(1.0, (magnitude - deadzone) / (32767 - deadzone))
    return round(x / magnitude * strength, 4), round(y / magnitude * strength, 4)


class XInputBackend:
    """Read-only native polling. XInput provides slots/types, no product names."""

    def __init__(self, dll=None, clock=time.monotonic):
        self._clock = clock
        self._empty_until = {}
        self._types = {}
        self._dll = dll
        self.unavailable_reason = ""
        if dll is None and os.name == "nt":
            for name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
                try:
                    self._dll = ctypes.WinDLL(name, winmode=0x800)  # System32 only
                    break
                except OSError:
                    continue
        if self._dll is None:
            self.unavailable_reason = "XInput ist hier nicht verfügbar. Die Controller-Erkennung benötigt Windows und einen XInput-kompatiblen Treiber."
            self._get_state = self._get_caps = None
        else:
            self._get_state = self._dll.XInputGetState
            self._get_state.argtypes = [ctypes.c_uint32, ctypes.POINTER(XINPUT_STATE)]
            self._get_state.restype = ctypes.c_uint32
            self._get_caps = getattr(self._dll, "XInputGetCapabilities", None)
            if self._get_caps is not None:
                self._get_caps.argtypes = [ctypes.c_uint32, ctypes.c_uint32,
                                           ctypes.POINTER(XINPUT_CAPABILITIES)]
                self._get_caps.restype = ctypes.c_uint32

    @property
    def available(self):
        return self._get_state is not None

    def poll(self):
        if not self.available:
            return []
        result = []
        now = self._clock()
        for slot in range(4):
            if now < self._empty_until.get(slot, 0):
                continue
            state = XINPUT_STATE()
            if self._get_state(slot, ctypes.byref(state)) != 0:
                self._empty_until[slot] = now + 2
                self._types.pop(slot, None)
                continue
            self._empty_until.pop(slot, None)
            if slot not in self._types:
                caps = XINPUT_CAPABILITIES()
                self._types[slot] = (caps.SubType if self._get_caps is not None
                                    and self._get_caps(slot, 0, ctypes.byref(caps)) == 0 else 0)
            pad = state.Gamepad
            lx, ly = _stick(pad.sThumbLX, pad.sThumbLY, 7849)
            rx, ry = _stick(pad.sThumbRX, pad.sThumbRY, 8689)
            buttons = {name for name, bit in BUTTON_BITS.items() if pad.wButtons & bit}
            for name, value in (("LT", pad.bLeftTrigger), ("RT", pad.bRightTrigger)):
                if value > 30:
                    buttons.add(name)
            result.append({"slot": slot, "name": f"XInput-Controller {slot + 1}",
                           "type": "XInput-" + SUBTYPES.get(self._types[slot], "Gerät"),
                           "subtype": self._types[slot], "buttons": buttons,
                           "axes": {"lx": lx, "ly": ly, "rx": rx, "ry": ry,
                                    "lt": max(0, pad.bLeftTrigger - 30) / 225,
                                    "rt": max(0, pad.bRightTrigger - 30) / 225}})
        return result


def _plain_path(path):
    for item in (path, *path.parents):
        try:
            info = item.lstat()
        except FileNotFoundError:
            continue
        if item.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise HubError("Controller-Einstellungen dürfen nicht über Verknüpfungen oder Junctions geändert werden. Bitte den tatsächlichen Profilordner auswählen.")


def _read_config(path):
    _plain_path(path)
    try:
        if not path.is_file() or path.stat().st_size > 4 * 1024 * 1024:
            raise HubError(f"Eine vorhandene Konfigdatei unter 4 MB wird benötigt: {path}")
        return path.read_bytes()
    except OSError as exc:
        raise HubError(f"Die Controller-Konfigdatei konnte nicht gelesen werden: {path}\n{exc}") from None


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _cancel(event):
    if event is not None and event.is_set():
        raise Cancelled()


def _dolphin_mapping(slot):
    controls = {
        "Buttons/A": "`Button A`", "Buttons/B": "`Button B`",
        "Buttons/X": "`Button X`", "Buttons/Y": "`Button Y`",
        "Buttons/Z": "`Shoulder R`", "Buttons/Start": "`Start`",
        "D-Pad/Up": "`Pad N`", "D-Pad/Down": "`Pad S`",
        "D-Pad/Left": "`Pad W`", "D-Pad/Right": "`Pad E`",
        "Main Stick/Up": "`Left Y+`", "Main Stick/Down": "`Left Y-`",
        "Main Stick/Left": "`Left X-`", "Main Stick/Right": "`Left X+`",
        "C-Stick/Up": "`Right Y+`", "C-Stick/Down": "`Right Y-`",
        "C-Stick/Left": "`Right X-`", "C-Stick/Right": "`Right X+`",
        "Triggers/L": "`Shoulder L` | (`Trigger L` > 0.9)",
        "Triggers/R": "`Trigger R` > 0.9",
        "Triggers/L-Analog": "`Trigger L`", "Triggers/R-Analog": "`Trigger R`",
    }
    return {"Device": f"XInput/{slot}/Gamepad", **controls,
            **{key + "/Range": "100" for key in controls}}


def _replace_dolphin_section(raw, slot):
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise HubError("Diese Dolphin-Konfiguration ist nicht als UTF-8 lesbar. Bitte im Emulator neu speichern; sie wurde nicht geändert.") from None
    ending = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    starts = [(index, match.group(1)) for index, line in enumerate(lines)
              if (match := re.fullmatch(r"\s*\[([^\]]+)\]\s*", line.rstrip("\r\n")))]
    targets = [index for index, name in starts if name == "GCPad1"]
    if len(targets) != 1:
        raise HubError("Die vorhandene GCPadNew.ini muss genau einen Abschnitt [GCPad1] enthalten. Bitte Port 1 zunächst in Dolphin konfigurieren und speichern.")
    start = targets[0]
    end = next((index for index, _ in starts if index > start), len(lines))
    values = _dolphin_mapping(slot)
    seen = set()
    replacement = []
    for line in lines[start + 1:end]:
        match = re.match(r"\s*([^#;=]+?)\s*=", line)
        key = match.group(1).strip() if match else None
        if key in values:
            if key in seen:
                raise HubError("Die Controller-Konfiguration enthält doppelte Eingabezuordnungen. Bitte zuerst in Dolphin korrigieren; sie wurde nicht geändert.")
            seen.add(key)
            replacement.append(f"{key} = {values[key]}{ending}")
        else:
            replacement.append(line)
    if replacement and not replacement[-1].endswith(("\n", "\r")):
        replacement[-1] += ending
    replacement.extend(f"{key} = {value}{ending}" for key, value in values.items() if key not in seen)
    if not lines[start].endswith(("\n", "\r")):
        lines[start] += ending
    output = "".join([*lines[:start + 1], *replacement, *lines[end:]])
    return (b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b"") + output.encode("utf-8")


class ControllerService:
    """Create read-only previews, then exact backups and atomic confirmed writes."""

    def __init__(self, hub):
        self.hub = hub
        self._previews = {}
        self.backup_dir = Path(hub.data_dir) / "controller-backups"

    def _entry(self, emulator_id):
        entry = self.hub.catalog.by_id(emulator_id)
        if entry is None:
            raise HubError("Der gewählte Emulator ist nicht mehr im Katalog vorhanden.")
        return entry

    def manual_guide(self, emulator_id):
        entry = self._entry(emulator_id)
        return entry.get("controller_manual") or CONTROLLER_GUIDES.get(emulator_id, "Im Emulator die Einstellungen für Eingabe/Controller öffnen, das Gamepad wählen, alle Tasten zuordnen und speichern. Der Menüname hängt von der Version ab.")

    def can_auto(self, emulator_id):
        entry = self._entry(emulator_id)
        return entry.get("controller_config") == "auto" and entry.get("controller_adapter") == "dolphin_gc_xinput"

    def config_path(self, emulator_id):
        if not self.can_auto(emulator_id):
            raise HubError("Für diesen Emulator wird eine manuelle Controller-Einrichtung angeboten.")
        if not self.hub.is_installed(emulator_id):
            raise HubError("Bitte Dolphin zuerst installieren oder seinen vorhandenen Ordner zuordnen.")
        overrides = self.hub.settings.get("controller_config_paths", {})
        if not isinstance(overrides, dict):
            raise HubError("Die Controller-Profilpfade in settings.json sind ungültig.")
        own = overrides.get(emulator_id)
        if own:
            if not isinstance(own, str) or not Path(own).is_absolute():
                raise HubError("Ein Controller-Profil benötigt einen vollständigen Dateipfad.")
            path = Path(own).absolute()
        else:
            profiles = self.hub.profile_paths(self._entry(emulator_id))
            configs = [p for p in profiles if p.get("label") == "Einstellungen" and p.get("type") == "directory"]
            if len(configs) != 1:
                raise HubError("Bitte die aktive GCPadNew.ini über „Konfigdatei wählen“ zuordnen.")
            path = configs[0]["path"] / "GCPadNew.ini"
        if path.name.casefold() != "gcpadnew.ini":
            raise HubError("Für Dolphin wird ausschließlich die aktive Datei GCPadNew.ini unterstützt.")
        _plain_path(path)
        assert_not_game_file(path, game_protection(self.hub.data_dir, self.hub.settings))
        return path

    def set_config_path(self, emulator_id, path):
        if not self.can_auto(emulator_id):
            raise HubError("Für diesen Emulator ist keine automatische Konfiguration vorgesehen.")
        path = Path(path).absolute()
        if path.name.casefold() != "gcpadnew.ini":
            raise HubError("Bitte die vorhandene GCPadNew.ini aus dem aktiven Dolphin-Profil auswählen.")
        _read_config(path)
        assert_not_game_file(path, game_protection(self.hub.data_dir, self.hub.settings))
        overrides = self.hub.settings.get("controller_config_paths", {})
        if not isinstance(overrides, dict):
            raise HubError("Die Controller-Profilpfade in settings.json sind ungültig.")
        self.hub.settings.set("controller_config_paths", {**overrides, emulator_id: str(path)})

    def preview(self, emulator_id, slot, progress=None, log=None, cancel_event=None):
        with self.hub._lock:
            _cancel(cancel_event)
            if type(slot) is not int or not 0 <= slot <= 3:
                raise HubError("Bitte einen gültigen XInput-Controller auswählen.")
            path = self.config_path(emulator_id)
            dolphin_ini = path.parent / "Dolphin.ini"
            ini = configparser.ConfigParser(interpolation=None)
            try:
                ini.read_string(_read_config(dolphin_ini).decode("utf-8-sig"))
                # Port 1's native default is a standard controller; absent key is valid.
                standard = ini.getint("Core", "SIDevice0", fallback=6) == 6
            except (configparser.Error, UnicodeError, ValueError):
                raise HubError("Dolphin.ini ist nicht eindeutig lesbar. Bitte GameCube-Port 1 im Emulator konfigurieren und Dolphin schließen.") from None
            if not standard:
                raise HubError("GameCube-Port 1 ist nicht als Standard-Controller eingestellt. Bitte dies zuerst in Dolphin unter Controller ändern und speichern; danach Dolphin schließen.")
            original = _read_config(path)
            modified = _replace_dolphin_section(original, slot)
            token = uuid.uuid4().hex
            result = {"token": token, "emulator_id": emulator_id, "slot": slot,
                      "path": str(path), "text": modified.decode("utf-8-sig"),
                      "original_hash": _digest(original), "exists": True}
            self._previews = {token: {**result, "original": original, "modified": modified,
                                     "dolphin_hash": _digest(_read_config(dolphin_ini))}}
            if progress:
                progress(100, "Vorschau bereit · es wurde keine Konfigdatei geändert")
            return result

    def _history(self):
        history = self.hub.settings.get("controller_history", [])
        if not isinstance(history, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not isinstance(item.get("emulator_id"), str)
            or item.get("state") not in {"pending", "applied", "undone"}
            or any(not isinstance(item.get(key), str) or not Path(item[key]).is_absolute()
                   for key in ("path", "backup"))
            or any(not isinstance(item.get(key), str)
                   or re.fullmatch(r"[0-9a-f]{64}", item[key]) is None
                   for key in ("original_hash", "applied_hash"))
            for item in history
        ):
            raise HubError("Der Verlauf der Controller-Sicherungen in settings.json ist ungültig.")
        return history

    def last_change(self, emulator_id):
        return next((item for item in reversed(self._history()) if item.get("emulator_id") == emulator_id
                     and item.get("state") in {"pending", "applied"}), None)

    def _backup(self, emulator_id, data, suffix=""):
        _plain_path(self.backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        path = self.backup_dir / f"{emulator_id}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S-%f}-{uuid.uuid4().hex}{suffix}.bak"
        _plain_path(path)
        try:
            with path.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            if _digest(path.read_bytes()) != _digest(data):
                raise HubError("Die Sicherung der Controller-Konfiguration konnte nicht geprüft werden. Die Konfiguration bleibt unverändert.")
        except OSError as exc:
            raise HubError(f"Die Controller-Sicherung konnte nicht erstellt werden. Die Konfiguration bleibt unverändert. {exc}") from None
        return path

    @staticmethod
    def _write(path, data):
        _plain_path(path)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix="hub-controller-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            _plain_path(path)
            os.replace(temporary, path)
        except OSError as exc:
            raise HubError(f"Die Controller-Konfiguration konnte nicht geschrieben werden: {exc}") from None
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)

    def apply(self, preview, *, confirmed=False, progress=None, log=None, cancel_event=None):
        if confirmed is not True:
            raise HubError("Die Controller-Änderung wurde nicht bestätigt. Es wurde nichts überschrieben.")
        with self.hub._lock:
            _cancel(cancel_event)
            pending = self._previews.get(preview.get("token") if isinstance(preview, dict) else None)
            if pending is None:
                raise HubError("Diese Vorschau ist nicht mehr gültig. Bitte eine neue Vorschau erstellen.")
            path = self.config_path(pending["emulator_id"])
            if str(path) != pending["path"] or _digest(_read_config(path)) != pending["original_hash"]:
                raise HubError("Die Konfigdatei oder ihre Zuordnung wurde seit der Vorschau geändert. Bitte Dolphin schließen und eine neue Vorschau erstellen; es wurde nichts überschrieben.")
            if _digest(_read_config(path.parent / "Dolphin.ini")) != pending["dolphin_hash"]:
                raise HubError("Dolphin.ini wurde seit der Vorschau geändert. Bitte eine neue Vorschau erstellen.")
            if pending["modified"] == pending["original"]:
                return {"path": str(path), "backup": "", "message": "Diese Tastenbelegung ist bereits vorhanden."}
            history = self._history()
            _cancel(cancel_event)
            backup = self._backup(pending["emulator_id"], pending["original"])
            item = {"id": uuid.uuid4().hex, "emulator_id": pending["emulator_id"],
                    "path": str(path), "backup": str(backup), "original_hash": pending["original_hash"],
                    "applied_hash": _digest(pending["modified"]), "state": "pending",
                    "created_at": datetime.now(timezone.utc).isoformat()}
            self.hub.settings.set("controller_history", [*history, item])
            # After backup and journal, commit is short and deliberately indivisible.
            try:
                if _digest(_read_config(path)) != item["original_hash"]:
                    raise HubError("Die Konfiguration wurde während der Sicherung geändert. Sie wurde nicht überschrieben; bitte neu prüfen.")
                self._write(path, pending["modified"])
            except HubError:
                # A failed write must not hide an earlier successful undo entry.
                try:
                    self.hub.settings.set("controller_history", history)
                except HubError:
                    pass  # Exact snapshot remains on disk even if settings are unwritable.
                raise
            item["state"] = "applied"
            warning = ""
            try:
                self.hub.settings.set("controller_history", [*history, item])
            except HubError:
                warning = " Die Änderung ist gesichert, aber der Verlaufsstatus konnte nicht aktualisiert werden. Rückgängig bleibt über den gespeicherten Sicherungseintrag möglich."
            self._previews.clear()
            if log:
                log(f"GameCube-Port 1 eingerichtet. Vorherige Konfiguration gesichert: {backup}")
            if progress:
                progress(100, "Controller-Belegung gespeichert")
            return {"path": str(path), "backup": str(backup), "message": "GameCube-Port 1 eingerichtet. Dolphin neu starten." + warning}

    def undo(self, emulator_id, *, confirmed=False, progress=None, log=None, cancel_event=None):
        if confirmed is not True:
            raise HubError("Das Rückgängigmachen wurde nicht bestätigt. Es wurde nichts überschrieben.")
        with self.hub._lock:
            _cancel(cancel_event)
            history = self._history()
            original = self.last_change(emulator_id)
            if original is None:
                raise HubError("Für diesen Emulator ist keine Controller-Änderung zum Rückgängigmachen gespeichert.")
            item = copy.deepcopy(original)
            path = self.config_path(emulator_id)
            if str(path) != item.get("path"):
                raise HubError("Die Profilzuordnung hat sich geändert. Bitte die ursprüngliche Konfigdatei wieder zuordnen.")
            current = _read_config(path)
            if _digest(current) != item.get("applied_hash"):
                raise HubError("Die Controller-Konfiguration wurde inzwischen außerhalb des Hubs geändert. Sie wird nicht überschrieben. Die ursprüngliche Sicherung liegt unter: " + str(item.get("backup", "")))
            backup = Path(item.get("backup", ""))
            if (not backup.is_absolute() or backup.parent.resolve() != self.backup_dir.resolve()
                    or backup.suffix != ".bak"):
                raise HubError("Der gespeicherte Controller-Sicherungspfad ist ungültig.")
            previous = _read_config(backup)
            if _digest(previous) != item.get("original_hash"):
                raise HubError("Die ursprüngliche Controller-Sicherung ist beschädigt. Die aktuelle Konfiguration bleibt unverändert.")
            _cancel(cancel_event)
            safety = self._backup(emulator_id, current, "-vor-rueckgaengig")
            item["undo_backup"] = str(safety)
            updated = [item if row.get("id") == item["id"] else row for row in history]
            self.hub.settings.set("controller_history", updated)
            if _digest(_read_config(path)) != item["applied_hash"]:
                raise HubError("Die Konfiguration wurde während der Sicherung geändert. Sie wurde nicht überschrieben.")
            self._write(path, previous)
            item["state"] = "undone"
            warning = ""
            try:
                self.hub.settings.set("controller_history", updated)
            except HubError:
                warning = " Der Verlaufsstatus konnte nicht gespeichert werden. Die wiederhergestellte Datei und beide Sicherungen sind vorhanden."
            if log:
                log(f"Controller-Änderung rückgängig. Stand vor Rücknahme gesichert: {safety}")
            if progress:
                progress(100, "Vorherige Controller-Konfiguration wiederhergestellt")
            return {"path": str(path), "backup": str(safety), "message": "Vorherige Controller-Konfiguration wiederhergestellt. Dolphin neu starten." + warning}
