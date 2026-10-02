"""Qt-Standardhook mit den vom Hub verwendeten Windows-Eingabe-/Bildplugins.

Die QWidget-Oberfläche verwendet keine Qt-Bildschirmtastatur und zeigt keine
PDF-Dokumente. Diese optionalen Plugins vor der DLL-Abhängigkeitsanalyse auslassen.
"""
from pathlib import Path

from PyInstaller.utils.hooks.qt import add_qt6_dependencies


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
unused_plugins = {"qtvirtualkeyboardplugin.dll", "qpdf.dll"}
binaries = [(source, destination) for source, destination in binaries
            if Path(source).name.casefold() not in unused_plugins]
