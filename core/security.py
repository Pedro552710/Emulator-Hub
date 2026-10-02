"""Explizite Quellenfreigabe, auch für Weiterleitungen und GitHub-Assets."""
import re
from urllib.parse import unquote, urlsplit, urljoin

import requests

from .errors import HubError


class URLPolicy:
    # Diese Hosts dienen ausschließlich GitHub-Release-Weiterleitungen.
    GITHUB_CDN = {"release-assets.githubusercontent.com", "objects.githubusercontent.com"}

    def __init__(self, prefixes):
        self.prefixes = tuple(prefixes)
        for prefix in self.prefixes:
            self._parse(prefix)

    @staticmethod
    def _parse(url):
        try:
            p = urlsplit(url)
            if (p.scheme != "https" or not p.hostname or p.username or p.password
                    or p.port not in (None, 443) or "\\" in url
                    or any(ord(c) < 32 for c in url)):
                raise ValueError()
            decoded = unquote(p.path)
            if "\\" in decoded or any(s in (".", "..") for s in decoded.split("/")):
                raise ValueError()
            return p
        except (ValueError, TypeError):
            raise HubError("Die Adresse ist keine sichere HTTPS-Adresse.") from None

    def allows(self, url):
        p = self._parse(url)
        for prefix in self.prefixes:
            base = self._parse(prefix)
            if p.netloc.lower() != base.netloc.lower():
                continue
            path = base.path.rstrip("/")
            if not path or p.path == path or p.path.startswith(path + "/"):
                return True
        # Die API wird nur für bereits freigegebene offizielle Repositories erlaubt.
        if p.hostname == "api.github.com":
            match = re.fullmatch(r"/repos/([^/]+)/([^/]+)/releases(?:/latest)?", p.path)
            if match:
                return self.allows(f"https://github.com/{match[1]}/{match[2]}")
        return False

    def validate(self, url):
        if not self.allows(url):
            raise HubError("Die Adresse steht nicht in der Whitelist der offiziellen Quellen.")
        return url

    def get(self, url, *, stream=False, headers=None):
        """Kein ungeprüftes automatisches Redirect; niemals HTTP-Fallback."""
        self.validate(url)
        original = self._parse(url)
        github_asset = (original.hostname == "github.com"
                        and "/releases/download/" in original.path)
        session = requests.Session()
        session.headers.update({"User-Agent": "EmulatorHub/1.0", "Accept-Encoding": "identity"})
        current = url
        try:
            for _ in range(6):
                p = self._parse(current)
                if not (github_asset and p.hostname in self.GITHUB_CDN):
                    self.validate(current)
                response = session.get(current, timeout=(15, 30), stream=stream,
                                       allow_redirects=False, headers=headers)
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    response.close()
                    if not location:
                        raise HubError("Der Downloadserver lieferte eine ungültige Weiterleitung.")
                    current = urljoin(current, location)
                    continue
                if response.status_code in (403, 429):
                    response.close()
                    raise HubError("Die Quelle begrenzt gerade die Anfragen. Bitte später erneut versuchen oder die Anleitung verwenden.")
                if response.status_code == 404:
                    response.close()
                    raise HubError("Die Download-Datei wurde nicht gefunden. Bitte die manuelle Anleitung verwenden.")
                response.raise_for_status()
                return response
            raise HubError("Der Download enthält zu viele Weiterleitungen.")
        except requests.exceptions.SSLError:
            raise HubError("Das HTTPS-Zertifikat konnte nicht geprüft werden. Der Download wurde gestoppt.") from None
        except requests.exceptions.Timeout:
            raise HubError("Die Quelle antwortet nicht rechtzeitig. Bitte Internetverbindung prüfen und erneut versuchen.") from None
        except requests.exceptions.ConnectionError:
            raise HubError("Keine Verbindung zur offiziellen Quelle. Bitte die Internetverbindung prüfen.") from None
        except requests.exceptions.RequestException as exc:
            raise HubError(f"Die offizielle Quelle konnte nicht gelesen werden: {exc}") from None
        finally:
            # Die Response hält ihren Adapter bis zum Schließen durch den Aufrufer.
            session.close()
