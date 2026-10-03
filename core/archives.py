"""Archivextraktion mit Pfad-, Link- und Größenprüfung vor dem Schreiben."""
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import zipfile

from .errors import HubError, Cancelled

MAX_EXPANDED = 4 * 1024 ** 3
MAX_FILES = 50000
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_member(name, destination):
    normalized = name.replace("\\", "/")
    p = PurePosixPath(normalized)
    if not normalized or p.is_absolute() or any(s in (".", "..") for s in normalized.split("/") if s):
        raise HubError("Das Archiv enthält einen unsicheren Dateipfad.")
    for part in p.parts:
        if (any(c in part for c in ':<>"|?*') or part.endswith((".", " "))
                or part.split(".")[0].upper() in RESERVED or any(ord(c) < 32 for c in part)):
            raise HubError("Das Archiv enthält einen ungültigen Windows-Dateinamen.")
    target = Path(destination).joinpath(*p.parts)
    if not target.resolve().is_relative_to(Path(destination).resolve()):
        raise HubError("Das Archiv versucht außerhalb des Installationsordners zu schreiben.")
    return target


def _validate(members, destination):
    total = 0
    seen = set()
    for name, size, is_link in members:
        safe_member(name, destination)
        folded = name.replace("\\", "/").rstrip("/").casefold()
        if folded in seen or is_link:
            raise HubError("Das Archiv enthält doppelte Pfade oder Verknüpfungen und wird nicht entpackt.")
        seen.add(folded)
        total += size
        if total > MAX_EXPANDED or len(seen) > MAX_FILES:
            raise HubError("Das Archiv überschreitet die sichere Entpackgröße.")


def extract_archive(archive, destination, kind, cancel_event, *, progress=None):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    try:
        if cancel_event.is_set():
            raise Cancelled()
        if kind == "zip":
            with zipfile.ZipFile(archive) as zf:
                infos = zf.infolist()
                _validate([(i.filename, i.file_size, stat.S_ISLNK(i.external_attr >> 16)) for i in infos], destination)
                total = sum(info.file_size for info in infos)
                extracted = 0
                for info in infos:
                    if cancel_event.is_set():
                        raise Cancelled()
                    target = safe_member(info.filename, destination)
                    if info.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with zf.open(info) as src, target.open("wb") as dst:
                            while chunk := src.read(1024 * 1024):
                                if cancel_event.is_set():
                                    raise Cancelled()
                                dst.write(chunk)
                                extracted += len(chunk)
                                if progress is not None:
                                    progress(extracted / max(1, total))
        elif kind == "7z":
            import py7zr
            with py7zr.SevenZipFile(archive, "r") as zf:
                _validate([(i.filename, i.uncompressed or 0,
                            i.is_symlink or i.is_junction or i.is_socket) for i in zf.files], destination)
                zf.extractall(destination)
        elif kind == "tar":
            with tarfile.open(archive) as tf:
                members = tf.getmembers()
                _validate([(i.name, i.size, not (i.isfile() or i.isdir())) for i in members], destination)
                for member in members:
                    if cancel_event.is_set():
                        raise Cancelled()
                    tf.extract(member, destination, filter="data")
        else:
            raise HubError("Dieses Archivformat wird nicht automatisch entpackt. Bitte die Anleitung verwenden.")
        if cancel_event.is_set():
            raise Cancelled()
    except HubError:
        raise
    except Exception as exc:
        raise HubError(f"Entpacken fehlgeschlagen. Das Archiv ist möglicherweise beschädigt: {exc}") from None


def assert_plain_tree(path):
    """Reparse Points werden vor rekursivem Löschen strikt abgelehnt."""
    path = Path(path)
    for item in [path, *path.rglob("*")]:
        info = item.lstat()
        if item.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise HubError("Der Installationsordner enthält eine Verknüpfung. Aus Sicherheitsgründen bitte manuell entfernen.")


def remove_managed_tree(path, root):
    path, root = Path(path), Path(root).resolve()
    if path.parent.resolve() != root or path.resolve() == root:
        raise HubError("Löschen außerhalb des verwalteten Emulatorordners wurde verhindert.")
    if path.exists():
        assert_plain_tree(path)
        shutil.rmtree(path)
