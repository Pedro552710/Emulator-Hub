"""Favoriten, letzte Starts und Einstellungen mit Schutz vor parallelen Updates."""
import copy
from datetime import datetime, timezone
from pathlib import Path
import threading

from .errors import HubError
from .state import read_json, write_json

DEFAULTS = {"schema_version": 1, "favorites": [], "recent_emulators": [], "game_folders": []}


class SettingsStore:
    def __init__(self, data_dir):
        self.path = Path(data_dir) / "settings.json"
        self.lock = threading.RLock()
        loaded = read_json(self.path, DEFAULTS, "Einstellungen")
        if not isinstance(loaded, dict) or loaded.get("schema_version", 1) != 1:
            raise HubError("settings.json enthält keine gültigen Einstellungen.")
        self._data = {**copy.deepcopy(DEFAULTS), **loaded}
        for key in ("favorites", "game_folders"):
            if not isinstance(self._data[key], list) or any(not isinstance(v, str) for v in self._data[key]):
                raise HubError(f"settings.json: '{key}' muss eine Liste mit Texten sein.")
        if not isinstance(self._data["recent_emulators"], list) or any(
            not isinstance(v, dict) or not isinstance(v.get("id"), str) or not isinstance(v.get("last_used"), str)
            for v in self._data["recent_emulators"]
        ):
            raise HubError("settings.json enthält ungültige zuletzt benutzte Emulatoren.")

    def get(self, key, default=None):
        with self.lock:
            return copy.deepcopy(self._data.get(key, default))

    def set(self, key, value):
        with self.lock:
            data = {**self._data, key: copy.deepcopy(value)}
            write_json(self.path, data, "Einstellungen")
            self._data = data

    @property
    def favorites(self):
        return self.get("favorites", [])

    @property
    def recent_emulators(self):
        return self.get("recent_emulators", [])

    def toggle_favorite(self, identifier):
        with self.lock:
            favorites = self.favorites
            selected = identifier not in favorites
            if selected:
                favorites.append(identifier)
            else:
                favorites.remove(identifier)
            self.set("favorites", favorites)
            return selected

    def touch_emulator(self, identifier):
        with self.lock:
            recent = [r for r in self.recent_emulators if r["id"] != identifier]
            recent.insert(0, {"id": identifier, "last_used": datetime.now(timezone.utc).isoformat()})
            self.set("recent_emulators", recent[:20])
