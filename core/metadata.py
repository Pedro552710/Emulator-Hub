"""Optionale Cover und Spielinfos: eigene Zugangsdaten, lokale Caches, keine Spiele."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
import hashlib
import html
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
import time
from urllib.parse import urlparse
import warnings

from PIL import Image, UnidentifiedImageError
import requests

from .errors import Cancelled, HubError
from .state import read_json, write_json


PROVIDERS = {"igdb": "IGDB", "screenscraper": "ScreenScraper"}
CREDENTIAL_FIELDS = {
    "igdb": ("client_id", "client_secret"),
    "screenscraper": ("username", "password", "developer_id", "developer_password"),
}
MAX_JSON = 4 * 1024 * 1024
MAX_COVER = 12 * 1024 * 1024
MAX_PIXELS = 16_000_000
API_URL = "https://api.screenscraper.fr/api2/"
SS_ENDPOINTS = {"ssuserInfos.php", "systemesListe.php", "jeuRecherche.php", "jeuInfos.php", "mediaJeu.php"}

# IDs werden aus den aktuellen Plattformlisten der Dienste ermittelt.
CONSOLE_NAMES = {
    "NES": ("Nintendo Entertainment System", "NES", "Nintendo Entertainment System (NES)", "Famicom"),
    "SNES": ("Super Nintendo Entertainment System", "SNES", "Super Nintendo Entertainment System (SNES)"),
    "Game Boy / GBC": ("Game Boy", "Game Boy Color", "Nintendo Game Boy", "Nintendo Game Boy Color"),
    "Game Boy Advance": ("Game Boy Advance", "Nintendo Game Boy Advance"),
    "Nintendo 64": ("Nintendo 64", "N64"),
    "Nintendo DS": ("Nintendo DS", "NDS"),
    "Nintendo 3DS": ("Nintendo 3DS", "3DS"),
    "GameCube / Wii": ("Nintendo GameCube", "GameCube", "Nintendo Wii", "Wii"),
    "Wii U": ("Wii U", "Nintendo Wii U"),
    "PlayStation 1": ("PlayStation", "Sony PlayStation", "PlayStation 1"),
    "PlayStation 2": ("PlayStation 2", "Sony PlayStation 2"),
    "PlayStation 3": ("PlayStation 3", "Sony PlayStation 3"),
    "PSP": ("PlayStation Portable", "Sony PlayStation Portable", "PSP"),
    "PS Vita": ("PlayStation Vita", "Sony PlayStation Vita", "PS Vita"),
    "Master System / Mega Drive": ("Sega Master System", "Sega Mega Drive", "Sega Mega Drive/Genesis", "Megadrive", "Genesis", "Mega Drive", "Master System"),
    "Saturn": ("Sega Saturn", "Saturn"),
    "Dreamcast": ("Dreamcast", "Sega Dreamcast"),
    "Xbox (Original)": ("Xbox", "Microsoft Xbox"),
    "Xbox 360": ("Xbox 360", "Microsoft Xbox 360"),
    "Atari 2600": ("Atari 2600", "Atari VCS"),
    "PC Engine / TurboGrafx": ("PC Engine", "PC Engine / TurboGrafx-16", "TurboGrafx-16", "PC Engine SuperGrafx", "PC Engine CD"),
    "Neo Geo / Arcade": ("Arcade", "Neo Geo AES", "Neo Geo MVS", "Neo-Geo", "Neo Geo", "MAME"),
}
CONSOLE_NAMES.update({
    "Game Boy": ("Game Boy", "Nintendo Game Boy"),
    "Game Boy Color": ("Game Boy Color", "Nintendo Game Boy Color"),
    "GameCube": ("GameCube", "Nintendo GameCube"),
    "Wii": ("Wii", "Nintendo Wii"),
    "Mega Drive": ("Sega Mega Drive/Genesis", "Sega Mega Drive", "Mega Drive", "Megadrive", "Genesis"),
    "Master System": ("Sega Master System", "Master System"),
    "PlayStation": CONSOLE_NAMES["PlayStation 1"],
    "PC Engine": CONSOLE_NAMES["PC Engine / TurboGrafx"],
    "Arcade": ("Arcade", "MAME"),
    "Neo Geo": ("Neo Geo AES", "Neo Geo MVS", "Neo-Geo", "Neo Geo"),
})


def clean_game_name(value):
    """Regionen, Prüfsummen und Dump-Tags entfernen; keine Spieldatei lesen."""
    name = Path(str(value)).stem if Path(str(value)).suffix.lower() in {
        ".nes", ".sfc", ".smc", ".gb", ".gbc", ".gba", ".nds", ".3ds", ".iso",
        ".zip", ".bin", ".cue", ".chd", ".md", ".gen", ".gcm", ".rvz", ".wbfs",
        ".cso", ".cdi", ".gdi", ".z64", ".n64", ".v64", ".a26", ".pce", ".sms",
    } else str(value)
    name = re.sub(r"\[[^]]*\]|\([^)]*\)", " ", name)
    name = re.sub(r"\b(?:disc|disk|cd)\s*\d+\b", " ", name, flags=re.I)
    name = re.sub(r"^[0-9]{3,5}\s*[-_]+\s*", "", name)
    return re.sub(r"\s+", " ", name.replace("_", " ")).strip()[:180]


def _normal(value):
    return re.sub(r"[^\w]+", "", str(value).casefold())


def _text(value, limit=12000):
    if not isinstance(value, (str, int, float)):
        return ""
    return html.unescape(re.sub(r"<[^>]*>", "", str(value))).strip()[:limit]


def _identifier(value):
    text = str(value)
    if not re.fullmatch(r"[1-9][0-9]{0,11}", text):
        raise HubError("Der Dienst hat eine ungültige Spiel- oder Plattform-ID geliefert.")
    return text


def _is_link(path):
    path = Path(path)
    return path.is_symlink() or (path.exists() and bool(
        getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT))


def _list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return list(value.values())
    return []


def _ss_response(value):
    if not isinstance(value, dict) or not isinstance(value.get("response"), dict):
        raise HubError("ScreenScraper hat keine gültigen Informationsdaten geliefert.")
    return value["response"]


def _localized(value, languages=("de", "en", "fr")):
    """Die API liefert je nach Feld Listen oder nach Sprache benannte Objekte."""
    if isinstance(value, str):
        return _text(value)
    if isinstance(value, dict):
        for language in languages:
            for key in (language, f"nom_{language}", f"synopsis_{language}", f"date_{language}"):
                if key in value:
                    return _text(value[key])
        if "text" in value:
            return _text(value["text"])
    entries = _list(value)
    for language in languages:
        for item in entries:
            if isinstance(item, dict) and (item.get("langue") or item.get("region")) == language:
                return _text(item.get("text", ""))
    for item in entries:
        if isinstance(item, dict) and item.get("text"):
            return _text(item["text"])
        if isinstance(item, str):
            return _text(item)
    return ""


def _valid_candidate(item):
    """Beschädigte optionale Cacheeinträge dürfen keinen GUI-Start verhindern."""
    if not isinstance(item, dict) or item.get("provider") not in PROVIDERS:
        return False
    for key in ("id", "title", "description", "cover_path", "source", "source_url"):
        if not isinstance(item.get(key), str):
            return False
    if not item["title"] or not re.fullmatch(r"[1-9][0-9]{0,11}", item["id"]):
        return False
    if item.get("year") is not None and (type(item["year"]) is not int or not 1800 <= item["year"] <= 2200):
        return False
    for key in ("genres", "platforms"):
        if not isinstance(item.get(key), list) or any(not isinstance(value, str) for value in item[key]):
            return False
    if item["cover_path"] and not re.fullmatch(r"covers/[0-9a-f]{64}\.png", item["cover_path"]):
        return False
    for key in ("cover_url", "cover_media", "platform_id", "cover_warning", "cached_at"):
        if key in item and not isinstance(item[key], str):
            return False
    if "requires_confirmation" in item and type(item["requires_confirmation"]) is not bool:
        return False
    score = item.get("confidence", 0)
    if not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
        return False
    return True


class MetadataService:
    def __init__(self, data_dir, settings, *, session=None, credential_backend=None):
        self.data_dir = Path(data_dir).resolve()
        self.settings = settings
        self.cache_dir = self.data_dir / "cache"
        self.covers_dir = self.cache_dir / "covers"
        self.path = self.cache_dir / "metadata.json"
        self._lock = threading.RLock()
        self._request_lock = threading.RLock()
        self._session = session or requests.Session()
        self._credential_backend = credential_backend
        self._token = None
        self._token_expiry = 0
        self._last_request = {}
        self._intervals = {"igdb": .30, "screenscraper": 1.0}
        self._platforms = {}
        self._ss_user = None
        self._ss_calls = 0
        self._ss_date = ""
        self.last_warning = ""
        self._cache_readonly = False
        raw = {"schema_version": 1, "games": {}, "searches": {}}
        try:
            self._assert_cache()
            loaded = read_json(self.path, raw, "Der Cover-Cache")
            if (not isinstance(loaded, dict) or loaded.get("schema_version") != 1
                    or not isinstance(loaded.get("games"), dict) or not isinstance(loaded.get("searches", {}), dict)):
                raise HubError("Der Cover-Cache ist beschädigt. Bitte cache/metadata.json sichern oder den Cache leeren.")
            if (any(not isinstance(key, str) or not _valid_candidate(item) for key, item in loaded["games"].items())
                    or any(not isinstance(items, list) or any(not _valid_candidate(item) for item in items)
                           for items in loaded.get("searches", {}).values())):
                raise HubError("Der Cover-Cache enthält ungültige Spieleinfos. Bitte cache/metadata.json sichern oder den Cache leeren.")
            raw = loaded
        except HubError as exc:
            self.last_warning = str(exc)
            self._cache_readonly = True
        self._cache = {"schema_version": 1, "games": raw["games"], "searches": raw.get("searches", {})}

    def _writable_cache(self):
        if self._cache_readonly:
            raise HubError("Der Cover-Cache konnte nicht gelesen werden. Bitte die bisherige Datei sichern und unter Cover & Infos den Cache leeren, bevor neue Infos geladen werden.")

    def _assert_cache(self):
        try:
            for folder in (self.cache_dir, self.covers_dir):
                if _is_link(folder) or folder.exists() and not folder.resolve().is_relative_to(self.data_dir):
                    raise HubError("Der Cover-Cache darf keine Verknüpfung sein.")
            if _is_link(self.path):
                raise HubError("Die Cache-Datei darf keine Verknüpfung sein.")
        except OSError:
            raise HubError("Der Cover-Cache ist nicht zugänglich. Bitte Ordner und Schreibrechte prüfen.") from None

    @staticmethod
    def _provider(provider):
        if provider not in PROVIDERS:
            raise HubError("Bitte IGDB oder ScreenScraper als Datenquelle auswählen.")
        return provider

    def _vault(self):
        if self._credential_backend is not None:
            return self._credential_backend
        if os.name != "nt":
            raise HubError("Die Zugangsdaten können nur im Windows-Anmeldeinformationsmanager gespeichert werden.")
        try:
            from keyring.backends.Windows import WinVaultKeyring
            self._credential_backend = WinVaultKeyring()
            return self._credential_backend
        except Exception:
            raise HubError("Der Windows-Anmeldeinformationsmanager ist nicht verfügbar. Bitte keyring installieren und Windows-Anmeldung prüfen.") from None

    def load_credentials(self, provider):
        self._provider(provider)
        try:
            raw = self._vault().get_password("EmulatorHub.CoverInfos", provider)
            values = json.loads(raw) if raw else {}
            if not isinstance(values, dict):
                raise ValueError()
            return {key: values.get(key, "") if isinstance(values.get(key, ""), str) else ""
                    for key in CREDENTIAL_FIELDS[provider]}
        except HubError:
            raise
        except Exception:
            raise HubError("Die Zugangsdaten konnten nicht aus dem Windows-Anmeldeinformationsmanager gelesen werden.") from None

    def save_credentials(self, provider, values):
        self._provider(provider)
        if not isinstance(values, dict) or any(not isinstance(values.get(key, ""), str) for key in CREDENTIAL_FIELDS[provider]):
            raise HubError("Die Zugangsdaten enthalten ungültige Werte.")
        selected = {key: values.get(key, "") for key in CREDENTIAL_FIELDS[provider]}
        for key in ("client_id", "username", "developer_id"):
            if key in selected:
                selected[key] = selected[key].strip()
        try:
            vault = self._vault()
            if any(selected.values()):
                vault.set_password("EmulatorHub.CoverInfos", provider, json.dumps(selected, ensure_ascii=False))
            elif vault.get_password("EmulatorHub.CoverInfos", provider) is not None:
                vault.delete_password("EmulatorHub.CoverInfos", provider)
        except HubError:
            raise
        except Exception:
            raise HubError("Die Zugangsdaten konnten nicht sicher gespeichert werden. Es wurde keine unverschlüsselte Ersatzdatei angelegt.") from None
        with self._request_lock:
            self._token = None
            self._token_expiry = 0
            self._ss_user = None
            self._platforms.pop(provider, None)

    def _credentials(self, provider):
        values = self.load_credentials(provider)
        if any(not values[key] for key in CREDENTIAL_FIELDS[provider]):
            if provider == "screenscraper":
                raise HubError("ScreenScraper benötigt Benutzername und Passwort sowie eigene freigeschaltete Entwickler-ID und Entwicklerpasswort. Bitte unter Cover & Infos eintragen.")
            raise HubError("Bitte Twitch Client-ID und Client-Secret unter Cover & Infos eintragen.")
        return values

    @staticmethod
    def _cancel(cancel_event):
        if cancel_event.is_set():
            raise Cancelled()

    def _wait(self, seconds, cancel_event):
        if cancel_event.wait(max(0, seconds)):
            raise Cancelled()

    @staticmethod
    def _url(url, *, image=False):
        try:
            parsed = urlparse(url)
            port = parsed.port
        except (ValueError, TypeError):
            raise HubError("Die Datenquelle hat eine ungültige Adresse geliefert.") from None
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or port not in (None, 443) or parsed.fragment):
            raise HubError("Die Datenquelle hat eine unsichere Adresse geliefert.")
        valid = (parsed.hostname == "api.igdb.com" and parsed.path in ("/v4/games", "/v4/platforms"))
        valid |= parsed.hostname == "id.twitch.tv" and parsed.path == "/oauth2/token"
        valid |= parsed.hostname == "api.screenscraper.fr" and parsed.path.startswith("/api2/") and parsed.path.rsplit("/", 1)[-1] in SS_ENDPOINTS
        if image:
            valid = parsed.hostname == "images.igdb.com" and bool(re.fullmatch(
                r"/igdb/image/upload/(?:t_[A-Za-z0-9_]+/)?[A-Za-z0-9_\-]+\.(?:jpg|png|webp)", parsed.path)) and not parsed.query
            valid |= parsed.hostname in ("api.screenscraper.fr", "www.screenscraper.fr", "screenscraper.fr") and (
                parsed.path == "/api2/mediaJeu.php" or parsed.path == "/image.php" or parsed.path.startswith("/medias/"))
        if not valid:
            raise HubError("Die Adresse gehört nicht zu einer erlaubten Cover- oder Informationsquelle.")
        return url

    def _quota(self):
        if self._ss_date != datetime.now(timezone.utc).date().isoformat():
            self._ss_user = None
            self._ss_calls = 0
        if self._ss_user:
            maximum = int(self._ss_user.get("maxrequestsperday", 0) or 0)
            used = int(self._ss_user.get("requeststoday", 0) or 0) + self._ss_calls
            if maximum and used >= maximum:
                raise HubError("Das tägliche ScreenScraper-Kontingent ist aufgebraucht. Bitte am nächsten Tag erneut versuchen.")

    def _request(self, provider, method, url, cancel_event, log, *, image=False, **kwargs):
        """Nur freigegebene HTTPS-Ziele; kleine Antworten, kurze Timeouts und Abbruch."""
        self._url(url, image=image)
        maximum = MAX_COVER if image else MAX_JSON
        with self._request_lock:
            for attempt in range(4):
                self._cancel(cancel_event)
                if provider == "screenscraper":
                    self._quota()
                delay = self._intervals[provider] - (time.monotonic() - self._last_request.get(provider, 0))
                self._wait(delay, cancel_event)
                self._last_request[provider] = time.monotonic()
                response = None
                try:
                    response = self._session.request(method, url, timeout=(4, 6), allow_redirects=False, stream=True, **kwargs)
                    if provider == "screenscraper":
                        self._ss_calls += 1
                    status = response.status_code
                    if 300 <= status < 400:
                        # Authentifizierte Requests werden nie auf ein anderes Ziel umgeleitet.
                        raise HubError("Der Dienst hat die Abfrage umgeleitet. Aus Sicherheitsgründen wurde sie nicht weitergesendet.")
                    if status in (429, 500, 502, 503, 504) or provider == "screenscraper" and status == 429:
                        if attempt == 3:
                            raise HubError("Die Datenquelle ist zurzeit ausgelastet oder nicht erreichbar. Bitte später erneut versuchen.")
                        raw_delay = response.headers.get("Retry-After", "")
                        try:
                            wait = float(raw_delay)
                        except (TypeError, ValueError):
                            try:
                                retry_at = parsedate_to_datetime(raw_delay)
                                if retry_at.tzinfo is None:
                                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                                wait = (retry_at - datetime.now(timezone.utc)).total_seconds()
                            except (ValueError, TypeError, OverflowError):
                                wait = 2 ** (attempt + 1)
                        if not math.isfinite(wait) or wait > 3600:
                            raise HubError("Die Datenquelle verlangt eine längere Pause. Bitte später erneut versuchen; es wurde keine vorzeitige Wiederholung gesendet.")
                        wait = max(1, wait)
                        response.close()
                        response = None
                        log(f"{PROVIDERS[provider]}: Wartezeit {wait:g} Sekunden, neuer Versuch {attempt + 2}/4.")
                        self._wait(wait, cancel_event)
                        continue
                    if status in (401, 403):
                        raise HubError(f"{PROVIDERS[provider]} hat die Anmeldung abgelehnt. Bitte Zugangsdaten und Kontofreigabe prüfen.")
                    if status in (430, 431):
                        raise HubError("Das tägliche ScreenScraper-Kontingent ist aufgebraucht. Bitte am nächsten Tag erneut versuchen.")
                    if provider == "screenscraper" and status == 404:
                        return None
                    if status >= 400:
                        raise HubError(f"{PROVIDERS[provider]} konnte die Abfrage nicht ausführen (HTTP {status}). Bitte später erneut versuchen.")
                    length = response.headers.get("Content-Length", "")
                    if length.isdigit() and int(length) > maximum:
                        raise HubError("Die Antwort der Datenquelle ist zu groß.")
                    body = bytearray()
                    for chunk in response.iter_content(64 * 1024):
                        self._cancel(cancel_event)
                        body.extend(chunk)
                        if len(body) > maximum:
                            raise HubError("Die Antwort der Datenquelle ist zu groß.")
                    self._cancel(cancel_event)
                    if image:
                        return bytes(body)
                    try:
                        result = json.loads(body)
                    except (ValueError, UnicodeError):
                        raise HubError("Der Dienst hat keine gültigen Informationsdaten geliefert.") from None
                    if provider == "screenscraper":
                        self._update_ss_quota(result)
                    return result
                except requests.RequestException:
                    if attempt == 3:
                        raise HubError("Die Datenquelle ist nicht erreichbar. Bitte Internetverbindung prüfen; bereits gespeicherte Infos bleiben offline verfügbar.") from None
                    log(f"{PROVIDERS[provider]}: Verbindung unterbrochen, neuer Versuch {attempt + 2}/4.")
                    self._wait(2 ** attempt, cancel_event)
                finally:
                    if response is not None:
                        response.close()
        raise HubError("Die Datenquelle konnte nicht erreicht werden.")

    def _update_ss_quota(self, response):
        if not isinstance(response, dict):
            return
        user = response.get("response", {}).get("ssuser") if isinstance(response.get("response"), dict) else None
        if isinstance(user, dict):
            safe = {}
            for key in ("maxrequestsperdmin", "maxrequestsperday", "requeststoday"):
                try:
                    safe[key] = max(0, int(user.get(key, 0)))
                except (TypeError, ValueError):
                    safe[key] = 0
            self._ss_user = safe
            self._ss_calls = 0
            self._ss_date = datetime.now(timezone.utc).date().isoformat()
            per_minute = safe["maxrequestsperdmin"]
            if per_minute:
                self._intervals["screenscraper"] = max(1.0, 60 / per_minute + .05)

    def _ss_params(self):
        values = self._credentials("screenscraper")
        return {"devid": values["developer_id"], "devpassword": values["developer_password"],
                "ssid": values["username"], "sspassword": values["password"],
                "softname": "EmulatorHub", "output": "json"}

    def _igdb(self, endpoint, query, cancel_event, log):
        with self._request_lock:
            values = self._credentials("igdb")
            for authentication_attempt in range(2):
                if not self._token or time.monotonic() >= self._token_expiry:
                    result = self._request("igdb", "POST", "https://id.twitch.tv/oauth2/token", cancel_event, log,
                                           data={**values, "grant_type": "client_credentials"})
                    if not isinstance(result, dict) or not isinstance(result.get("access_token"), str):
                        raise HubError("Twitch hat keinen gültigen Zugriffsschlüssel geliefert.")
                    try:
                        lifetime = int(result.get("expires_in", 0))
                    except (ValueError, TypeError):
                        lifetime = 0
                    self._token = result["access_token"]
                    self._token_expiry = time.monotonic() + max(0, lifetime - 60)
                try:
                    result = self._request("igdb", "POST", f"https://api.igdb.com/v4/{endpoint}", cancel_event, log,
                                           headers={"Client-ID": values["client_id"], "Authorization": f"Bearer {self._token}",
                                                    "Content-Type": "text/plain"}, data=query.encode("utf-8"))
                    if not isinstance(result, list):
                        raise HubError("IGDB hat keine gültige Trefferliste geliefert.")
                    return result
                except HubError as exc:
                    if "Anmeldung abgelehnt" not in str(exc) or authentication_attempt:
                        raise
                    self._token = None
            raise HubError("IGDB konnte nicht angemeldet werden.")

    def test_connection(self, provider, progress, log, cancel_event):
        self._provider(provider)
        progress(-1, f"Verbindung zu {PROVIDERS[provider]} testen …")
        if provider == "igdb":
            self._igdb("games", "fields id; limit 1;", cancel_event, log)
        else:
            result = self._request(provider, "GET", API_URL + "ssuserInfos.php", cancel_event, log, params=self._ss_params())
            user = result.get("response", {}).get("ssuser") if isinstance(result, dict) and isinstance(result.get("response"), dict) else None
            if not isinstance(user, dict) or not user.get("id"):
                raise HubError("ScreenScraper konnte das Benutzerkonto nicht bestätigen. Bitte alle vier Zugangsdaten prüfen.")
        progress(100, "Verbindung erfolgreich")
        return {"provider": provider, "message": f"Die Verbindung zu {PROVIDERS[provider]} funktioniert."}

    def _console_ids(self, provider, console, cancel_event, log):
        if provider == "screenscraper":
            self._quota()
            if self._ss_user is None:
                self.test_connection(provider, lambda *_: None, log, cancel_event)
        if provider not in self._platforms:
            if provider == "igdb":
                rows = self._igdb("platforms", "fields id,name,abbreviation,alternative_name; limit 500;", cancel_event, log)
            else:
                if self._ss_user is None:
                    self.test_connection(provider, lambda *_: None, log, cancel_event)
                result = self._request(provider, "GET", API_URL + "systemesListe.php", cancel_event, log, params=self._ss_params())
                rows = _ss_response(result).get("systemes", [])
            found = []
            for row in _list(rows):
                if not isinstance(row, dict) or not str(row.get("id", "")).isdigit():
                    continue
                if provider == "igdb":
                    names = [row.get("name"), row.get("abbreviation"), row.get("alternative_name")]
                else:
                    names = [row.get("nom"), row.get("name")]
                    for value in _list(row.get("noms", {})):
                        names.append(value.get("text") if isinstance(value, dict) else value)
                found.append((str(row["id"]), [_text(n) for n in names if n]))
            if not found:
                raise HubError("Die Plattformliste der Datenquelle konnte nicht gelesen werden.")
            self._platforms[provider] = found
        aliases = {_normal(value) for value in CONSOLE_NAMES.get(console, (console,))}
        return [identifier for identifier, names in self._platforms[provider]
                if any(_normal(name) in aliases for name in names)]

    @staticmethod
    def _score(candidate, title, platform_match):
        score = SequenceMatcher(None, _normal(title), _normal(candidate["title"])).ratio()
        candidate.update({"confidence": round(score * (1 if platform_match else .5), 3),
                          "requires_confirmation": not (score == 1 and platform_match)})
        return candidate

    def search(self, game, provider, progress, log, cancel_event):
        self._provider(provider)
        self._cancel(cancel_event)
        if not isinstance(game, dict) or not game.get("console"):
            raise HubError("Bitte zuerst die Konsole für das Spiel in der Bibliothek zuordnen.")
        title = clean_game_name(game.get("name") or Path(game.get("path", "")).name)
        if not title:
            raise HubError("Aus dem Dateinamen konnte kein Spieltitel für die Suche ermittelt werden.")
        key = hashlib.sha256(json.dumps([provider, title.casefold(), game["console"]], ensure_ascii=False).encode()).hexdigest()
        with self._lock:
            cached = self._cache["searches"].get(key)
            if isinstance(cached, list):
                progress(100, "Treffer aus dem lokalen Cache geladen")
                return deepcopy(cached)
            self._writable_cache()
        progress(-1, f"{PROVIDERS[provider]}: {title} suchen …")
        ids = self._console_ids(provider, game["console"], cancel_event, log)
        if not ids:
            raise HubError("Die Konsole wurde in der Plattformliste der Datenquelle nicht eindeutig erkannt. Bitte die Konsolenzuordnung prüfen oder die andere Quelle verwenden.")
        candidates = []
        if provider == "igdb":
            escaped = title.replace("\\", "\\\\").replace('"', '\\"')
            escaped = re.sub(r"[\x00-\x1f]", " ", escaped)
            query = (f'search "{escaped}"; fields id,name,first_release_date,genres.name,summary,'
                     f'cover.image_id,url,platforms.id,platforms.name; where platforms = ({",".join(ids)}); limit 20;')
            rows = self._igdb("games", query, cancel_event, log)
            for row in _list(rows):
                if not isinstance(row, dict) or not row.get("name") or not str(row.get("id", "")).isdigit():
                    continue
                candidate = self._from_igdb(row)
                match = any(str(p.get("id")) in ids for p in _list(row.get("platforms")) if isinstance(p, dict))
                candidates.append(self._score(candidate, title, match))
        else:
            for index, platform in enumerate(ids):
                self._cancel(cancel_event)
                result = self._request(provider, "GET", API_URL + "jeuRecherche.php", cancel_event, log,
                                       params={**self._ss_params(), "systemeid": platform, "recherche": title})
                rows = _ss_response(result).get("jeux", []) if result is not None else []
                for row in _list(rows):
                    if isinstance(row, dict) and str(row.get("id", "")).isdigit():
                        candidate = self._from_ss(row)
                        if not candidate["title"]:
                            continue
                        # Eine Suchanfrage ist plattformgefiltert; die Antwort muss sie bestätigen.
                        match = candidate.get("platform_id") in ids
                        candidates.append(self._score(candidate, title, match))
                progress(int((index + 1) / len(ids) * 90), f"{PROVIDERS[provider]}: Suche {index + 1}/{len(ids)}")
        candidates = list({(c["id"], c.get("platform_id", "")): c for c in candidates}.values())
        candidates.sort(key=lambda c: (-c["confidence"], c["title"].casefold()))
        if len(candidates) != 1:
            for candidate in candidates:
                candidate["requires_confirmation"] = True
        with self._lock:
            self._assert_cache()
            updated = deepcopy(self._cache)
            updated["searches"][key] = candidates[:30]
            write_json(self.path, updated, "Der Cover-Cache")
            self._cache = updated
        progress(100, f"{len(candidates)} Treffer gefunden")
        return deepcopy(candidates[:30])

    def _from_igdb(self, row):
        identifier = _identifier(row["id"])
        year = None
        try:
            if row.get("first_release_date"):
                year = datetime.fromtimestamp(int(row["first_release_date"]), timezone.utc).year
        except (ValueError, OSError, OverflowError, TypeError):
            pass
        image_id = row.get("cover", {}).get("image_id", "") if isinstance(row.get("cover"), dict) else ""
        cover = f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg" if re.fullmatch(r"[A-Za-z0-9_\-]+", str(image_id)) else ""
        url = row.get("url", "")
        parsed = urlparse(url) if isinstance(url, str) else urlparse("")
        source_url = url if parsed.scheme == "https" and parsed.hostname == "www.igdb.com" and not parsed.username and not parsed.password else "https://www.igdb.com/"
        return {"id": identifier, "provider": "igdb", "title": _text(row.get("name"), 250), "year": year,
                "genres": [_text(g.get("name"), 100) for g in _list(row.get("genres")) if isinstance(g, dict) and g.get("name")],
                "description": _text(row.get("summary", "")), "cover_url": cover, "cover_path": "",
                "platforms": [_text(p.get("name"), 120) for p in _list(row.get("platforms")) if isinstance(p, dict) and p.get("name")],
                "source": "IGDB", "source_url": source_url}

    def _from_ss(self, row):
        identifier = _identifier(row["id"])
        platform = row.get("systeme", {}) if isinstance(row.get("systeme"), dict) else {}
        title = _localized(row.get("noms", {}), ("wor", "eu", "us", "de", "en", "ss")) or _text(row.get("nom", ""), 250)
        dates = _localized(row.get("dates", {}), ("eu", "de", "wor", "us", "jp"))
        match = re.search(r"\b(19[0-9]{2}|20[0-9]{2})\b", dates)
        genres = []
        for genre in _list(row.get("genres", [])):
            if isinstance(genre, dict):
                text = _localized(genre.get("noms", genre))
                if text:
                    genres.append(text)
        media = None
        raw_medias = row.get("medias", [])
        for item in _list(raw_medias):
            if isinstance(item, dict) and item.get("type") in ("box-2D", "box-3D"):
                if media is None or item["type"] == "box-2D" and item.get("region") in ("eu", "wor", "de"):
                    media = item
        # XML-ähnliche API-Objekte liefern Typ/Region im Schlüssel statt in einer Liste.
        if media is None and isinstance(raw_medias, dict):
            for key in raw_medias:
                match_media = re.fullmatch(r"media_box-(2D|3D)\(([a-z]+)\)", key)
                if match_media:
                    media = {"type": "box-" + match_media[1], "region": match_media[2]}
                    break
        media_name = ""
        if media and re.fullmatch(r"[a-z]{2,5}", str(media.get("region", "wor"))):
            media_name = f"{media['type']}({media.get('region', 'wor')})"
        return {"id": identifier, "provider": "screenscraper", "title": title[:250],
                "year": int(match[1]) if match else None, "genres": genres,
                "description": _localized(row.get("synopsis", {})), "cover_path": "", "cover_url": "",
                "cover_media": media_name, "platform_id": str(platform.get("id", "")),
                "platforms": [_text(platform.get("nom") or platform.get("text"), 120)] if platform.get("nom") or platform.get("text") else [],
                "source": "ScreenScraper", "source_url": f"https://www.screenscraper.fr/gameinfos.php?gameid={identifier}"}

    def _store_cover(self, candidate, cancel_event, log):
        provider = candidate["provider"]
        content_key = f"{provider}:{candidate['id']}:{candidate.get('platform_id', '')}:{candidate.get('cover_media', '')}:{candidate.get('cover_url', '')}"
        filename = hashlib.sha256(content_key.encode()).hexdigest() + ".png"
        target = self.covers_dir / filename
        self._assert_cache()
        if target.is_file() and not _is_link(target):
            return "covers/" + filename
        if provider == "igdb":
            if not candidate.get("cover_url"):
                return ""
            body = self._request(provider, "GET", candidate["cover_url"], cancel_event, log, image=True)
        else:
            if not candidate.get("cover_media"):
                return ""
            platform = _identifier(candidate.get("platform_id"))
            body = self._request(provider, "GET", API_URL + "mediaJeu.php", cancel_event, log, image=True,
                                 params={**self._ss_params(), "systemeid": platform, "jeuid": _identifier(candidate["id"]),
                                         "media": candidate["cover_media"], "outputformat": "png", "maxheight": 1000, "maxwidth": 1000})
        if not body:
            return ""
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(body)) as image:
                    if image.format not in ("PNG", "JPEG", "WEBP") or image.width * image.height > MAX_PIXELS:
                        raise ValueError()
                    image.verify()
                with Image.open(io.BytesIO(body)) as image:
                    image.load()
                    converted = image.convert("RGBA")
                    converted.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise HubError("Das Cover ist kein gültiges oder angemessen großes Bild. Es wurde nicht gespeichert.") from None
        self._cancel(cancel_event)
        temporary = None
        with self._lock:
            self._assert_cache()
            self.covers_dir.mkdir(parents=True, exist_ok=True)
            try:
                with tempfile.NamedTemporaryFile(dir=self.covers_dir, suffix=".tmp", delete=False) as handle:
                    temporary = Path(handle.name)
                    converted.save(handle, format="PNG")
                    handle.flush()
                    os.fsync(handle.fileno())
                self._cancel(cancel_event)
                os.replace(temporary, target)
            except OSError:
                raise HubError("Das Cover konnte nicht im lokalen Cache gespeichert werden. Bitte freien Speicher und Schreibrechte prüfen.") from None
            finally:
                if temporary and temporary.exists():
                    temporary.unlink(missing_ok=True)
        return "covers/" + filename

    def choose(self, game_id, candidate, progress, log, cancel_event):
        self._cancel(cancel_event)
        self._writable_cache()
        if not isinstance(game_id, str) or not game_id or not isinstance(candidate, dict):
            raise HubError("Bitte einen gültigen Bibliothekseintrag und einen gefundenen Treffer auswählen.")
        provider = self._provider(candidate.get("provider"))
        _identifier(candidate.get("id"))
        selected = deepcopy(candidate)
        if not _valid_candidate(selected):
            raise HubError("Die gefundenen Spielinfos enthalten ungültige Werte. Bitte die Suche erneut ausführen.")
        progress(-1, f"{PROVIDERS[provider]}: Infos und Cover speichern …")
        if provider == "screenscraper":
            # Details nur anhand der bestätigten Spiel-ID; keine Hashes oder Spielinhalte übertragen.
            result = self._request(provider, "GET", API_URL + "jeuInfos.php", cancel_event, log,
                                   params={**self._ss_params(), "gameid": selected["id"], "systemeid": _identifier(selected.get("platform_id"))})
            row = _ss_response(result).get("jeu") if result is not None else None
            if isinstance(row, dict):
                if str(row.get("id")) != selected["id"]:
                    raise HubError("ScreenScraper lieferte eine andere Spiel-ID. Die Zuordnung wurde nicht gespeichert.")
                selected = {**selected, **self._from_ss(row)}
        selected["cover_warning"] = ""
        try:
            selected["cover_path"] = self._store_cover(selected, cancel_event, log)
        except Cancelled:
            raise
        except HubError as exc:
            selected["cover_path"] = ""
            selected["cover_warning"] = str(exc)
            log(f"Cover konnte nicht geladen werden: {exc}")
        self._cancel(cancel_event)
        selected["cached_at"] = datetime.now(timezone.utc).isoformat()
        selected["requires_confirmation"] = False
        with self._lock:
            self._assert_cache()
            updated = deepcopy(self._cache)
            updated["games"][game_id] = selected
            write_json(self.path, updated, "Der Cover-Cache")
            self._cache = updated
        progress(100, "Cover und Infos gespeichert")
        return self.get(game_id)

    def get(self, game_id):
        with self._lock:
            item = deepcopy(self._cache["games"].get(game_id))
        if not isinstance(item, dict):
            return None
        relative = item.get("cover_path", "")
        item["cover_path"] = ""
        if isinstance(relative, str) and re.fullmatch(r"covers/[0-9a-f]{64}\.png", relative):
            path = self.cache_dir / relative
            self._assert_cache()
            if path.is_file() and not _is_link(path) and path.resolve().is_relative_to(self.covers_dir.resolve()):
                item["cover_path"] = str(path.resolve())
        return item

    def clear_cache(self):
        """Nur eigene Cover/Infos löschen; keine Spielpfade, Einstellungen oder Secrets."""
        with self._lock:
            self._assert_cache()
            empty = {"schema_version": 1, "games": {}, "searches": {}}
            write_json(self.path, empty, "Der Cover-Cache")
            self._cache = empty
            self._cache_readonly = False
            self.last_warning = ""
            if self.covers_dir.exists():
                try:
                    for path in self.covers_dir.iterdir():
                        if re.fullmatch(r"[0-9a-f]{64}\.png", path.name) and path.is_file() and not _is_link(path):
                            path.unlink()
                except OSError:
                    raise HubError("Die Infos wurden geleert; einige Cover konnten nicht gelöscht werden. Bitte Schreibrechte prüfen.") from None
