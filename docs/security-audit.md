# Prüfung vor der GitHub-Veröffentlichung

Stand: 2. Oktober 2026. Geprüft wurde der gesamte lokale Projektordner, einschließlich
`.venv/`, `build/`, `dist/`, `test-artifacts/`, `tests/`, `assets/`, `configs/` und der
beiden XLSX-Dateien. Das erste Inventar umfasste ungefähr 11.000 Dateien und 1,36 GB;
Probe-Builds erzeugen anschließend weitere ignorierte Dateien.

## Zugangsdaten und persönliche Pfade

In den für Git vorgesehenen Dateien wurden keine echten Zugangsdaten, privaten
Schlüssel, API-Tokens oder persönlichen Windows-Benutzerpfade gefunden. Daher
mussten keine echten Zugangsdaten aus Programmcode entfernt werden.

| Fundstelle | Einordnung und Behandlung |
| --- | --- |
| `core/metadata.py`, Funktionen `load_credentials` / `save_credentials` | Zugangsdaten-Feldnamen und Windows Credential Manager-Aufrufe. Keine fest eingetragenen Accounts oder Schlüssel; keine Klartext-Zugangsdaten in `catalog.json`. |
| `tests/test_metadata.py:88–89`, `:98`, `:126`, `:206`, `:224`, `:300`, `:306`, `:308`, `:334` | Ausdrückliche synthetische Account-/Tokenwerte für einen im Test definierten Fake-Vault und Fake-HTTP-Antworten. Es findet keine Anmeldung mit diesen Werten statt. Tests prüfen außerdem, dass solche Werte weder in Cache noch Logs gelangen. |
| `tests/test_metadata_ui.py:86–97` | Synthetische Eingaben für einen gemockten Zugangsdatenservice. Keine echten Accounts. |
| `tests/test_metadata.py:71`, `:268`; `tests/test_security_archives.py:26` | Künstliche URL-Zugangsdaten, mit denen fehlendes Caching bzw. die Ablehnung unsicherer URLs geprüft werden. Keine verwendbaren Konten. |
| `.venv/pyvenv.cfg:1`, `:4`, `:5` | Lokale Interpreterpfade, redigiert etwa `C:\Users\<Benutzername>\…`. Die vollständige Entwicklungsumgebung ist ignoriert und wird nicht veröffentlicht. |
| `.venv/Lib/site-packages/PySide6/support/__pycache__/…` | Herstellerseitige kompilierte Dateipfade. Python-Bytecode und Entwicklungsumgebung sind ausgeschlossen. |
| `.venv/Lib/site-packages/Cryptodome/SelfTest/…` | Mitgelieferte öffentliche Kryptografie-Testvektoren enthalten absichtlich PEM-Privatschlüsselmuster; keine Projektzugangsdaten. Die Umgebung und ihre Testvektoren gehören nicht ins Repository. |
| Lokale `settings.json`, `installed.json`, `library.json` und `hub.log` unter `test-artifacts/` | Lokale Spiel-, Profil- und Installationspfade bzw. Test-Hardwaredaten. Vollständig ignoriert; nicht in Beispiele oder Dokumentation übernommen. |

`settings.example.json` enthält ausschließlich leere Listen/Zuordnungen und
ungefährliche Standardeinstellungen. Benutzer tragen Accounts über die Oberfläche
ein; Zugangsdaten werden nicht in die Beispieldatei eingetragen.

Der Windows Credential Manager außerhalb des Projekts wurde für diese Prüfung
nicht gelesen. Keine lokalen Benutzerdaten wurden gelöscht oder verschoben.

## Emulatoren, Spiele und Firmware

**Im lokalen Projektordner liegen tatsächlich heruntergeladene Emulatoren.** Sie
sind Überreste früherer ausdrücklich ausgeführter Downloadtests und werden durch
`test-artifacts/` komplett vom Repository ausgeschlossen:

- `test-artifacts/live-data/emulators/mesen/Mesen.exe`
- `test-artifacts/live-data/emulators/bsnes/bsnes_v115-windows/bsnes.exe`
- `test-artifacts/live-data/emulators/sameboy/sameboy.exe`
- `test-artifacts/live-data/emulators/azahar/azahar-windows-mxe-2126.1.2/azahar.exe`
- `test-artifacts/live-data/emulators/cemu/Cemu_2.6/Cemu.exe`
- `test-artifacts/live-data/emulators/ppsspp/PPSSPPWindows64.exe`
- `test-artifacts/live-data/emulators/xemu/xemu.exe`

Die Herkunft ist durch den bestehenden optionalen Downloadtest
`tools/verify_live.py`, seine lokalen Logs und `test-artifacts/live-data/installed.json`
mit Release-Versionen und Archiv-Prüfsummen nachvollziehbar. Zugehörige DLLs,
Übersetzungen, Texturen und Konfigurationen bleiben ebenfalls ausgeschlossen.

Weitere auffällige Fundstellen:

| Fundstelle | Inhalt / Einordnung |
| --- | --- |
| `test-artifacts/live-data/emulators/sameboy/{agb,cgb0,cgb,dmg,mgb,sgb2,sgb}_boot.bin` | Sieben Boot-ROM-Dateien aus dem vorhandenen SameBoy-Download, 256 oder 2.304 Bytes. Sie sind als Firmware-Fundstellen gemeldet und ausgeschlossen. Die Prüfung behauptet keine Herkunft aus einem Hersteller-BIOS und führt keine BIOS-Downloads aus. |
| `test-artifacts/live-data/emulators/ppsspp/assets/shaders/smiley_16x16_rgba.bin` | 1.024-Byte-Shader-/Bildressource der Emulatorinstallation, ebenfalls ausgeschlossen. |
| `.venv/Lib/site-packages/PySide6/resources/v8_context_snapshot*.bin` | Qt-WebEngine/V8-Ressourcen der Entwicklungsabhängigkeit, keine Spiel-Dateien; ausgeschlossen. |
| `test-artifacts/covers-preview-data/Eigene Spiele/{Abenteuer (Europe).nes,Waldwanderung.sfc,Wolkenflug.gba}` | Je 37 Bytes identischer lesbarer Testtext. SHA-256: `8a7283f6f06bde5975605fa90728777cf873555b364a4501469ab54cd35d2185`. Inhalt geprüft: synthetische UI-Testdateien, keine Spiele. Trotz Spieleendung vollständig ausgeschlossen. |
| `test-artifacts/phase2-ui/spiele-test/{Handheld-Test.gb,Mehrdeutig.iso,UI-Test.nes}` | Je 45 Bytes identischer lesbarer Testtext. SHA-256: `f1e8aa093547cd958c6be863ec9ee60c011f4cbde76cf160e98b8fb78a6e553e`. Inhalt geprüft: synthetische Metadaten-Testdateien, keine Spiele; ausgeschlossen. |
| `test-artifacts/exe-portable-v2-…/{original,moved}/data/emulators/mesen/Mesen.exe` | Je 157 Bytes, künstlicher PE-Header plus Testmarker; kein ausführbarer Emulator. SHA-256: `8f5d73619873786551563f6e51e9d09e748227b2d8eb4a2366935f5426ef4b28`. Entspricht dem Muster des bestehenden Testhelfers; ausgeschlossen. |
| `test-artifacts/phase3-ui/Eigener melonDS/melonDS.exe` | 139-Byte-Testheader aus `tests/helpers.py:windows_executable`, kein ausführbarer Emulator. SHA-256: `c557d8f0161f73b35e21169661993fc663d1ceeb0766faa8bb563a6db1fad188`; ausgeschlossen. |
| `test-artifacts/phase3-ui/Sicherungen/melonds-20261001-211440-329634.zip` | ZIP inklusive Manifest und Dateiliste geprüft: `melonDS.toml` mit 51 Bytes künstlichem Einstellungs-Testtext. Kein ROM oder BIOS im Archiv; ausgeschlossen. |
| `build/EmulatorHub/base_library.zip` | Erzeugte Python-Standardbibliothek, inklusive Archiv-Dateiliste gelesen; ausgeschlossen. |
| `dist/`, portable EXE-Kopien unter `test-artifacts/` | Gebaute Versionen des Emulator Hub und dessen Abhängigkeiten, keine mitgelieferten Emulatorinstallationen. Build-Ausgaben gehören nur in Releases. |
| `test-artifacts/release-tools/` | Lokales Inno-Setup-Buildwerkzeug. Kein Emulator; vollständig ausgeschlossen. |

Tests erzeugen kleine Dummy-Dateien, Archive und PE-Header in temporären
Testordnern. Im veröffentlichten `tests/` liegen Python-Quellen; es werden keine
echten ROMs, BIOS-Dateien, Spiele oder Emulator-Binaries eingecheckt.

## Tabellen und Assets

Beide Tabellen unter `docs/` wurden einschließlich ZIP-XML, Zelltexten, Kommentaren,
Hyperlinks und Dokumenteigenschaften gelesen. Die Metadaten nennen `openpyxl`
bzw. `Microsoft Excel Compatible / Openpyxl 3.1.5`; keine persönlichen Autoren
oder Benutzerpfade. Verweise betreffen Emulator-Projekt-/Release-Seiten; es wurden
keine ROM-, BIOS- oder Firmware-Downloadlinks gefunden.

In `assets/` liegen die Grafikdateien `logo.svg`, `logo.png` und `icon.ico` sowie
eine `README.md` mit ihrer Herkunft und Lizenz. SVG-Code
und gerendertes PNG wurden gelesen bzw. visuell geprüft: ein eigenständiges
mintgrünes Controller-Piktogramm auf dunklem abgerundetem Quadrat, ohne Namen,
Firmenlogos oder Figuren. PNG und ICO entstehen aus diesem SVG durch
`tools/make_icons.py`; die Herkunft ist die ursprüngliche Erstellung im Projekt.
Es wurden keine fremden Markenbilder übernommen. Das ersetzt keine juristische
Prüfung eines später ausgetauschten Logos.

## Wiederholbare Prüfung und Grenzen

```powershell
python tools/audit_publication.py --check --report test-artifacts/publication-audit.json
```

Der Helfer inventarisiert auch ignorierte Dateien, liest Text/Bytecode und
ZIP-/XLSX-Mitglieder, meldet Risiken mit Dateipfad und Zeile und gibt keine
Zugangsdatenwerte aus. Die Git-Kandidaten werden mit Git selbst und der aktuellen
`.gitignore` ausgewertet, ohne ein Repository im Projekt anzulegen. `--check`
endet mit Fehlercode 1 bei ungeklärten Risiken in diesen Kandidaten. Der ausführliche
redigierte Bericht liegt lokal unter `test-artifacts/`; die geplante Dateiliste
steht in [repository-files.txt](repository-files.txt).

Die Suche ist heuristisch, keine Garantie für die Abwesenheit jedes denkbaren
Geheimnisses. Komprimierte EXE-Inhalte, unbekannte Archivformate und Dateien
oberhalb der dokumentierten Leselimits benötigen eine gesonderte Prüfung; solche
Grenzen werden im Bericht gemeldet. Die Veröffentlichung enthält keine dieser
lokalen ausführbaren Emulator-/Spiele-/Firmware-Dateien. `.gitignore` schützt nur
unverfolgte Dateien: bereits eingecheckte oder mit `git add -f` hinzugefügte Daten
müssen zusätzlich im Git-Verlauf geprüft werden.
