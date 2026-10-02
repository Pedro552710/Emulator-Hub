"""Projekt vor einer Veröffentlichung prüfen, ohne vertrauliche Werte auszugeben.

Die Prüfung liest auch ignorierte Dateien sowie ZIP-/XLSX-Inhalte. Sie verändert
keine Projektdatei. --check schlägt bei ungeklärten Risiken in Git-Kandidaten fehl.
Das temporäre Git-Verzeichnis liegt außerhalb des Projekts; Git wird nicht im
Arbeitsordner initialisiert. Ein Bericht enthält Pfade/Kategorien, niemals Werte.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TEXT_LIMIT = 8 * 1024 * 1024
ARCHIVE_MEMBER_LIMIT = 16 * 1024 * 1024
ARCHIVE_TOTAL_LIMIT = 128 * 1024 * 1024
TEXT_EXTENSIONS = {
    ".py", ".ps1", ".spec", ".json", ".jsonl", ".yaml", ".yml", ".md",
    ".txt", ".ini", ".cfg", ".toml", ".xml", ".bml", ".csv", ".rst",
    ".svg", ".iss", ".bat", ".cmd", ".properties", ".h", ".cpp", ".pem", ".key",
}
GAME_EXTENSIONS = {
    ".rom", ".bios", ".bin", ".nes", ".sfc", ".smc", ".gb", ".gbc",
    ".gba", ".z64", ".n64", ".v64", ".nds", ".3ds", ".iso", ".gcm",
    ".rvz", ".wbfs", ".cue", ".chd", ".cso", ".gen", ".cdi", ".gdi",
    ".nsp", ".xci", ".cia", ".wad", ".dol", ".nro", ".cci", ".wud",
    ".wux", ".rpx", ".vpk", ".elf", ".self", ".sms", ".a26", ".pce", ".zip",
}
BINARY_EXTENSIONS = {".exe", ".dll", ".pyd", ".msi", ".msix", ".appx", ".so", ".dylib"}
ARCHIVE_EXTENSIONS = {".zip", ".xlsx", ".whl", ".7z", ".rar", ".tar", ".gz", ".tgz", ".xz", ".bz2"}
PERSONAL_PATH = re.compile(r"(?:[A-Za-z]:[\\/]+Users[\\/]+)([^\\/\s<>\"']+)", re.I)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")
TOKEN = re.compile(
    r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|"
    r"AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9_-]{24,}|xox[baprs]-[A-Za-z0-9-]{15,})\b"
)
ASSIGNMENT = re.compile(
    r"(?i)[\"']?\b(client[_-]?secret|developer[_-]?password|devpassword|"
    r"password|passwd|kennwort|secret|token|api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"client[_-]?id|developer[_-]?id|devid|username|sspassword|ssuser)"
    r"[\"']?\s*[:=]\s*(?P<quote>[\"'])(?P<value>[^\r\n\"']*)(?P=quote)"
)
REFERENCE = re.compile(r"\b(?:client_secret|developer_password|api_key|access_token|refresh_token|password|passwd|kennwort|sspassword|ssuser|devid|devpassword)\b", re.I)
ENV_ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?([A-Z_]*(?:SECRET|PASSWORD|TOKEN|API_KEY)[A-Z_]*)\s*=\s*([^\s#\"']+)")
URL_CREDENTIAL = re.compile(r"https?://[^\s:/]+:(?P<basic>[^\s/@]+)@|[?&](?:client_secret|password|sspassword|token|api_key)=(?P<query>[^\s&\"']+)", re.I)
SAFE_VALUES = {
    "", "secret", "client", "client-id", "secret-value", "token", "token-1",
    "token-2", "test", "test-token", "test-password", "password", "pass", "user",
    "username", "developer", "dev", "dev-pass", "dummy", "dummy-secret", "dummy-password",
    "app", "appsecret", "client_secret", "client_id", "developer_id", "developer_password",
    "password-secret", "super-secret", "sensitive", "new", "old", "a", "b", "c", "x", "y",
    "ssuser", "sspassword", "devid", "devpassword", "client_credentials", "oauth-token",
    "falsch", "wrong", "wrong-secret", "unused", "Backendtest", "anonymous",
}
SAFE_VALUES = {value.casefold() for value in SAFE_VALUES}
# Explicit values from the account-free mock tests; never an exemption for
# arbitrary credentials merely because someone placed them inside tests/.
FIXTURE_VALUES = {value.casefold() for value in (
    "own-client", "own-user", "own-dev", "TOP_SECRET", "USER_SECRET", "DEV_SECRET",
    "TOKEN_SECRET", "SHOULD_NOT_CACHE", " password ", " dev password ", "eigene-id", "eigenes-test-secret",
)}
FIXTURE_HASHES = {
    "8a7283f6f06bde5975605fa90728777cf873555b364a4501469ab54cd35d2185",
    "f1e8aa093547cd958c6be863ec9ee60c011f4cbde76cf160e98b8fb78a6e553e",
    "8f5d73619873786551563f6e51e9d09e748227b2d8eb4a2366935f5426ef4b28",
    "c557d8f0161f73b35e21169661993fc663d1ceeb0766faa8bb563a6db1fad188",
}
PLACEHOLDER = re.compile(r"(?:<[^>]+>|\$\{|DEIN[_ -]|YOUR[_ -]|EXAMPLE|BEISPIEL|DUMMY|TEST[_ -]|REDACTED|PLATZHALTER)", re.I)
AUDIT_FILES = {"tools/audit_publication.py", "tests/test_publication_audit.py"}


def _safe_path(value):
    """Persönliche Benutzernamen auch in Befundpfaden nicht ausgeben."""
    return PERSONAL_PATH.sub(lambda match: match.group(0).replace(match.group(1), "<Benutzername>"), str(value))


def _category(path):
    first = path.replace("\\", "/").split("/", 1)[0]
    if first in {".venv", "venv"}:
        return "Entwicklungsabhängigkeit"
    if first == "build":
        return "Erzeugte Build-Datei"
    if first in {"dist", "Output"}:
        return "Erzeugte Veröffentlichung"
    if first == "test-artifacts" or path.startswith("ui/.ui-smoke/"):
        return "Lokales Testartefakt"
    if "__pycache__/" in path or path.endswith(".pyc"):
        return "Erzeugter Python-Bytecode"
    return "Projektdatei"


def publication_candidates(root, files):
    """Git-eigene Ignore-Auswertung, auch vor dem ersten git init."""
    with tempfile.TemporaryDirectory(prefix="EmulatorHub-publication-git-") as temporary:
        metadata = Path(temporary) / "repository.git"
        init = subprocess.run(["git", "init", "--bare", "--quiet", str(metadata)],
                              capture_output=True, check=False)
        if init.returncode:
            raise RuntimeError("Git konnte für die Ignore-Prüfung nicht gestartet werden.")
        names = [path.relative_to(root).as_posix() for path in files]
        arguments = ["git", "-c", "core.excludesFile=NUL", f"--git-dir={metadata}",
                     f"--work-tree={root}", "check-ignore", "--no-index", "-z", "--stdin"]
        result = subprocess.run(arguments, input=("\0".join(names) + "\0").encode("utf-8"),
                                cwd=root, capture_output=True, check=False)
        if result.returncode not in (0, 1):
            raise RuntimeError("Die .gitignore konnte nicht zuverlässig ausgewertet werden.")
        ignored = set(result.stdout.decode("utf-8").split("\0")) - {""}
        return sorted(set(names) - ignored), ignored


def inspect_text(path, text, ignored=False):
    findings = []
    source = path.split("!", 1)[0]
    tests = source.startswith("tests/")
    for number, line in enumerate(text.splitlines(), 1):
        if PERSONAL_PATH.search(line):
            # Public/Default are standard Windows folders, not personal users.
            usernames = [match.group(1).casefold() for match in PERSONAL_PATH.finditer(line)]
            if any(name not in {"public", "default", "all", "username", "user", "name"} for name in usernames):
                findings.append({"path": _safe_path(path), "line": number, "kind": "Persönlicher Windows-Pfad",
                                 "classification": "lokaler Pfad" if ignored else "prüfen", "blocking": not ignored})
        if source not in AUDIT_FILES and (PRIVATE_KEY.search(line) or TOKEN.search(line)):
            findings.append({"path": _safe_path(path), "line": number, "kind": "Schlüssel-/Token-Muster",
                             "classification": "prüfen", "blocking": not ignored})
        if source not in AUDIT_FILES:
            for url in URL_CREDENTIAL.finditer(line):
                value = (url.group("basic") or url.group("query")).casefold()
                fixture = tests and value in SAFE_VALUES | FIXTURE_VALUES
                findings.append({"path": _safe_path(path), "line": number, "kind": "Zugangsdaten in URL",
                                 "classification": "synthetischer Testfall" if fixture else "prüfen", "blocking": not ignored and not fixture})
        env = ENV_ASSIGNMENT.search(line)
        if env and source not in AUDIT_FILES:
            placeholder = env.group(2).casefold() in SAFE_VALUES or PLACEHOLDER.search(env.group(2))
            findings.append({"path": _safe_path(path), "line": number, "kind": "Zugangsdaten in Umgebungszuweisung",
                             "classification": "Platzhalter" if placeholder else "prüfen", "blocking": not ignored and not placeholder})
        assignments = list(ASSIGNMENT.finditer(line))
        for match in assignments:
            value = match.group("value")
            # Variable names/defaults/synthetic data are recorded, never echoed.
            fixture = tests and value.casefold() in FIXTURE_VALUES
            placeholder = value.casefold() in SAFE_VALUES or PLACEHOLDER.search(value) or fixture
            fixture = tests and placeholder
            classification = ("synthetischer Testwert" if fixture else
                              "Platzhalter/Feldname" if placeholder else "prüfen")
            findings.append({"path": _safe_path(path), "line": number,
                             "kind": "Zugangsdaten-Feld: " + match.group(1).casefold(),
                             "classification": classification,
                             "blocking": not ignored and not placeholder and source not in AUDIT_FILES})
        if not assignments and REFERENCE.search(line) and source not in AUDIT_FILES:
            findings.append({"path": _safe_path(path), "line": number, "kind": "Zugangsdaten-Verweis",
                             "classification": "Feldname/Programmlogik, kein gespeicherter Wert", "blocking": False})
    return findings


def _decode(data):
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", errors="replace")
    return data.decode("utf-8-sig", errors="replace")


def _content_record(path, size, data, ignored, category):
    suffix = Path(path.split("!")[-1]).suffix.casefold()
    nes = data.startswith(b"NES\x1a")
    windows_binary = data.startswith(b"MZ")
    # Mega-Drive-ROMs verwenden ebenfalls .md. Markdown-Dateien bleiben erlaubt;
    # der binäre Konsolenheader an Offset 0x100 wird unabhängig vom Namen erkannt.
    sega = data[0x100:0x104] == b"SEGA" and b"\0" in data[:0x100]
    if suffix not in GAME_EXTENSIONS | BINARY_EXTENSIONS and not (nes or windows_binary or sega):
        return None
    kind = ("Spiel-/Firmware-Signatur" if nes or sega else
            "Spiel-/Firmware-Endung" if suffix in GAME_EXTENSIONS else "Binärdatei")
    digest = hashlib.sha256(data).hexdigest() if size == len(data) else None
    if category == "Entwicklungsabhängigkeit":
        classification = "Python-/Qt-Abhängigkeit, nicht im Repository"
    elif "test-artifacts/release-tools/" in path.replace("\\", "/"):
        classification = "Lokales Build-Werkzeug, nicht im Repository"
    elif digest in FIXTURE_HASHES:
        classification = "Inhaltlich verifizierte synthetische Testdatei, nicht im Repository"
    elif "test-artifacts/live-data/emulators/" in path.replace("\\", "/"):
        classification = "Heruntergeladene Emulatorinstallation, nicht im Repository"
    elif category == "Erzeugte Veröffentlichung" and "EmulatorHub" in path:
        classification = "Gebauter Emulator Hub, nicht im Quellcode-Repository"
    else:
        classification = "prüfen: Inhalt/Provenienz manuell bestätigen"
    return {"path": _safe_path(path), "size": size, "kind": kind,
            "classification": classification, "ignored": ignored,
            "sha256": digest,
            "blocking": not ignored}


def _zip_records(path, file, ignored, findings, binaries, limits):
    """Archive nur lesen; keine Extraktion und keine verschachtelten Downloads."""
    total = 0
    try:
        with zipfile.ZipFile(file) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                name = path + "!" + member.filename
                suffix = Path(member.filename).suffix.casefold()
                if member.file_size > ARCHIVE_MEMBER_LIMIT or total + member.file_size > ARCHIVE_TOTAL_LIMIT:
                    limits.append({"path": _safe_path(name), "reason": "Archiv-Leselimit", "ignored": ignored})
                    continue
                try:
                    data = archive.read(member)
                except (OSError, RuntimeError, zipfile.BadZipFile):
                    limits.append({"path": _safe_path(name), "reason": "Archiv-Eintrag nicht lesbar", "ignored": ignored})
                    continue
                total += len(data)
                if suffix in TEXT_EXTENSIONS or member.filename.endswith(("LICENSE", "NOTICE")):
                    findings.extend(inspect_text(name, _decode(data), ignored))
                content = _content_record(name, member.file_size, data, ignored, _category(path))
                if content:
                    binaries.append(content)
    except (OSError, zipfile.BadZipFile):
        limits.append({"path": _safe_path(path), "reason": "Archiv nicht als ZIP lesbar", "ignored": ignored})


def audit(root=ROOT):
    root = Path(root).resolve()
    files, skipped = [], []
    for directory, folders, names in os.walk(root, followlinks=False):
        allowed_folders = []
        for name in sorted(folders):
            if name == ".git":
                continue
            path = Path(directory) / name
            try:
                info = path.lstat()
                if path.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                    skipped.append({"path": _safe_path(path.relative_to(root).as_posix()), "reason": "Verknüpfung/Reparse Point", "ignored": False})
                else:
                    allowed_folders.append(name)
            except OSError:
                skipped.append({"path": _safe_path(path.relative_to(root).as_posix()), "reason": "Ordner nicht lesbar", "ignored": False})
        folders[:] = allowed_folders
        for name in sorted(names):
            path = Path(directory) / name
            relative = path.relative_to(root).as_posix()
            try:
                attributes = getattr(path.lstat(), "st_file_attributes", 0)
                if path.is_symlink() or attributes & 0x400:
                    skipped.append({"path": _safe_path(relative), "reason": "Verknüpfung/Reparse Point", "ignored": False})
                else:
                    files.append(path)
            except OSError:
                skipped.append({"path": _safe_path(relative), "reason": "Nicht lesbar", "ignored": False})
    candidates, ignored_paths = publication_candidates(root, files + [root / row["path"] for row in skipped])
    for row in skipped:
        row["ignored"] = row["path"] in ignored_paths
    findings, binaries, archives = [], [], []
    total_size = 0
    for file in files:
        relative = file.relative_to(root).as_posix()
        suffix = file.suffix.casefold()
        ignored = relative in ignored_paths
        try:
            size = file.stat().st_size
            total_size += size
            # Auch umbenannte Dateien prüfen, beispielsweise eine EXE als .dat
            # oder ein ROM in assets/. Die Endung ist keine Sicherheitsgrenze.
            with file.open("rb") as handle:
                header = handle.read(512)
            if suffix in {".xlsx", ".zip", ".whl"}:
                archives.append(_safe_path(relative))
                _zip_records(relative, file, ignored, findings, binaries, skipped)
            elif suffix in ARCHIVE_EXTENSIONS:
                skipped.append({"path": _safe_path(relative), "reason": "Archivformat benötigt gesonderte Prüfung", "ignored": ignored})
            if suffix in TEXT_EXTENSIONS or file.name in {".gitignore", "LICENSE", "NOTICE"} or file.name.startswith(".env"):
                if size <= TEXT_LIMIT:
                    findings.extend(inspect_text(relative, _decode(file.read_bytes()), ignored))
                else:
                    skipped.append({"path": _safe_path(relative), "reason": "Text-Leselimit", "ignored": ignored})
            elif suffix == ".pyc":
                # co_filename can contain personal compiler paths. Values are never printed.
                findings.extend(inspect_text(relative, file.read_bytes().decode("latin-1"), ignored))
            content = _content_record(relative, size, header, ignored, _category(relative))
            if content:
                # Kleine Testdateien vollständig hashen, große Binaries nur am
                # Header erkennen. ZIP-Inhalte werden zusätzlich oben gelesen.
                if size <= TEXT_LIMIT:
                    data = file.read_bytes()
                    content = _content_record(relative, size, data, ignored, _category(relative))
                binaries.append(content)
        except OSError:
            skipped.append({"path": _safe_path(relative), "reason": "Nicht vollständig lesbar", "ignored": ignored})
    blockers = [row for row in findings + binaries if row["blocking"]]
    blockers += [dict(row, kind="Unvollständige Prüfung") for row in skipped if not row["ignored"]]
    return {"created_at": datetime.now(timezone.utc).isoformat(), "file_count": len(files),
            "total_bytes": total_size, "candidate_count": len(candidates),
            "ignored_count": len(ignored_paths), "files_by_area": dict(Counter(_category(path.relative_to(root).as_posix()) for path in files)),
            "publication_files": candidates, "findings": findings, "binary_findings": binaries,
            "archives_checked": archives, "scan_limits": skipped, "blocking_findings": blockers,
            "scope": "Projektordner inklusive ignorierter Dateien; kein Credential Manager und keine externen Spieleordner",
            "limitation": "Heuristische Suche ersetzt keine manuelle Rechte-/Provenienzprüfung; komprimierte EXE-Inhalte und nicht-ZIP-Archive werden nicht vollständig dekodiert."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit 1 bei ungeklärten Risiken in Git-Kandidaten")
    parser.add_argument("--report", type=Path, help="Redigierten JSON-Bericht speichern (am besten unter test-artifacts/)")
    parser.add_argument("--root", type=Path, default=ROOT, help="Anderen Projektordner prüfen")
    args = parser.parse_args()
    try:
        report = audit(args.root)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Geprüft: {report['file_count']} Dateien; {report['candidate_count']} Git-Kandidaten; {report['ignored_count']} ignoriert.")
        print(f"Binär-/Spiel-/Firmware-Fundstellen: {len(report['binary_findings'])}; Archive: {len(report['archives_checked'])}.")
        print("Vertrauliche Werte werden nicht ausgegeben. Bericht und docs/security-audit.md enthalten die Einordnung.")
        for row in report["blocking_findings"]:
            location = row["path"] + (":" + str(row["line"]) if "line" in row else "")
            print("PRÜFEN: " + location + " — " + row.get("kind", row.get("reason", "")))
        print(f"Ungeklärte Veröffentlichungshindernisse: {len(report['blocking_findings'])}.")
        return 1 if args.check and report["blocking_findings"] else 0
    except (OSError, RuntimeError) as error:
        print("Prüfung nicht vollständig möglich: " + str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
