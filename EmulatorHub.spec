# -*- mode: python ; coding: utf-8 -*-
"""Ordner-Build: Qt-Bibliotheken bleiben als austauschbare Dateien erhalten."""
from importlib import metadata
from pathlib import Path
import re
import runpy
import sys

from PySide6.QtCore import QLibraryInfo
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo, StringFileInfo, StringStruct, StringTable,
    VarFileInfo, VarStruct, VSVersionInfo,
)


project = Path(SPECPATH)
version = runpy.run_path(str(project / "core" / "version.py"))["VERSION"]
if not re.fullmatch(r"\d+\.\d+\.\d+", version):
    raise ValueError("core/version.py muss eine Version im Format X.Y.Z enthalten.")
version_tuple = (*map(int, version.split(".")), 0)
translations = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
datas = [
    (str(project / "assets"), "assets"),
    (str(project / "catalog.json"), "."),
    (str(project / "configs"), "configs"),
    (str(translations / "qtbase_de.qm"), "PySide6/translations"),
    (str(project / "LICENSE"), "."),
    (str(project / "THIRD_PARTY_NOTICES.md"), "."),
]
legal_docs = project / "docs" / "licenses"
if legal_docs.is_dir():
    datas.append((str(legal_docs), "licenses/legal"))

# Originaltexte aus den installierten Wheels mitliefern. Keine Python-Dateien
# oder Nutzerdaten einsammeln; fehlende Texte sind in den Projekt-Notices erklärt.
for distribution in metadata.distributions():
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", distribution.metadata["Name"])
    for entry in distribution.files or ():
        path = Path(str(entry))
        if path.is_absolute() or ".." in path.parts:
            continue
        if path.suffix.casefold() in {".py", ".pyc", ".pyd", ".dll", ".so"}:
            continue
        if not path.name.upper().startswith(("LICENSE", "COPYING", "NOTICE", "COPYRIGHT", "AUTHORS")):
            continue
        source = Path(distribution.locate_file(entry))
        if source.is_file():
            # Beispielsweise setuptools enthält mehrere fremde LICENSE-Dateien.
            # Die ursprünglichen Unterordner verhindern Überschreiben gleicher Namen.
            destination = Path("licenses") / f"{name}-{distribution.version}" / path.parent
            datas.append((str(source), destination.as_posix()))
python_license = Path(sys.base_prefix) / "LICENSE.txt"
if python_license.is_file():
    datas.append((str(python_license), "licenses/Python"))

hiddenimports = ["keyring.backends.Windows", "win32ctypes.pywin32.win32cred"]
hiddenimports += collect_submodules("win32ctypes.core.ctypes")

version_info = VSVersionInfo(
    ffi=FixedFileInfo(filevers=version_tuple, prodvers=version_tuple,
                      mask=0x3F, flags=0, OS=0x40004, fileType=0x1,
                      subtype=0, date=(0, 0)),
    kids=[
        StringFileInfo([StringTable("040704B0", [
            StringStruct("FileDescription", "Emulator Hub"),
            StringStruct("FileVersion", version),
            StringStruct("InternalName", "EmulatorHub"),
            StringStruct("OriginalFilename", "EmulatorHub.exe"),
            StringStruct("ProductName", "Emulator Hub"),
            StringStruct("ProductVersion", version),
        ])]),
        VarFileInfo([VarStruct("Translation", [1031, 1200])]),
    ],
)

a = Analysis(
    [str(project / "main.py")],
    pathex=[str(project)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(project / "tools" / "pyinstaller_hooks")],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.QtVirtualKeyboard", "PySide6.QtPdf", "PySide6.QtPdfWidgets"],
    noarchive=False,
    optimize=0,
)
# Auch bei einer unerwarteten zusätzlichen Hook-Quelle keine unbenutzten
# VirtualKeyboard-/PDF-Dateien verteilen. Windows-Eingabeplugins bleiben erhalten.
def without_unused_qt(toc):
    def excluded(entry):
        paths = [str(path).replace("\\", "/").casefold() for path in entry[:2]]
        return any("virtualkeyboard" in path or path.rsplit("/", 1)[-1].startswith("qt6pdf")
                   or path.rsplit("/", 1)[-1] == "qpdf.dll" for path in paths)

    return [entry for entry in toc if not excluded(entry)]


a.binaries = without_unused_qt(a.binaries)
a.datas = without_unused_qt(a.datas)
# Windows 10/11 stellen UCRT/API-Set bereits als Systemkomponenten bereit.
# Keine app-lokalen Kompatibilitätskopien aus fremden PATH-Verzeichnissen übernehmen.
a.binaries = [entry for entry in a.binaries
              if not Path(entry[0]).name.casefold().startswith("api-ms-win-")
              and Path(entry[0]).name.casefold() != "ucrtbase.dll"]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="EmulatorHub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="_internal",
    icon=[str(project / "assets" / "icon.ico")],
    version=version_info,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="EmulatorHub",
)
