# Drittanbieter-Software und Lizenzen

Stand: **02.10.2026**. Grundlage sind `requirements.txt`, `requirements.lock.txt` und die Lizenzmetadaten/-dateien der tatsächlich verwendeten Windows-Pakete. Die Projekt-[MIT-Lizenz](LICENSE) gilt für den eigenen Code und das eigene Logo; sie ersetzt keine Lizenz der folgenden Komponenten. Copyrights verbleiben bei deren jeweiligen Autoren. Der Build gibt verfügbare vollständige LICENSE-, COPYING-, NOTICE- und Copyright-Dateien sowie die Python-Lizenz und ergänzende Texte unter `_internal/licenses/` mit.

**Es werden keine Emulatoren mitgeliefert.** Vom Benutzer separat heruntergeladene Emulatoren unterliegen ihren eigenen Lizenzen und Installationsbedingungen. ROMs, Spiele, BIOS-/Firmware-Dateien und fremde Cover gehören weder ins Repository noch in die Release-Pakete. Dienstinhalte aus IGDB/ScreenScraper sind nicht durch die MIT-Lizenz des Projekts freigegeben.

## Direkte Abhängigkeiten

| Paket | Getestete Version | Lizenz | Primärquelle |
| --- | --- | --- | --- |
| PySide6 | 6.11.2 | LGPL-3.0 / GPL-2.0 / GPL-3.0; kommerzielle Alternative. Für die hier genutzten Community-Komponenten wird die LGPLv3-Option verwendet; siehe unten. | [Qt for Python](https://doc.qt.io/qtforpython-6/) / [Lizenzmetadaten](https://pypi.org/project/PySide6/6.11.2/) |
| Pillow | 12.3.0 | MIT-CMU, einschließlich ursprünglicher PIL-Copyrights; native Bildbibliotheken haben eigene Hinweise im Wheel. | [Original-Lizenz](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| keyring | 25.7.0 | MIT | [Projekt und Lizenz](https://github.com/jaraco/keyring) |
| requests | 2.34.2 | Apache-2.0 | [LICENSE](https://github.com/psf/requests/blob/main/LICENSE) |
| py7zr | 1.1.3 | LGPL-2.1-or-later | [LICENSE](https://github.com/miurahr/py7zr/blob/master/LICENSE) |
| packaging | 26.3 | Apache-2.0 **oder** BSD-2-Clause | [LICENSE](https://github.com/pypa/packaging/blob/main/LICENSE) |
| psutil | 7.2.2 | BSD-3-Clause | [LICENSE](https://github.com/giampaolo/psutil/blob/master/LICENSE) |
| PyYAML | 6.0.3 | MIT; eingebundenes LibYAML hat eigene MIT-Copyrights. | [LICENSE](https://github.com/yaml/pyyaml/blob/main/LICENSE) |
| openpyxl | 3.1.5 | MIT/Expat; nur Excel-Import, kein Laufzeitbedarf der Desktop-Anwendung. | [Offizielle Dokumentation](https://openpyxl.readthedocs.io/en/stable/) / [Original-Volltext](docs/licenses/openpyxl-3.1.5-MIT.txt) |
| PyInstaller | 6.22.3 | GPL-2.0-or-later **mit Bootloader-Ausnahme**; Buildwerkzeug. Diese Ausnahme gestattet das Einbetten und Verteilen des Bootloaders in Anwendungen unter anderen Lizenzen. | [COPYING und Ausnahme](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt) |

Python 3.12 wird als Laufzeit eingebunden und unter der **PSF License Version 2**, mit zusätzlichen historischen und Standardbibliothek-Hinweisen, verteilt. [Python-Lizenzübersicht](https://docs.python.org/3.12/license.html). Windows-XInput wird aus vorhandenen Windows-Systembibliotheken geladen; Windows-DLLs werden dafür nicht mitgeliefert.

## PySide6, Shiboken und Qt

PySide6, PySide6_Essentials, PySide6_Addons und Shiboken6 **6.11.2** enthalten Python-Bindings und Qt-Komponenten. Qt und Qt for Python bieten Community-Lizenzen (LGPL/GPL) sowie kommerzielle Lizenzen an. **Nicht jedes Qt-Modul ist unter LGPL erhältlich.** Der Hub verwendet Core, Gui, Widgets und Svg sowie für Tests QtTest; benötigte DLLs und Plugins können zusätzlich etwa Network oder OpenGL einbinden. Die Verteilung erfolgt mit dynamischen Bibliotheken im PyInstaller-Ordner-Modus. Nicht benötigte GPL-exklusive Module wie QtVirtualKeyboard werden beim Build ausgeschlossen. Eine kommerzielle Lizenz wird mit diesem Projekt nicht erteilt. [Qt-Lizenzübersicht](https://doc.qt.io/qt-6/licensing.html), [Qt-LGPL-Pflichten](https://www.qt.io/development/open-source-lgpl-obligations).

Die Volltexte [LGPLv3](docs/licenses/LGPL-3.0.txt) und [GPLv3](docs/licenses/GPL-3.0.txt) werden mitgegeben; LGPLv3 ergänzt die GPLv3. Die Copyrights liegen bei The Qt Company Ltd. und weiteren Qt-/PySide-Mitwirkenden. Zusätzliche in Qt enthaltene Drittanbieter-Komponenten bleiben ihren jeweiligen Lizenzen unterworfen; maßgeblich sind die [Qt-Drittanbieter-Hinweise](https://doc.qt.io/qt-6/licenses-used-in-qt.html) und der zugehörige Quellbaum. Neue Module oder zusätzliche Plugins vor dem Verteilen erneut prüfen.

Benutzer dürfen kompatible geänderte LGPL-Bibliotheken verwenden, dynamische DLLs/PYD-Dateien unter `_internal/PySide6` bzw. `_internal/shiboken6` austauschen oder das offene Projekt mit angepassten Abhängigkeiten erneut bauen. ABI und 64-Bit-Architektur müssen passen. Reverse Engineering zur Fehlersuche an geänderten LGPL-Komponenten wird nicht untersagt. Quellcode und Buildanleitung der Anwendung sind im Projekt verfügbar; [Entwicklungsanleitung](docs/development.md). An den Drittanbieter-Bibliotheken wurden keine eigenen Änderungen vorgenommen.

Die entsprechenden Originalquellen sind kostenlos über die offiziellen Archive erreichbar: [Qt 6.11.2](https://download.qt.io/archive/qt/6.11/6.11.2/), [Qt for Python / Shiboken 6.11.2](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.2-src/) und [Qt-for-Python-Quellbaum](https://code.qt.io/cgit/pyside/pyside-setup.git/?h=6.11.2). Die genauen mitgelieferten Versionen stehen im Lockfile und den eingebundenen Paketmetadaten. Bei einer Aktualisierung oder Änderung müssen diese Quellbezüge und alle Lizenztexte mit aktualisiert werden.

## Indirekte und Build-Abhängigkeiten aus dem Lockfile

Die folgende Liste umfasst zusätzlich alle übrigen Einträge des derzeitigen Lockfiles. Sie beschreibt auch reine Build-/Import-Abhängigkeiten, die nicht zwingend in jedem fertigen Paket enthalten sind. Die tatsächlich eingebundenen Paketversionen und Original-Copyrights stehen in den mitgelieferten Metadaten und Lizenzdateien.

| Paket | Version | Lizenz | Originalprojekt / Quellen |
| --- | --- | --- | --- |
| altgraph | 0.17.5 | MIT | [altgraph](https://github.com/ronaldoussoren/altgraph) |
| backports.zstd | 1.7.0 | PSF-2.0; enthaltenes Zstandard: BSD-3-Clause oder GPL-2.0 | [backports.zstd](https://github.com/rogdham/backports.zstd) / [Zstandard](https://github.com/facebook/zstd) |
| brotli | 1.2.0 | MIT | [Brotli](https://github.com/google/brotli) |
| certifi | 2026.7.22 | MPL-2.0 | [certifi](https://github.com/certifi/python-certifi) |
| charset-normalizer | 3.5.2 | MIT | [charset-normalizer](https://github.com/jawah/charset_normalizer) |
| et_xmlfile | 2.0.0 | MIT; übernommene Python-Komponenten: PSF-Lizenz | [et_xmlfile](https://foss.heptapod.net/openpyxl/et_xmlfile) / [Lizenzvolltexte](docs/licenses/README.md) |
| idna | 3.20 | BSD-3-Clause | [idna](https://github.com/kjd/idna) |
| inflate64 | 1.0.4 | LGPL-2.1-or-later | [inflate64](https://github.com/miurahr/inflate64) |
| jaraco.classes | 3.4.0 | MIT | [jaraco.classes](https://github.com/jaraco/jaraco.classes) |
| jaraco.context | 6.1.2 | MIT | [jaraco.context](https://github.com/jaraco/jaraco.context) |
| jaraco.functools | 4.6.0 | MIT | [jaraco.functools](https://github.com/jaraco/jaraco.functools) |
| more-itertools | 11.1.0 | MIT | [more-itertools](https://github.com/more-itertools/more-itertools) |
| multivolumefile | 0.2.3 | LGPL-2.1-or-later | [multivolumefile](https://github.com/miurahr/multivolume) |
| pefile | 2024.8.26 | MIT | [pefile](https://github.com/erocarrera/pefile) |
| pybcj | 1.0.8 | LGPL-2.1-or-later | [pybcj](https://github.com/miurahr/pybcj) |
| pycryptodomex | 3.23.0 | BSD-2-Clause für neuere Teile; ältere Teile Public Domain. Der vollständige LICENSE.rst-Text bleibt maßgeblich. | [PyCryptodome-Lizenzen](https://www.pycryptodome.org/src/license) |
| pyinstaller-hooks-contrib | 2026.8 | Standard-Build-Hooks: GPL-2.0-or-later; eingebundene Runtime-Hooks: Apache-2.0. | [Original LICENSE](https://github.com/pyinstaller/pyinstaller-hooks-contrib/blob/master/LICENSE) |
| pyppmd | 1.3.1 | LGPL-2.1-or-later | [pyppmd](https://github.com/miurahr/pyppmd) |
| PySide6_Addons | 6.11.2 | LGPL-/GPL-/kommerzielle Alternativen, abhängig vom Modul; siehe Qt-Abschnitt. | [Qt for Python](https://doc.qt.io/qtforpython-6/) |
| PySide6_Essentials | 6.11.2 | LGPL-/GPL-/kommerzielle Alternativen; siehe Qt-Abschnitt. | [Qt for Python](https://doc.qt.io/qtforpython-6/) |
| pywin32-ctypes | 0.2.3 | BSD-3-Clause | [pywin32-ctypes](https://github.com/enthought/pywin32-ctypes) |
| setuptools | 84.0.0 | MIT; eingebundene Vendor-Komponenten behalten ihre eigenen Lizenzen. | [setuptools](https://github.com/pypa/setuptools) |
| shiboken6 | 6.11.2 | LGPL-3.0 / GPL-2.0 / GPL-3.0 oder kommerziell | [Shiboken](https://doc.qt.io/qtforpython-6/shiboken6/) |
| texttable | 1.7.0 | MIT | [texttable](https://github.com/foutaise/texttable) |
| urllib3 | 2.8.0 | MIT | [urllib3](https://github.com/urllib3/urllib3) |

LGPL-2.1-or-later-Bibliotheken werden unverändert genutzt. Die Originalquellen zu den angegebenen Versionen sind außerdem als Source Distributions beim jeweiligen PyPI-Projekt unter **Download files** erhältlich, etwa [py7zr 1.1.3](https://pypi.org/project/py7zr/1.1.3/#files), [inflate64 1.0.4](https://pypi.org/project/inflate64/1.0.4/#files), [pybcj 1.0.8](https://pypi.org/project/pybcj/1.0.8/#files), [pyppmd 1.3.1](https://pypi.org/project/pyppmd/1.3.1/#files) und [multivolumefile 0.2.3](https://pypi.org/project/multivolumefile/0.2.3/#files). Das vollständige Projekt kann mit angepassten Versionen dieser Bibliotheken neu gebaut werden. Lizenz-/Copyright-Dateien aus nativen Bild-, Archiv- und Krypto-Abhängigkeiten müssen beim erneuten Verteilen erhalten bleiben.

## Native Laufzeitkomponenten

Python und Qt binden native Laufzeitbibliotheken ein, die nicht als eigene Python-Pakete im Lockfile erscheinen. Dazu zählen insbesondere OpenSSL (Apache-2.0 bei Version 3), libffi (MIT), zlib, Bild-/Schriftbibliotheken und Microsoft-C/C++-Laufzeiten. Die mitgegebene Python-LICENSE enthält zusätzliche Python-/OpenSSL-/Standardbibliothek-Hinweise; die entsprechenden Originalquellen stehen unter [CPython](https://www.python.org/downloads/source/), [OpenSSL](https://github.com/openssl/openssl) und [libffi](https://github.com/libffi/libffi). Für Microsoft-Runtime-Dateien gelten die [Microsoft-Weitergabebedingungen](https://learn.microsoft.com/en-us/cpp/windows/redistributing-visual-cpp-files).

Qt kann als `opengl32sw.dll` einen Mesa/LLVM-Software-Rasterizer mitliefern. Mesa verwendet überwiegend MIT und LLVM eigene permissive Lizenzbedingungen; die genaue Lizenz richtet sich nach dem konkreten Build. [Qt-Windows-Grafikhinweise](https://doc.qt.io/qt-6/windows-graphics.html), [Mesa-Lizenz](https://docs.mesa3d.org/license.html), [LLVM-Lizenz](https://llvm.org/docs/DeveloperPolicy.html#copyright-license-and-patents). Qt-Drittanbieter-Attributionen einschließlich Schrift- und Bildbibliotheken sind zusätzlich in [Qt-6.11.2-third-party.txt](docs/licenses/Qt-6.11.2-third-party.txt) gesammelt.

Pillow-Wheels können unter anderem libjpeg-turbo, libpng, libtiff, libwebp, OpenJPEG, FreeType und LittleCMS einbinden. Diese unterliegen eigenen permissiven Lizenz-/Copyright-Bedingungen (BSD-/MIT-/zlib-/FreeType-/IJG-Varianten), nicht pauschal MIT-CMU. [Pillow-Hinweise zu nativen Bibliotheken](https://pillow.readthedocs.io/en/stable/handbook/security.html). Bei Änderungen an Wheels oder nativen Bibliotheken die zugehörigen Originalhinweise mitführen; die Paket-LICENSE allein ist keine Freigabe fremder Komponenten.

Inno Setup ist ein separat benötigtes Buildwerkzeug und wird nicht als Compiler mitgeliefert. Für den Setup-Bootstrap gelten zusätzlich die [Inno-Setup-Lizenzbedingungen](https://jrsoftware.org/files/is/license.txt).
