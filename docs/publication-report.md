# Vorbereitung der ersten GitHub-Veröffentlichung

Stand: 2. Oktober 2026. Öffentliche Version: **1.0.0**.

Die Programmfunktionen bleiben unverändert. Anwendungsversion und Fenstertitel
verwenden jetzt `core/version.py`; Katalog-Herkunftsangaben und Importpfade
berücksichtigen die nach `docs/` verschobenen Tabellen. Git wurde im Projekt
nicht initialisiert; es wurde nichts auf GitHub hochgeladen oder veröffentlicht.

## Geänderte Dateien

| Datei | Änderung |
| --- | --- |
| `.gitignore` | Entwicklungs-, Build-, Installer-, Laufzeit-, Spiele- und Binärdateien ausschließen; Spec veröffentlichen. |
| `build.ps1` | Ordner-Build, EXE-Starttest, Installer-Erkennung, portable ZIP, Lizenz-/Dokumentkopien und SHA-256. |
| `EmulatorHub.spec` | Onedir, zentrale Windows-Version, Ressourcen, eigene QtGui-Hookdatei und vollständige Lizenzpfade. |
| `main.py` | Anwendungsversion aus zentraler Stelle. |
| `ui/window.py` | Zentrale Version im Fenstertitel. |
| `catalog.json` | Nur `source_workbook` auf `docs/` geändert. |
| `tools/import_catalog.py` | Neuer Standardpfad und reproduzierbare relative Herkunftsangabe. |
| `tests/test_comfort_integration.py` | Neuer Tabellenpfad. |
| `README.md` | Übersichtliche Startseite; ausführliche Inhalte ins Handbuch verschoben. |
| `docs/catalog_sources.md` | Tabellenverweise angepasst. |
| `docs/verification.md` | Veröffentlichungstests ergänzen frühere Ergebnisse. |

## Neue Dateien

- `core/version.py`
- `installer/EmulatorHub.iss`
- `tools/pyinstaller_hooks/hook-PySide6.QtGui.py`
- `tools/audit_publication.py`
- `tests/test_publication_audit.py`
- `.github/workflows/tests.yml`
- `.github/workflows/release.yml`
- `.github/ISSUE_TEMPLATE/bug_report.yml`
- `LICENSE`
- `THIRD_PARTY_NOTICES.md`
- `CONTRIBUTING.md`
- `CHANGELOG.md`
- `settings.example.json`
- `assets/README.md`
- `docs/user-guide.md`
- `docs/development.md`
- `docs/releasing.md`
- `docs/security-audit.md`
- `docs/repository-files.txt`
- `docs/publication-report.md`
- `docs/licenses/README.md`
- `docs/licenses/LGPL-3.0.txt`
- `docs/licenses/GPL-3.0.txt`
- `docs/licenses/openpyxl-3.1.5-MIT.txt`
- `docs/licenses/et_xmlfile-2.0.0-MIT.txt`
- `docs/licenses/et_xmlfile-2.0.0-PSF.txt`
- `docs/licenses/Qt-6.11.2-third-party.txt`

Die bestehenden Abhängigkeiten und beide Standardkonfigurationen wurden nicht
geändert. PNG und ICO wurden beim Build erneut aus dem vorhandenen SVG erzeugt.

## Verschobene Dateien

- `emulatoren.xlsx` → `docs/emulatoren.xlsx`
- `emulatoren_mit_downloadanleitungen.xlsx` → `docs/emulatoren_mit_downloadanleitungen.xlsx`

Die Arbeitsmappen bleiben inhaltlich unverändert. Der Import reproduziert den
gesamten aktuellen Katalog; lediglich abschließende Zeilenumbrüche unterscheiden
sich bei byteweisem Vergleich.

## Sicherheitsbefunde

Keine echten Projekt-Zugangsdaten oder persönlichen Benutzerpfade in den
Git-Kandidaten gefunden. Es mussten keine echten Accounts aus Programmcode
entfernt werden. Beispiel-Einstellungen enthalten keine Zugangsdaten.

Persönliche Interpreterpfade sind in `.venv/pyvenv.cfg` vorhanden. Unter
`test-artifacts/live-data/emulators/` liegen sieben echte Emulatorinstallationen
und sieben SameBoy-Boot-ROM-Dateien. Synthetische Spiel-Testdateien und alte
Sicherungs-/Build-Ausgaben liegen ebenfalls lokal. Alles wird ausgeschlossen;
es wurden keine persönlichen Daten gelöscht. Die genauen redigierten Fundstellen
stehen in [security-audit.md](security-audit.md).

Die [Repository-Dateiliste](repository-files.txt) wird mit Git selbst gegen die
`.gitignore` geprüft. Sie umfasst nur Quellcode, Tests, Konfigurationen,
Dokumentation, geprüfte Tabellen und eigene Grafiken. Der vollständige lokale
Auditbericht bleibt unter `test-artifacts/publication-audit-final.json`.

## Durchgeführte Prüfungen

- 227 Tests aus einer sauberen Kopie der Git-Kandidaten bestanden (218 bestehende und 9 Veröffentlichungstests).
- Python-Fensterstart mit isolierten Daten, XInput- und Credential-Backendprüfung erfolgreich.
- Beide GitHub-Workflows mit Actionlint 1.7.12 geprüft, ohne Fehler.
- `pip check`, Python-/PowerShell-Syntax sowie Tabellenimport erfolgreich.
- Finaler PyInstaller-Ordner-Build und dessen EXE-Starttest erfolgreich.
- Portable ZIP entpackt und ohne `--data-dir` gestartet: `data/settings.json` entsteht relativ neben der EXE.
- Installer mit Inno Setup 6 gebaut; zusätzliche Kompilierung mit Inno Setup 7.1 erfolgreich.
- Installer in einem isolierten Testordner installiert, Programm gestartet und deinstalliert. Eigene synthetische Daten blieben erhalten; die Testregistrierung wurde entfernt.
- Beim Installertest wurden Verknüpfungen mit `/NOICONS` ausgelassen, um bestehende Benutzerverknüpfungen zu schützen.

Der finale Paketinhalt wird zusätzlich auf Ressourcen, Versionen, Lizenztexte,
ausgeschlossene Nutzerdaten und Prüfsummen geprüft. Unbenutzte VirtualKeyboard-
und PDF-Plugins werden vor der Abhängigkeitsanalyse ausgeschlossen; normale
Windows-, offscreen- und SVG-Plugins bleiben erhalten. Gleichnamige Lizenztexte
werden durch ihre ursprünglichen Unterordner voneinander getrennt.

Die Build-Umgebung begrenzt `PATH` auf Python und Windows. Unnötige UCRT/API-Set-
Kopien aus der lokalen Java-Installation wurden aus den Paketen entfernt;
Windows 10/11 stellen diese Systemkomponenten selbst bereit. Auch nach dieser
Bereinigung wurden die finale ZIP und der finale Installer erneut gestartet.

Die vollständige Dateiliste enthält 111 geplante Repository-Dateien. Eine saubere
Checkout-Simulation prüfte außerdem beide Tabellen, den Programmstart und den
Audit ohne übernommene Entwicklungsumgebung oder Build-Ausgaben; sie meldete
keine ungeklärten Veröffentlichungshindernisse.

## Ausgaben und verbleibende manuelle Schritte

- `dist/EmulatorHub/EmulatorHub.exe` samt vollständigem Programmordner.
- `Output/EmulatorHub-Setup.exe`
- `Output/EmulatorHub-1.0.0-portable.zip`
- `Output/SHA256SUMS.txt`

Der tatsächliche GitHub-Actions-Lauf und das automatische Release lassen sich
erst nach einem Push prüfen. Startmenü-/Desktop-Verknüpfungen und SmartScreen
wurden beim isolierten Installertest nicht interaktiv geprüft. Windows 10 wurde
nicht separat getestet; die lokalen Prüfungen liefen unter Windows 11 x64.
Die Pakete sind unsigniert. Keine neuen Live-Emulator-, Spiele- oder BIOS-Downloads
wurden für diese Vorbereitung ausgeführt.

Vor dem Commit den Platzhalter `[DEIN NAME]` in `LICENSE` ersetzen und für Pakete
mit dem endgültigen Copyright erneut bauen. Ein leeres GitHub-Repository selbst
anlegen, Git-Dateiliste prüfen, committen, pushen und `v1.0.0` taggen. Die genauen
Befehle stehen in [releasing.md](releasing.md).
