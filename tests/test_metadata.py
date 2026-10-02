"""Cover-/Infotests ohne Konten, Netzwerk oder echte Anmeldeinformationen."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import io
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch

from PIL import Image
import requests

from core.errors import Cancelled, HubError
from core.metadata import MAX_COVER, MetadataService, clean_game_name
from core.settings import SettingsStore
from tests.helpers import Response


class Vault:
    def __init__(self):
        self.values = {}

    def get_password(self, service, username):
        return self.values.get((service, username))

    def set_password(self, service, username, password):
        self.values[service, username] = password

    def delete_password(self, service, username):
        self.values.pop((service, username), None)


class Session:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError("Unerwartete Netzabfrage")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def image_bytes():
    output = io.BytesIO()
    Image.new("RGB", (80, 120), "#62dfb6").save(output, format="JPEG")
    return output.getvalue()


def igdb_game(name="Testspiel", *, game_id=91, platform_id=18):
    return {"id": game_id, "name": name, "first_release_date": 946684800,
            "summary": "Eine <b>Beschreibung</b>.", "genres": [{"name": "Adventure"}],
            "cover": {"image_id": "co_test"}, "url": "https://www.igdb.com/games/testspiel",
            "platforms": [{"id": platform_id, "name": "NES"}]}


def ss_game():
    return {"id": "91", "noms": [{"region": "jp", "text": "JP Name"}, {"region": "wor", "text": "Testspiel"}],
            "systeme": {"id": "3", "nom": "NES"},
            "synopsis": [{"langue": "en", "text": "English"}, {"langue": "de", "text": "Deutsche Beschreibung"}],
            "dates": [{"region": "eu", "text": "2000-01-01"}],
            "genres": [{"noms": [{"langue": "de", "text": "Abenteuer"}]}],
            "medias": [{"type": "box-2D", "region": "wor", "url": "https://api.screenscraper.fr/api2/mediaJeu.php?sspassword=SHOULD_NOT_CACHE"}]}


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.settings = SettingsStore(self.root)
        self.session = Session()
        self.vault = Vault()
        self.service = MetadataService(self.root, self.settings, session=self.session, credential_backend=self.vault)
        self.service._wait = lambda _seconds, event: self.service._cancel(event)
        self.cancel = threading.Event()
        self.messages = []
        self.progress = lambda *_: None
        self.game = {"id": "game-1", "name": "Testspiel (Europe) [!]", "console": "NES", "path": str(self.root / "own.nes")}
        self.service.save_credentials("igdb", {"client_id": "own-client", "client_secret": "TOP_SECRET"})
        self.service.save_credentials("screenscraper", {"username": "own-user", "password": "USER_SECRET", "developer_id": "own-dev", "developer_password": "DEV_SECRET"})

    def search(self, provider="igdb"):
        return self.service.search(self.game, provider, self.progress, self.messages.append, self.cancel)

    def choose(self, candidate):
        return self.service.choose(self.game["id"], candidate, self.progress, self.messages.append, self.cancel)

    def igdb_responses(self, rows=None):
        return [Response(payload={"access_token": "TOKEN_SECRET", "expires_in": 3600}),
                Response(payload=[{"id": 18, "name": "Nintendo Entertainment System (NES)", "abbreviation": "NES"}]),
                Response(payload=rows if rows is not None else [igdb_game()])]

    def ss_responses(self):
        return [Response(payload={"response": {"ssuser": {"id": "own-user", "maxrequestsperdmin": "30", "maxrequestsperday": "500", "requeststoday": "20"}}}),
                Response(payload={"response": {"systemes": [{"id": "3", "noms": {"nom_eu": "Nintendo Entertainment System"}}]}}),
                Response(payload={"response": {"jeux": [ss_game()]}})]

    def test_filename_cleanup_keeps_game_title_and_does_not_read_rom(self):
        self.assertEqual(clean_game_name("0012 - Test_Game (Europe) (Rev 2) [!] Disc 1.nes"), "Test Game")
        self.assertEqual(clean_game_name("Testspiel III"), "Testspiel III")
        self.assertFalse(Path(self.game["path"]).exists())

    def test_credentials_only_in_vault_not_settings_cache_or_logs(self):
        self.assertEqual(self.service.load_credentials("igdb")["client_secret"], "TOP_SECRET")
        self.assertEqual(self.settings.get("client_secret"), None)
        self.session.responses = self.igdb_responses()
        self.search()
        text = self.service.path.read_text(encoding="utf-8") + " ".join(self.messages)
        for secret in ("TOP_SECRET", "TOKEN_SECRET", "USER_SECRET", "DEV_SECRET"):
            self.assertNotIn(secret, text)
        self.service.save_credentials("igdb", {"client_id": "", "client_secret": ""})
        self.assertEqual(self.service.load_credentials("igdb"), {"client_id": "", "client_secret": ""})

    def test_vault_errors_never_expose_secret_or_use_plaintext_fallback(self):
        with patch.object(self.vault, "set_password", side_effect=RuntimeError("TOP_SECRET")):
            with self.assertRaises(HubError) as raised:
                self.service.save_credentials("igdb", {"client_id": "client", "client_secret": "TOP_SECRET"})
        self.assertNotIn("TOP_SECRET", str(raised.exception))
        self.assertEqual(list(self.root.iterdir()), [])

    def test_igdb_console_filter_unique_exact_title_and_search_cache(self):
        self.session.responses = self.igdb_responses()
        candidates = self.search()
        self.assertEqual(candidates[0]["year"], 2000)
        self.assertEqual(candidates[0]["description"], "Eine Beschreibung.")
        self.assertFalse(candidates[0]["requires_confirmation"])
        self.assertEqual(candidates[0]["confidence"], 1.0)
        self.assertIn(b"where platforms = (18)", self.session.calls[-1][2]["data"])
        self.assertEqual(self.search(), candidates)
        self.assertEqual(len(self.session.calls), 3)
        self.assertIsNone(self.service.get(self.game["id"]))

    def test_uncertain_multiple_or_other_platform_results_require_confirmation(self):
        self.session.responses = self.igdb_responses([igdb_game(), igdb_game("Testspiel II", game_id=92)])
        self.assertTrue(all(c["requires_confirmation"] for c in self.search()))
        self.service.clear_cache()
        self.session.responses = [Response(payload=[igdb_game(platform_id=999)])]
        self.assertTrue(self.search()[0]["requires_confirmation"])

    def test_unassigned_and_unknown_console_stop_before_game_lookup(self):
        self.game["console"] = None
        with self.assertRaisesRegex(HubError, "Konsole"):
            self.search()
        self.assertEqual(self.session.calls, [])
        self.game["console"] = "Unbekannte Konsole"
        self.session.responses = self.igdb_responses()[:2]
        with self.assertRaisesRegex(HubError, "nicht eindeutig"):
            self.search()
        self.assertEqual(len(self.session.calls), 2)

    def test_cover_validated_normalized_offline_and_survives_portable_move(self):
        self.session.responses = self.igdb_responses() + [Response(body=image_bytes())]
        candidate = self.search()[0]
        result = self.choose(candidate)
        cover = Path(result["cover_path"])
        self.assertTrue(cover.is_absolute())
        with Image.open(cover) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, (80, 120))
        stored = json.loads(self.service.path.read_text())
        self.assertRegex(stored["games"]["game-1"]["cover_path"], r"^covers/[0-9a-f]{64}\.png$")
        copied = self.root / "moved"
        shutil.copytree(self.service.cache_dir, copied / "cache")
        offline = MetadataService(copied, SettingsStore(copied), session=Session(), credential_backend=Vault())
        self.assertEqual(offline.get("game-1")["title"], "Testspiel")
        self.assertTrue(Path(offline.get("game-1")["cover_path"]).is_relative_to(copied))
        self.assertEqual(offline.search(self.game, "igdb", self.progress, self.messages.append, self.cancel), [candidate])
        self.service.choose("game-2", candidate, self.progress, self.messages.append, self.cancel)
        self.assertEqual(len(self.session.calls), 4)

    def test_screen_scraper_search_details_localization_quota_and_no_media_secrets(self):
        self.session.responses = self.ss_responses() + [Response(payload={"response": {"jeu": ss_game()}}), Response(body=image_bytes())]
        result = self.choose(self.search("screenscraper")[0])
        self.assertEqual(result["title"], "Testspiel")
        self.assertEqual(result["description"], "Deutsche Beschreibung")
        self.assertEqual(result["genres"], ["Abenteuer"])
        self.assertEqual(result["year"], 2000)
        self.assertEqual(self.service._intervals["screenscraper"], 2.05)
        params = self.session.calls[-1][2]["params"]
        self.assertEqual(params["media"], "box-2D(wor)")
        self.assertEqual(params["jeuid"], "91")
        self.assertNotIn("romnom", self.session.calls[-2][2]["params"])
        text = self.service.path.read_text() + " ".join(self.messages)
        for secret in ("SHOULD_NOT_CACHE", "USER_SECRET", "DEV_SECRET"):
            self.assertNotIn(secret, text)

    def test_screen_scraper_daily_quota_stops_without_further_requests(self):
        self.session.responses = [Response(payload={"response": {"ssuser": {"id": "own-user", "maxrequestsperday": 100, "requeststoday": 100}}})]
        self.service.test_connection("screenscraper", self.progress, self.messages.append, self.cancel)
        with self.assertRaisesRegex(HubError, "Kontingent"):
            self.search("screenscraper")
        self.assertEqual(len(self.session.calls), 1)

    def test_retry_rate_limit_respects_wait_is_cancellable_and_sanitizes_network_errors(self):
        waits = []
        self.service._wait = lambda seconds, event: (waits.append(seconds), self.service._cancel(event))
        self.session.responses = [Response(status=429, headers={"Retry-After": "9"}), Response(payload={"access_token": "TOKEN_SECRET", "expires_in": 3600}), Response(payload=[])]
        self.service.test_connection("igdb", self.progress, self.messages.append, self.cancel)
        self.assertIn(9, waits)
        self.assertTrue(all(r[2]["allow_redirects"] is False and r[2]["timeout"] == (4, 6) for r in self.session.calls))
        self.session.responses = [requests.ConnectionError("TOP_SECRET") for _ in range(4)]
        with self.assertRaises(HubError) as raised:
            self.service.test_connection("igdb", self.progress, self.messages.append, self.cancel)
        self.assertNotIn("TOP_SECRET", str(raised.exception) + " ".join(self.messages))
        self.cancel.set()
        count = len(self.session.calls)
        with self.assertRaises(Cancelled):
            self.search()
        self.assertEqual(len(self.session.calls), count)

    def test_long_retry_after_and_http_date_are_respected_without_shortened_retry(self):
        waits = []
        self.service._wait = lambda seconds, event: (waits.append(seconds), self.service._cancel(event))
        self.session.responses = [Response(status=429, headers={"Retry-After": "180"}),
                                  Response(payload={"access_token": "TOKEN_SECRET", "expires_in": 3600}), Response(payload=[])]
        self.service.test_connection("igdb", self.progress, self.messages.append, self.cancel)
        self.assertIn(180, waits)
        retry_at = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=240), usegmt=True)
        self.session.responses = [Response(status=429, headers={"Retry-After": retry_at}), Response(payload=[])]
        self.service.test_connection("igdb", self.progress, self.messages.append, self.cancel)
        self.assertTrue(any(238 <= delay <= 241 for delay in waits))
        count = len(self.session.calls)
        self.session.responses = [Response(status=429, headers={"Retry-After": "7200"})]
        with self.assertRaisesRegex(HubError, "längere Pause"):
            self.service.test_connection("igdb", self.progress, self.messages.append, self.cancel)
        self.assertEqual(len(self.session.calls), count + 1)

    def test_cancel_during_response_does_not_commit_candidate_or_cover(self):
        self.session.responses = self.igdb_responses()
        candidate = self.search()[0]
        response = Response(body=image_bytes())
        def chunks(_size):
            self.cancel.set()
            yield response.content
        response.iter_content = chunks
        self.session.responses = [response]
        with self.assertRaises(Cancelled):
            self.choose(candidate)
        self.assertIsNone(self.service.get("game-1"))
        self.assertTrue(response.closed)
        self.assertFalse(self.service.covers_dir.exists())

    def test_malicious_url_invalid_image_oversized_cover_keep_infos_without_downloaded_game(self):
        self.session.responses = self.igdb_responses()
        candidate = self.search()[0]
        candidate["cover_url"] = "https://untrusted.example/game.zip"
        result = self.choose(candidate)
        self.assertEqual(result["cover_path"], "")
        self.assertIn("erlaubten", result["cover_warning"])
        self.assertEqual(len(self.session.calls), 3)
        candidate["cover_url"] = "https://images.igdb.com/igdb/image/upload/t_cover_big/co_test.jpg"
        self.session.responses = [Response(body=b"not an image")]
        self.assertIn("gültiges", self.choose(candidate)["cover_warning"])
        self.session.responses = [Response(headers={"Content-Length": str(MAX_COVER + 1)})]
        self.assertIn("zu groß", self.choose(candidate)["cover_warning"])
        self.assertFalse(self.service.covers_dir.exists())

    def test_redirect_with_credentials_is_not_followed_or_logged(self):
        self.session.responses = [Response(status=302, headers={"Location": "https://untrusted.example/?password=USER_SECRET"})]
        with self.assertRaisesRegex(HubError, "umgeleitet") as raised:
            self.service.test_connection("screenscraper", self.progress, self.messages.append, self.cancel)
        self.assertNotIn("USER_SECRET", str(raised.exception) + " ".join(self.messages))
        self.assertEqual(len(self.session.calls), 1)

    def test_corrupt_cache_does_not_block_start_or_get_overwritten_before_clear(self):
        self.service.path.parent.mkdir()
        self.service.path.write_text("BROKEN", encoding="utf-8")
        optional = MetadataService(self.root, self.settings, session=Session(), credential_backend=self.vault)
        self.assertTrue(optional.last_warning)
        self.assertIsNone(optional.get("game-1"))
        with self.assertRaisesRegex(HubError, "Cache leeren"):
            optional.search(self.game, "igdb", self.progress, self.messages.append, self.cancel)
        self.assertEqual(optional.path.read_text(), "BROKEN")
        optional.clear_cache()
        self.assertFalse(optional.last_warning)
        self.assertFalse(optional._cache_readonly)

    def test_malformed_cached_game_fields_are_quarantined_and_preserved(self):
        self.service.path.parent.mkdir()
        malformed = {"schema_version": 1, "games": {"game-1": {"title": [], "genres": None}}, "searches": {}}
        self.service.path.write_text(json.dumps(malformed), encoding="utf-8")
        optional = MetadataService(self.root, self.settings, session=Session(), credential_backend=self.vault)
        self.assertTrue(optional.last_warning)
        self.assertIsNone(optional.get("game-1"))
        self.assertEqual(json.loads(optional.path.read_text()), malformed)

    def test_separate_console_aliases_match_current_service_platform_names(self):
        self.game["console"] = "Mega Drive"
        row = igdb_game(platform_id=29)
        row["platforms"][0]["name"] = "Sega Mega Drive/Genesis"
        self.session.responses = [Response(payload={"access_token": "TOKEN_SECRET", "expires_in": 3600}),
                                  Response(payload=[{"id": 29, "name": "Sega Mega Drive/Genesis"}]), Response(payload=[row])]
        self.assertFalse(self.search()[0]["requires_confirmation"])
        self.assertIn(b"where platforms = (29)", self.session.calls[-1][2]["data"])

    def test_password_spaces_remain_exact_and_wrong_shape_response_has_german_error(self):
        self.service.save_credentials("screenscraper", {"username": "own-user", "password": " password ", "developer_id": "own-dev", "developer_password": " dev password "})
        self.assertEqual(self.service.load_credentials("screenscraper")["password"], " password ")
        self.session.responses = [Response(payload={"access_token": "TOKEN_SECRET", "expires_in": 3600}), Response(payload={"broken": []})]
        with self.assertRaisesRegex(HubError, "gültige Trefferliste"):
            self.service.test_connection("igdb", self.progress, self.messages.append, self.cancel)

    def test_clear_cache_only_removes_generated_covers_not_games_settings_or_credentials(self):
        self.session.responses = self.igdb_responses() + [Response(body=image_bytes())]
        self.choose(self.search()[0])
        game = Path(self.game["path"])
        game.write_bytes(b"own game not downloaded")
        keep = self.service.covers_dir / "my-file.png"
        keep.write_bytes(b"unmanaged")
        self.settings.set("favorites", ["test"])
        vault = deepcopy(self.vault.values)
        self.service.clear_cache()
        self.assertIsNone(self.service.get("game-1"))
        self.assertEqual(game.read_bytes(), b"own game not downloaded")
        self.assertTrue(keep.exists())
        self.assertEqual(self.settings.favorites, ["test"])
        self.assertEqual(self.vault.values, vault)
        self.assertEqual(list(self.service.covers_dir.iterdir()), [keep])

    def test_external_cached_cover_path_is_never_exposed(self):
        self.service._cache["games"]["game-1"] = {"title": "Testspiel", "cover_path": str(self.root / "own.nes")}
        self.assertEqual(self.service.get("game-1")["cover_path"], "")

    def test_screenscraper_requires_own_developer_credentials_before_request(self):
        self.service.save_credentials("screenscraper", {"username": "own-user", "password": "USER_SECRET"})
        with self.assertRaisesRegex(HubError, "Entwickler"):
            self.service.test_connection("screenscraper", self.progress, self.messages.append, self.cancel)
        self.assertEqual(self.session.calls, [])


if __name__ == "__main__":
    unittest.main()
