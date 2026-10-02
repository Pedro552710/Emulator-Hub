"""Bibliothek eigener Dateien: nur Pfade und Metadaten, keine Dateiveränderungen."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import stat
import threading

from .errors import HubError, Cancelled
from .paths import config_path as resolve_config_path
from .state import read_json, write_json


def _path_key(path):
    text = str(Path(path).resolve())
    return text.casefold() if os.name == "nt" else text


def _is_link(path):
    """Auch Windows-Junctions und andere Reparse Points nicht verfolgen."""
    path = Path(path)
    details = path.lstat()
    return path.is_symlink() or bool(
        getattr(details, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
    )


class LibraryStore:
    def __init__(self, data_dir, catalog, settings, launcher=None, config_path=None):
        self.data_dir = Path(data_dir).resolve()
        self.path = self.data_dir / "library.json"
        self.catalog = catalog
        self.settings = settings
        self.launcher = launcher
        self.last_warning = ""
        self._lock = threading.RLock()
        self.config_path = Path(config_path) if config_path is not None else resolve_config_path("extensions.json", self.data_dir)
        self.extension_config = read_json(self.config_path, None, "Die Dateiendungs-Konfiguration")
        if not isinstance(self.extension_config, dict) or self.extension_config.get("schema_version") != 1:
            raise HubError("Die Dateiendungs-Konfiguration benötigt schema_version: 1.")
        extensions = self.extension_config.get("extensions")
        if not isinstance(extensions, dict) or not extensions:
            raise HubError("Die Dateiendungs-Konfiguration benötigt eine nicht leere extensions-Tabelle.")
        self.extensions = {}
        for suffix, consoles in extensions.items():
            values = [consoles] if isinstance(consoles, str) else consoles
            if (
                not isinstance(suffix, str) or not re.fullmatch(r"\.[a-z0-9]+", suffix)
                or not isinstance(values, list) or not values
                or any(not isinstance(c, str) or not c.strip() for c in values)
                or len(set(values)) != len(values)
            ):
                raise HubError("Die Dateiendungs-Konfiguration enthält eine ungültige Endung oder Konsolenliste.")
            self.extensions[suffix] = list(values)
        self.supported_consoles = sorted(
            {e["konsole"] for e in catalog.items} | {c for values in self.extensions.values() for c in values},
            key=str.casefold,
        )
        raw = read_json(self.path, {"schema_version": 1, "games": []}, "Die Spielebibliothek")
        self._games = self._validate_saved(raw)

    def _validate_saved(self, raw):
        if not isinstance(raw, dict) or raw.get("schema_version") != 1 or not isinstance(raw.get("games"), list):
            raise HubError("Die Spielebibliothek ist beschädigt. Bitte library.json sichern und korrigieren oder umbenennen.")
        games = {}
        paths = set()
        for game in raw["games"]:
            if (
                not isinstance(game, dict)
                or any(not isinstance(game.get(k), str) for k in ("id", "path", "name", "last_played"))
                or not game["id"] or not game["name"] or not Path(game["path"]).is_absolute()
                or type(game.get("favorite")) is not bool
                or game.get("console") is not None and (not isinstance(game.get("console"), str) or not game["console"].strip())
                or type(game.get("missing", False)) is not bool
                or type(game.get("assigned_manually", False)) is not bool
                or game.get("emulator_id") is not None and not isinstance(game.get("emulator_id"), str)
            ):
                raise HubError("Die Spielebibliothek enthält einen ungültigen Eintrag. Bitte library.json sichern und korrigieren oder umbenennen.")
            candidates = game.get("candidates", [])
            if not isinstance(candidates, list) or any(not isinstance(c, str) or not c.strip() for c in candidates):
                raise HubError("Die Spielebibliothek enthält eine ungültige Konsolenliste.")
            if game["last_played"]:
                try:
                    datetime.fromisoformat(game["last_played"])
                except ValueError:
                    raise HubError("Die Spielebibliothek enthält ein ungültiges Datum in last_played.") from None
            key = _path_key(game["path"])
            if game["id"] in games or key in paths:
                raise HubError("Die Spielebibliothek enthält doppelte IDs oder Dateipfade.")
            games[game["id"]] = deepcopy(game)
            paths.add(key)
        return games

    @property
    def games(self):
        with self._lock:
            return deepcopy(list(self._games.values()))

    def get_game(self, game_id):
        with self._lock:
            try:
                return deepcopy(self._games[game_id])
            except KeyError:
                raise HubError("Das Spiel wurde in der Bibliothek nicht gefunden. Bitte die Liste erneut laden.") from None

    def _save(self, games):
        write_json(self.path, {"schema_version": 1, "games": list(games.values())}, "Die Spielebibliothek")
        self._games = games

    def set_roots(self, roots):
        if not isinstance(roots, (list, tuple)) or any(not isinstance(p, (str, Path)) or not str(p).strip() for p in roots):
            raise HubError("Bitte eine Liste mit Spielordnern auswählen.")
        unique = {}
        for value in roots:
            path = Path(value).absolute()
            unique.setdefault(_path_key(path), str(path))
        self.settings.set("game_folders", list(unique.values()))

    def scan(self, roots, progress, log, cancel_event):
        """Erfasst ausschließlich reguläre Dateien unter den gewählten Ordnern."""
        files = {}
        errors = []
        seen_roots = set()
        progress(-1, "Eigene Spielordner durchsuchen …")

        def check_cancel():
            if cancel_event.is_set():
                raise Cancelled()

        def report_error(message):
            errors.append(message)
            log(message)

        def walk_error(error):
            report_error(f"Ordner konnte nicht gelesen werden: {error.filename or '?'} ({error.strerror or error})")

        for value in roots:
            check_cancel()
            folder = Path(value).absolute()
            try:
                if _is_link(folder):
                    report_error(f"Verknüpfter Spielordner wird übersprungen: {folder}. Bitte den tatsächlichen Ordner auswählen.")
                    continue
                root = folder.resolve()
                root_key = _path_key(root)
                if root_key in seen_roots:
                    continue
                seen_roots.add(root_key)
                if not root.is_dir():
                    report_error(f"Spielordner wurde nicht gefunden: {folder}")
                    continue
                if root == self.data_dir:
                    report_error(f"Der eigene Hub-Datenordner wird nicht als Spielordner gescannt: {root}")
                    continue
                for current, directories, names in os.walk(root, followlinks=False, onerror=walk_error):
                    check_cancel()
                    current_path = Path(current)
                    # Eine während des Scans geänderte Verknüpfung darf nicht nach außen führen.
                    if _is_link(current_path) or not current_path.resolve().is_relative_to(root):
                        directories[:] = []
                        continue
                    safe_dirs = []
                    for name in directories:
                        check_cancel()
                        child = current_path / name
                        try:
                            if not _is_link(child) and child.resolve().is_relative_to(root) and child.resolve() != self.data_dir:
                                safe_dirs.append(name)
                        except OSError as exc:
                            report_error(f"Unterordner wird übersprungen: {child} ({exc})")
                    directories[:] = safe_dirs
                    for name in names:
                        check_cancel()
                        path = current_path / name
                        suffix = path.suffix.lower()
                        if suffix not in self.extensions:
                            continue
                        try:
                            if _is_link(path) or not path.is_file():
                                continue
                            resolved = path.resolve()
                            if not resolved.is_relative_to(root):
                                continue
                            files.setdefault(_path_key(resolved), resolved)
                        except OSError as exc:
                            report_error(f"Datei wird übersprungen: {path} ({exc})")
                    progress(-1, f"Spielordner durchsuchen · {len(files)} Dateien gefunden")
            except OSError as exc:
                report_error(f"Spielordner konnte nicht gelesen werden: {folder} ({exc})")

        with self._lock:
            games = deepcopy(self._games)
            by_path = {_path_key(g["path"]): g for g in games.values()}
            added = 0
            for index, (key, path) in enumerate(files.items(), start=1):
                check_cancel()
                candidates = self.extensions[path.suffix.lower()]
                game = by_path.get(key)
                if game is None:
                    identifier = hashlib.sha256(key.encode("utf-8")).hexdigest()
                    game = {"id": identifier, "path": str(path), "name": path.stem,
                            "console": candidates[0] if len(candidates) == 1 else None,
                            "favorite": False, "last_played": "", "assigned_manually": False,
                            "emulator_id": None}
                    games[identifier] = game
                    by_path[key] = game
                    added += 1
                elif not game.get("assigned_manually"):
                    game["console"] = candidates[0] if len(candidates) == 1 else None
                game.update({"path": str(path), "candidates": list(candidates), "missing": False})
                progress(int(index / max(1, len(files)) * 100), f"Bibliothek erfassen · {index} / {len(files)}")
            for game in games.values():
                check_cancel()
                try:
                    game["missing"] = not Path(game["path"]).is_file() or _is_link(game["path"])
                except OSError:
                    game["missing"] = True
            check_cancel()
            self._save(games)
            result = {"added": added, "total": len(games),
                      "ambiguous": sum(g["console"] is None and not g.get("missing") for g in games.values()),
                      "missing": sum(bool(g.get("missing")) for g in games.values()), "errors": errors}
        progress(100, f"Scan abgeschlossen · {added} neue Spiele")
        log(f"Bibliothek: {result['total']} Spiele, {result['ambiguous']} Konsolen noch zuordnen, {result['missing']} Dateien fehlen.")
        return result

    def set_console(self, game_id, console):
        if console not in self.supported_consoles:
            raise HubError("Bitte eine Konsole aus der Liste auswählen.")
        with self._lock:
            self.get_game(game_id)
            games = deepcopy(self._games)
            games[game_id].update({"console": console, "assigned_manually": True, "emulator_id": None})
            self._save(games)
            return deepcopy(games[game_id])

    def toggle_favorite(self, game_id):
        with self._lock:
            self.get_game(game_id)
            games = deepcopy(self._games)
            favorite = games[game_id]["favorite"] = not games[game_id]["favorite"]
            self._save(games)
            return favorite

    def touch_game(self, game_id, emulator_id=None):
        with self._lock:
            self.get_game(game_id)
            games = deepcopy(self._games)
            games[game_id]["last_played"] = datetime.now(timezone.utc).isoformat()
            if emulator_id is not None:
                games[game_id]["emulator_id"] = emulator_id
            self._save(games)

    def launch_game(self, game_id, emulator_id=None):
        self.last_warning = ""
        game = self.get_game(game_id)
        if game["console"] is None:
            raise HubError("Diese Dateiendung ist mehrdeutig. Bitte zuerst die Konsole für das Spiel zuordnen.")
        if self.launcher is None:
            raise HubError("Der Spielstart ist noch nicht eingerichtet. Bitte den Emulator direkt starten.")
        game["emulator_id"] = emulator_id or game.get("emulator_id")
        result = self.launcher(game, game["emulator_id"])
        try:
            # Der Launcher kann hier die tatsächlich gewählte Emulator-ID setzen.
            self.touch_game(game_id, game.get("emulator_id"))
        except HubError as exc:
            self.last_warning = f"Das Spiel wurde gestartet, aber Zuletzt gespielt konnte nicht gespeichert werden: {exc}"
        return result
