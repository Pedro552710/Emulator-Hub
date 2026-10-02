# Entwicklung und Windows-Build

[Zur Startseite](../README.md) · [Handbuch](user-guide.md) · [Veröffentlichen](releasing.md)

## Umgebung

Windows 10/11 x64 und Python 3.12 x64. Abhängigkeiten mit den getesteten Versionen installieren:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe main.py
```

`requirements.txt` definiert unterstützte Versionsbereiche; `requirements.lock.txt` enthält direkte und indirekte Versionen für reproduzierbare Windows-Builds. Nach bewussten Updates Tests und Paket-Build erneut prüfen und Lizenzhinweise aktualisieren. Die virtuelle Umgebung muss für den Skript-Build unter `.venv` liegen.

## Tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
.\.venv\Scripts\python.exe main.py --smoke-test --data-dir test-artifacts\python-smoke-data --screenshot test-artifacts\python-smoke.png
.\.venv\Scripts\python.exe main.py --smoke-test --check-integrations --data-dir test-artifacts\integration-smoke-data
```

Die Tests verwenden künstliche Dateiinhalte, simulierte Netzantworten, eigene temporäre Konfigurationsdateien und native Qt-Komponenten. Es werden keine echten Spiele oder BIOS-Dateien benötigt. Der Integrationstest prüft die Verfügbarkeit des Windows-Zugangsdatenbackends und XInput; er meldet keine fremden Kontodaten an und startet keinen Emulator.

`tools/verify_live.py` ist ein gesonderter, optionaler Downloadtest: Er lädt reale Emulatoren aus ihren offiziellen Projektquellen in `test-artifacts/`. Er gehört **nicht** zu den CI-Offline-Tests. Seine Ausgaben und heruntergeladene Programme dürfen weder ins Repository noch in Release-Pakete aufgenommen werden. Historische Ergebnisse und Einschränkungen stehen unter [Verifikation](verification.md).

## Pakete bauen

```powershell
.\build.ps1
```

`EmulatorHub.spec` beschreibt ausdrücklich einen PyInstaller-**Ordner-Build**. Ergebnis: `dist\EmulatorHub\EmulatorHub.exe` samt `_internal`, Ressourcen und Lizenzdateien. Den gesamten Ordner weitergeben. Der Build erzeugt Icons erneut, prüft den Programmstart und packt `Output\EmulatorHub-<Version>-portable.zip` mit einer leeren `portable.flag`. Der Flag liegt nur in der ZIP-Stagingkopie, damit die Installer-Version ihren normalen Datenordner verwendet.

Mit dem offiziellen [Inno Setup](https://jrsoftware.org/isinfo.php) und verfügbarem `ISCC.exe` entsteht aus `installer/EmulatorHub.iss` außerdem `Output\EmulatorHub-Setup.exe`. Ohne Compiler bleibt der Ordner-Build und die ZIP erfolgreich; der fehlende Installer wird ausdrücklich gemeldet. Ein Compilerfehler bricht den Build mit Fehler ab. Eine pro Benutzer installierte Anwendung verwendet standardmäßig `%LOCALAPPDATA%\EmulatorHub` für ihre Daten. Die Deinstallation entfernt die installierten Programmdateien, nicht selbst bereitgestellte Spiel-Dateien.

`-RequireInstaller` verlangt einen erfolgreichen Installer-Build, etwa in CI. Mit `-IsccPath 'C:\Pfad\zu\ISCC.exe'` lässt sich ein abweichender Compilerpfad angeben; `-SkipSmokeTest` überspringt nur den EXE-Starttest. `Output\SHA256SUMS.txt` enthält die SHA-256-Prüfsummen der in diesem Lauf erzeugten Pakete. README, Handbuch und Lizenzdokumentation werden mitgeliefert. Der QtGui-Buildhook lässt ungenutzte VirtualKeyboard- und PDF-Plugins aus; die normalen Windows-, SVG- und offscreen-Plugins bleiben erhalten.

Während PyInstaller läuft, begrenzt das Skript `PATH` auf Python, die virtuelle Umgebung und Windows. Anschließend stellt es den ursprünglichen Wert wieder her. UCRT/API-Set-Kompatibilitätskopien werden nicht eingepackt; Windows 10/11 stellen diese Systemkomponenten bereits bereit. So gelangen beispielsweise keine Java-Laufzeitdateien aus dem lokalen `PATH` unbeabsichtigt in das Paket.

Versionsnummern werden ausschließlich in `core/version.py` geändert. Fenster, Installer, ZIP und Release-Tagprüfung verwenden diese Version. Die erste öffentliche Version heißt `1.0.0`; interne Entwicklungsnummern sind keine zusätzlichen öffentlichen Releases.

## Lizenzen und erneutes Bauen

Die MIT-Lizenz des Projekts hebt Drittanbieter-Lizenzen nicht auf. Der Build nimmt [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md), Projekt-LICENSE, Python-LICENSE, verfügbare Lizenz-/Copyright-/NOTICE-Dateien der installierten Distributionen und ergänzende Volltexte aus `docs/licenses/` mit. Sie liegen im fertigen Ordner unter `_internal/licenses/`.

Qt/PySide6 werden als dynamische Bibliotheken im Ordner-Modus verteilt. Kompatible eigene Bibliotheksversionen dürfen ausgetauscht werden. Alternativ das frei verfügbare Projekt mit einer angepassten Python-/PySide6-Umgebung neu bauen; es gibt keine Signatur- oder Lizenzprüfung, die diesen Austausch verhindern soll. Reverse Engineering zum Debuggen von Änderungen an LGPL-Bibliotheken wird nicht untersagt. Die verwendeten Versionen, Lizenzoptionen und Bezugsstellen der entsprechenden Bibliotheksquellen stehen in [THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## Katalog und Konfigurationen

Zur Laufzeit liest die Anwendung `catalog.json`; Excel ist nur eine dokumentierte Importquelle. Die Tabellen liegen unter `docs/emulatoren.xlsx` und `docs/emulatoren_mit_downloadanleitungen.xlsx`. Der Import verwendet das Blatt `Emulatoren` und die geprüften Ergänzungen in `tools/catalog_enrichment.json`:

```powershell
.\.venv\Scripts\python.exe tools\import_catalog.py
```

Der Import **ersetzt catalog.json**. Dauerhafte Änderungen deshalb auch in den Importergänzungen pflegen. Unbekannte Zeilen oder unbestätigte Quellen müssen zuerst ausdrücklich geprüft werden. Weitere Felder erklärt [new_catalog_fields.md](new_catalog_fields.md).

`configs/system_requirements.json` enthält grobe CPU-/RAM-/GPU-Schwellen. `configs/extensions.json` enthält eindeutige oder mehrdeutige Endungszuordnungen. Die Anwendung kopiert Standards bei der ersten Einrichtung in den Datenordner; lokale Anpassungen werden nicht ersetzt. `settings.example.json` enthält ausschließlich leere, nicht persönliche Beispielwerte und wird nicht automatisch als Laufzeitkonfiguration geladen. Cover-Zugangsdaten werden ausschließlich über die Oberfläche im Windows-Anmeldeinformationsmanager gespeichert, niemals in dieser Beispiel-Datei.

## Struktur

| Pfad | Aufgabe |
| --- | --- |
| `main.py`, `core/`, `ui/` | Programmstart, Fachlogik, native Qt-Oberfläche |
| `core/version.py` | Zentrale öffentliche Programmversion |
| `catalog.json`, `configs/` | Emulator-Katalog und anpassbare Standards |
| `assets/`, `tools/make_icons.py` | Eigenes SVG, PNG und mehrstufiges Windows-Icon |
| `tools/import_catalog.py`, `tools/catalog_enrichment.json` | Reproduzierbarer, geprüfter Excel-Import |
| `tests/` | Offline- und native Qt-Tests |
| `EmulatorHub.spec`, `build.ps1`, `installer/` | Ordner-Paket, portable ZIP und Inno-Installer |
| `.github/workflows/` | Windows-Tests und Tag-Releases |
| `docs/` | Handbuch, Konfigurationen, Quellen, Lizenztexte und Prüfergebnisse |

Benutzerdaten, `.venv`, `build`, `dist`, `Output`, Cache, Logs und `test-artifacts` bleiben durch `.gitignore` lokal. Cover, Screenshots mit privaten Pfaden, echte Emulatorpakete und persönliche Konfigurationsdateien nicht manuell hinzufügen.
