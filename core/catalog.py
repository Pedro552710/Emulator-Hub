"""Load the editable emulator catalog without any spreadsheet dependency."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import string
from urllib.parse import unquote, urlsplit


LEGAL_NOTICE = "BIOS/Firmware und Spiele nur aus der eigenen Hardware oder direkt vom Rechteinhaber beziehen."
INSTALL_METHODS = {"auto_github", "auto_direct", "winget", "manuell"}
REQUIRED_TEXT_FIELDS = (
    "id", "kategorie", "hersteller", "konsole", "emulator", "plattformen",
    "pc_anforderung", "official_url", "download_anleitung", "hinweis",
    "install_methode",
)


class CatalogError(ValueError):
    """A readable catalog error that the main window can present to the user."""


def catalog_path() -> Path:
    """Prefer an editable catalog next to the packaged executable."""
    if getattr(sys, "frozen", False):
        external = Path(sys.executable).resolve().parent / "catalog.json"
        if external.is_file():
            return external
        return Path(getattr(sys, "_MEIPASS", external.parent)) / "catalog.json"
    return Path(__file__).resolve().parent.parent / "catalog.json"


def _https_parts(value: str, label: str):
    try:
        parts = urlsplit(value)
        valid = (
            parts.scheme == "https" and bool(parts.hostname)
            and not parts.username and not parts.password
            and parts.port in (None, 443) and not parts.fragment
            and "\\" not in value and not any(ord(c) < 32 for c in value)
        )
    except ValueError:
        valid = False
    if not valid:
        raise CatalogError(f"{label}: Eine gültige HTTPS-Adresse ohne Zugangsdaten ist erforderlich.")
    return parts


def _url_allowed(value: str, prefixes: list[str]) -> bool:
    target = urlsplit(value)
    target_path = unquote(target.path).rstrip("/")
    # Encoded separators and parent traversal must not turn a prefix into another path.
    if "\\" in target_path or any(p in {".", ".."} for p in target_path.split("/")):
        return False
    for prefix in prefixes:
        allowed = urlsplit(prefix)
        base_path = unquote(allowed.path).rstrip("/")
        if target.hostname != allowed.hostname:
            continue
        if target_path == base_path or target_path.startswith(base_path + "/") or not base_path:
            return True
    return False


class Catalog:
    """Validated, data-driven catalog. New entries need no application changes."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path is not None else catalog_path()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise CatalogError(f"Der Katalog konnte nicht gelesen werden: {self.path}\n{exc}") from exc
        if not isinstance(raw, dict) or type(raw.get("schema_version")) is not int or raw["schema_version"] != 1:
            raise CatalogError("Der Katalog benötigt schema_version: 1 und ein JSON-Objekt als Wurzel.")

        self.categories = raw.get("categories")
        if (
            not isinstance(self.categories, list) or not self.categories
            or any(not isinstance(c, str) or not c.strip() for c in self.categories)
            or len(set(self.categories)) != len(self.categories)
        ):
            raise CatalogError("categories muss eine Liste mit eindeutigen, nicht leeren Kategorien sein.")
        self.official_sources = raw.get("official_sources")
        if not isinstance(self.official_sources, list) or not self.official_sources:
            raise CatalogError("official_sources benötigt mindestens eine offizielle HTTPS-Quelle.")
        for prefix in self.official_sources:
            if not isinstance(prefix, str):
                raise CatalogError("Jeder Eintrag in official_sources muss eine HTTPS-Adresse sein.")
            parts = _https_parts(prefix, "official_sources")
            if parts.query:
                raise CatalogError("Whitelist-Adressen in official_sources dürfen keine URL-Abfrage enthalten.")

        self.items = raw.get("emulators")
        if not isinstance(self.items, list) or not self.items:
            raise CatalogError("emulators muss eine nicht leere Liste enthalten.")
        self._by_id: dict[str, dict] = {}
        for index, item in enumerate(self.items, start=1):
            self._validate_item(item, index)
            if item["id"] in self._by_id:
                raise CatalogError(f"Die Emulator-ID '{item['id']}' kommt mehrfach vor.")
            self._by_id[item["id"]] = item

    def _validate_item(self, item: object, index: int) -> None:
        if not isinstance(item, dict):
            raise CatalogError(f"Emulator {index}: Ein JSON-Objekt ist erforderlich.")
        label = f"Emulator {index} ({item.get('id', '?')})"
        for field in REQUIRED_TEXT_FIELDS:
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise CatalogError(f"{label}: '{field}' muss ein nicht leerer Text sein.")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", item["id"]) or len(item["id"]) > 80:
            raise CatalogError(f"{label}: Die ID darf nur kleine Buchstaben, Zahlen und Bindestriche enthalten.")
        if item["kategorie"] not in self.categories:
            raise CatalogError(f"{label}: Die Kategorie fehlt in categories.")
        method = item["install_methode"]
        if method not in INSTALL_METHODS:
            raise CatalogError(f"{label}: Unbekannte install_methode '{method}'.")
        if LEGAL_NOTICE not in item["hinweis"]:
            raise CatalogError(f"{label}: Der erforderliche Rechtshinweis fehlt in hinweis.")
        for field in ("download_muster", "exe"):
            if not isinstance(item.get(field), str):
                raise CatalogError(f"{label}: '{field}' muss ein Text sein (bei manuell auch leer).")
        steps = item.get("manuelle_schritte")
        if not isinstance(steps, list) or not steps or any(not isinstance(s, str) or not s.strip() for s in steps):
            raise CatalogError(f"{label}: manuelle_schritte benötigt eine Liste mit nicht leeren Schritten.")
        for field in ("download_muster", "checksum_muster"):
            if field not in item:
                continue
            if not isinstance(item[field], str):
                raise CatalogError(f"{label}: '{field}' muss ein regulärer Ausdruck als Text sein.")
            try:
                re.compile(item[field], re.IGNORECASE)
            except re.error as exc:
                raise CatalogError(f"{label}: Ungültiges Muster in '{field}': {exc}") from exc
        filenames = [item["exe"]] + item.get("alternative_exes", []) if isinstance(item.get("alternative_exes", []), list) else None
        if filenames is None or any(not isinstance(n, str) for n in filenames):
            raise CatalogError(f"{label}: alternative_exes muss eine Liste mit Dateinamen sein.")
        for name in filenames:
            if name and (not name.lower().endswith(".exe") or any(c in name for c in "/\\:") or name in {".", ".."}):
                raise CatalogError(f"{label}: Startdateien müssen reine .exe-Dateinamen ohne Verzeichnisse sein.")
        for field in ("official_url", "direct_url", "checksum_url", "winget_manifest_url"):
            if field not in item:
                continue
            if not isinstance(item[field], str):
                raise CatalogError(f"{label}: '{field}' muss eine HTTPS-Adresse sein.")
            _https_parts(item[field], f"{label}, {field}")
            if not _url_allowed(item[field], self.official_sources):
                raise CatalogError(f"{label}: '{field}' liegt nicht in official_sources.")
        if "sha256" in item and (not isinstance(item["sha256"], str) or not re.fullmatch(r"[A-Fa-f0-9]{64}", item["sha256"])):
            raise CatalogError(f"{label}: sha256 muss genau 64 hexadezimale Zeichen enthalten.")
        if method == "auto_github":
            repo = item.get("github_repo")
            if not isinstance(repo, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
                raise CatalogError(f"{label}: auto_github benötigt github_repo im Format Besitzer/Repository.")
            if not _url_allowed(f"https://github.com/{repo}", self.official_sources):
                raise CatalogError(f"{label}: github_repo liegt nicht in official_sources.")
            if not item["download_muster"] or not item["exe"]:
                raise CatalogError(f"{label}: auto_github benötigt download_muster und exe.")
        elif method == "auto_direct" and (not item.get("direct_url") or not item["exe"]):
            raise CatalogError(f"{label}: auto_direct benötigt direct_url und exe.")
        elif method == "winget" and (not isinstance(item.get("winget_id"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]+", item["winget_id"])):
            raise CatalogError(f"{label}: winget benötigt eine gültige winget_id.")
        if item.get("archive_type", "zip") not in {"zip", "7z", "tar", "installer"}:
            raise CatalogError(f"{label}: Nicht unterstützter archive_type.")
        self._validate_profiles(item, label)
        if item.get("controller_config", "manuell") not in {"auto", "manuell"}:
            raise CatalogError(f"{label}: controller_config muss 'auto' oder 'manuell' sein.")
        for field in ("controller_manual", "controller_note"):
            if field in item and (not isinstance(item[field], str) or not item[field].strip()):
                raise CatalogError(f"{label}: '{field}' muss ein nicht leerer Text sein.")
        if item.get("controller_config") == "auto" and item.get("controller_adapter") != "dolphin_gc_xinput":
            raise CatalogError(f"{label}: Für automatische Controller-Konfigurationen ist ein unterstützter Adapter erforderlich.")

    @staticmethod
    def _validate_profiles(item: dict, label: str) -> None:
        """Optional library/profile metadata; existing catalog entries stay valid."""
        from .profiles import PROFILE_ROOTS, relative_parts
        from .errors import HubError

        def launch_arguments(value):
            if not isinstance(value, list) or not value or any(not isinstance(arg, str) for arg in value):
                raise CatalogError(f"{label}: Startparameter müssen eine nicht leere Textliste sein.")
            try:
                for argument in value:
                    if any(ord(char) < 32 for char in argument):
                        raise ValueError()
                    for _, field, format_spec, conversion in string.Formatter().parse(argument):
                        if field is not None and (field not in {"game", "game_dir", "game_stem", "exe_dir"} or format_spec or conversion):
                            raise ValueError()
            except ValueError:
                raise CatalogError(f"{label}: Erlaubte Startplatzhalter: {{game}}, {{game_dir}}, {{game_stem}}, {{exe_dir}}.") from None

        if "launch_args" in item:
            launch_arguments(item["launch_args"])
        if "launch_extensions" in item and (
            not isinstance(item["launch_extensions"], list) or not item["launch_extensions"]
            or any(not isinstance(suffix, str) or not re.fullmatch(r"\.[a-z0-9]+", suffix) for suffix in item["launch_extensions"])
        ):
            raise CatalogError(f"{label}: launch_extensions benötigt Dateiendungen wie '.iso'.")
        if "launch_profiles" in item:
            profiles = item["launch_profiles"]
            if not isinstance(profiles, dict) or not profiles:
                raise CatalogError(f"{label}: launch_profiles benötigt Startdateinamen mit Parameterlisten.")
            seen = set()
            for executable, arguments in profiles.items():
                if (not isinstance(executable, str) or not executable.lower().endswith(".exe")
                        or any(char in executable for char in "/\\:") or executable.casefold() in seen):
                    raise CatalogError(f"{label}: launch_profiles benötigt eindeutige, reine .exe-Dateinamen.")
                seen.add(executable.casefold())
                if arguments is not None:
                    launch_arguments(arguments)
        for field in ("launch_note", "bios_note", "backup_note"):
            if field in item and not isinstance(item[field], str):
                raise CatalogError(f"{label}: '{field}' muss ein Text sein.")
        for field in ("bios", "backup_paths"):
            if field not in item:
                continue
            specs = item[field]
            if not isinstance(specs, list):
                raise CatalogError(f"{label}: '{field}' muss eine Liste sein.")
            for spec in specs:
                if (not isinstance(spec, dict) or not isinstance(spec.get("label"), str) or not spec["label"].strip()
                        or spec.get("root") not in PROFILE_ROOTS):
                    raise CatalogError(f"{label}: '{field}' benötigt Bezeichnung und gültigen Basisordner.")
                try:
                    relative_parts(spec.get("directory"), allow_empty=field == "bios")
                except HubError as exc:
                    raise CatalogError(f"{label}: {exc}") from None
                if "portable" in spec:
                    portable = spec["portable"]
                    if not isinstance(portable, dict) or ("marker" in portable) == ("markers" in portable):
                        raise CatalogError(f"{label}: portable benötigt genau marker oder markers.")
                    markers = portable.get("markers", [portable.get("marker")])
                    if not isinstance(markers, list) or not markers:
                        raise CatalogError(f"{label}: Portable Markierungen benötigen eine nicht leere Liste.")
                    try:
                        for marker in markers:
                            relative_parts(marker)
                        relative_parts(portable.get("directory"), allow_empty=field == "bios")
                    except HubError as exc:
                        raise CatalogError(f"{label}: {exc}") from None
                    if portable.get("marker_type", "file") not in {"file", "directory"}:
                        raise CatalogError(f"{label}: marker_type muss file oder directory sein.")
                    if "path_from_marker" in portable and type(portable["path_from_marker"]) is not bool:
                        raise CatalogError(f"{label}: path_from_marker muss true oder false sein.")
                    if portable.get("path_from_marker") and (
                        "portable.txt" not in markers or portable.get("marker_type", "file") != "file"
                    ):
                        raise CatalogError(f"{label}: path_from_marker ist nur für eine portable.txt-Datei vorgesehen.")
                if "note" in spec and not isinstance(spec["note"], str):
                    raise CatalogError(f"{label}: Der Profilhinweis muss ein Text sein.")
                if field == "bios":
                    names = spec.get("filenames")
                    if (not isinstance(names, list) or not names or any(not isinstance(name, str) or not name
                            or any(char in name for char in "/\\:") for name in names)):
                        raise CatalogError(f"{label}: BIOS-Dateien benötigen reine Dateinamen.")
                    for name in names:
                        try:
                            relative_parts(name)
                        except HubError as exc:
                            raise CatalogError(f"{label}: {exc}") from None
                    for boolean in ("required", "any_of"):
                        if boolean in spec and type(spec[boolean]) is not bool:
                            raise CatalogError(f"{label}: '{boolean}' muss true oder false sein.")
                elif spec.get("type", "directory") not in {"file", "directory"}:
                    raise CatalogError(f"{label}: Sicherungspfade benötigen type: file oder directory.")

    def by_id(self, emulator_id: str) -> dict:
        try:
            return self._by_id[emulator_id]
        except KeyError as exc:
            raise CatalogError(f"Der Emulator '{emulator_id}' steht nicht im Katalog.") from exc
