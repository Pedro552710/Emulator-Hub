"""Verknüpfungen ausschließlich im Startmenü/auf dem Desktop des Benutzers."""
import base64
import ctypes
import os
from pathlib import Path
import subprocess

from .errors import HubError


def shortcut_folders():
    if os.name != "nt":
        return {}
    result = {}
    for key, csidl in (("desktop", 0x10), ("startmenu", 0x02)):
        buffer = ctypes.create_unicode_buffer(32768)
        if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buffer) == 0:
            folder = Path(buffer.value)
            result[key] = folder if key == "desktop" else folder / "Emulator Hub"
    return result


def _quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def create_shortcuts(entry, executable, choices):
    from .launch import build_emulator_command
    command, _ = build_emulator_command(entry, executable)
    executable = Path(command[0])
    arguments = subprocess.list2cmdline(command[1:])
    folders = shortcut_folders()
    paths = []
    for choice, folder in folders.items():
        if not choices.get(choice):
            continue
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"Emulator Hub - {entry['id']}.lnk"
        script = ("$ErrorActionPreference='Stop'; $w=New-Object -ComObject WScript.Shell; "
                  f"$s=$w.CreateShortcut({_quote(target)}); "
                  f"$s.TargetPath={_quote(executable)}; "
                  f"$s.Arguments={_quote(arguments)}; "
                  f"$s.WorkingDirectory={_quote(Path(executable).parent)}; "
                  f"$s.Description={_quote(entry['emulator'])}; $s.Save()")
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                                 "-EncodedCommand", encoded], capture_output=True,
                                timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise HubError("Die Verknüpfung konnte nicht angelegt werden. Der Emulator wurde trotzdem installiert.")
        paths.append(str(target))
    return paths


def remove_shortcuts(entry, paths):
    approved = {folder / f"Emulator Hub - {entry['id']}.lnk" for folder in shortcut_folders().values()}
    for value in paths:
        path = Path(value)
        if path in approved:
            path.unlink(missing_ok=True)
