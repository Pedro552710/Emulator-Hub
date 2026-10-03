"""Stabile GitHub-Releases und eindeutige Windows-x64-Assets."""
import re
import time

from .errors import HubError


class GitHubClient:
    def __init__(self, policy):
        self.policy = policy
        self._cache = {}

    def latest(self, repo, force=False):
        if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo or "")
                or any(part in (".", "..") for part in repo.split("/"))):
            raise HubError("Das offizielle GitHub-Repository ist im Katalog nicht richtig eingetragen.")
        cached = self._cache.get(repo)
        if cached and not force and time.monotonic() - cached[0] < 900:
            return cached[1]
        with self.policy.get(f"https://api.github.com/repos/{repo}/releases/latest",
                             headers={"Accept": "application/vnd.github+json",
                                      "X-GitHub-Api-Version": "2022-11-28"}) as response:
            if len(response.content) > 8 * 1024 * 1024:
                raise HubError("Die Release-Antwort ist ungewöhnlich groß.")
            try:
                release = response.json()
            except ValueError:
                raise HubError("Die Quelle lieferte keine gültigen Release-Daten.") from None
        if (not isinstance(release, dict) or release.get("draft") or release.get("prerelease")
                or not release.get("tag_name") or not isinstance(release.get("assets"), list)):
            raise HubError("Es ist kein verwendbares stabiles Release verfügbar. Bitte die Anleitung verwenden.")
        self._cache[repo] = (time.monotonic(), release)
        return release

    def asset(self, entry, release):
        if entry.get("entry_type") == "utility" and (not isinstance(release, dict)
                or release.get("draft") or release.get("prerelease")):
            raise HubError("Für dieses Hilfsprogramm ist kein stabiles Release verfügbar. Bitte die manuelle Anleitung verwenden.")
        pattern = entry.get("download_muster", "")
        if not pattern:
            raise HubError("Für diesen Emulator ist kein zuverlässiges Windows-Downloadmuster hinterlegt.")
        matches = [a for a in release["assets"] if re.fullmatch(pattern, a.get("name", ""), re.I)]
        if len(matches) != 1:
            raise HubError("Das Windows-x64-Asset konnte nicht eindeutig erkannt werden. Bitte die manuelle Anleitung verwenden.")
        asset = matches[0]
        self.policy.validate(asset.get("browser_download_url", ""))
        # Ein Asset darf nicht auf ein anderes freigegebenes Repository ausweichen.
        expected = f"https://github.com/{entry['github_repo']}/releases/download/"
        if not asset["browser_download_url"].startswith(expected):
            raise HubError("Das Download-Asset gehört nicht zum offiziellen Repository.")
        return asset
