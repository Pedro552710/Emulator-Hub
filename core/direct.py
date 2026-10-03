"""Resolve the stable WinUAE ZIP from links on the official download page."""
from dataclasses import dataclass
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit

import requests

from .errors import Cancelled, HubError

WINUAE_PAGE = "https://www.winuae.net/download/"
WINUAE_RELEASES = "https://download.abime.net/winuae/releases/"
MAX_PAGE_SIZE = 1024 * 1024


@dataclass(frozen=True)
class DirectAsset:
    url: str
    name: str
    version: str


class _WinUAEDownloadPage(HTMLParser):
    """Associate links with the version heading, excluding other sections."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.version = None
        self.headings = set()
        self.links = []
        self._heading_tags = []
        self._heading_text = []
        self._anchor = None
        self._anchor_text = []

    def handle_starttag(self, tag, attrs):
        if tag in {"strong", "h1", "h2", "h3", "h4", "h5", "h6"}:
            if not self._heading_tags:
                self._heading_text = []
            self._heading_tags.append(tag)
        if tag == "a":
            self._anchor = (self.version, dict(attrs).get("href", ""))
            self._anchor_text = []

    def handle_data(self, data):
        if self._heading_tags:
            self._heading_text.append(data)
        if self._anchor is not None:
            self._anchor_text.append(data)

    def handle_endtag(self, tag):
        if self._heading_tags and tag == self._heading_tags[-1]:
            self._heading_tags.pop()
            if not self._heading_tags:
                text = " ".join("".join(self._heading_text).split())
                match = re.fullmatch(r"Download WinUAE ([0-9]+\.[0-9]+\.[0-9]+)", text)
                self.version = match[1] if match else None
                if self.version:
                    self.headings.add(self.version)
        if tag == "a" and self._anchor is not None:
            version, href = self._anchor
            self.links.append((version, href, "".join(self._anchor_text)))
            self._anchor = None


def select_winuae_asset(html, policy):
    """Fail closed when the stable heading, versioned x64 ZIP or host changes."""
    parser = _WinUAEDownloadPage()
    parser.feed(html)
    parser.close()
    if len(parser.headings) != 1:
        raise HubError("WinUAE: Die stabile Versionsangabe ist nicht eindeutig. Bitte manuell prüfen.")
    version = next(iter(parser.headings))
    # This filename convention is checked against an actual link, never used
    # to construct an unverified download URL.
    expected_name = "WinUAE" + version.replace(".", "") + "0_x64.zip"
    candidates = set()
    for section_version, href, label in parser.links:
        if section_version != version:
            continue
        url = urljoin(WINUAE_PAGE, href)
        try:
            parts = urlsplit(url)
        except ValueError:
            raise HubError("WinUAE: Ungültiger Downloadlink. Bitte manuell prüfen.") from None
        filename = parts.path.rsplit("/", 1)[-1]
        if not re.fullmatch(r"WinUAE[0-9]+_x64\.zip", filename):
            continue
        if (filename != expected_name or url != WINUAE_RELEASES + filename
                or not re.search(r"zip.*64-bit", label, re.I)
                or re.search(r"beta|preview|nightly|experimental", label, re.I)):
            raise HubError("WinUAE: Downloadquelle oder Version passt nicht zum stabilen 64-Bit-ZIP. Bitte manuell prüfen.")
        policy.validate(url)
        candidates.add(url)
    if len(candidates) != 1:
        raise HubError("WinUAE: Kein eindeutiges stabiles 64-Bit-ZIP gefunden. Bitte die offizielle Downloadseite manuell prüfen.")
    return DirectAsset(next(iter(candidates)), expected_name, version)


def resolve_winuae(policy, entry, cancel_event):
    if entry.get("direct_url") != WINUAE_PAGE:
        raise HubError("WinUAE: Die Ermittlung benötigt die offizielle Downloadseite.")
    if cancel_event.is_set():
        raise Cancelled()
    try:
        with policy.get(WINUAE_PAGE, stream=True) as response:
            body = bytearray()
            for chunk in response.iter_content(65536):
                if cancel_event.is_set():
                    raise Cancelled()
                body.extend(chunk)
                if len(body) > MAX_PAGE_SIZE:
                    raise HubError("WinUAE: Die Downloadseite ist ungewöhnlich groß. Bitte manuell prüfen.")
    except requests.exceptions.RequestException:
        raise HubError("WinUAE: Die Downloadseite konnte nicht vollständig geladen werden. Bitte manuell prüfen.") from None
    try:
        html = body.decode("utf-8-sig")
    except UnicodeError:
        raise HubError("WinUAE: Die Downloadseite konnte nicht gelesen werden. Bitte manuell prüfen.") from None
    return select_winuae_asset(html, policy)
