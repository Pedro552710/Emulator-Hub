# Katalogquellen und Installationsentscheidungen

Geprüft am **01.10.2026**. Datengrundlage: [emulatoren_mit_downloadanleitungen.xlsx](emulatoren_mit_downloadanleitungen.xlsx), Blatt `Emulatoren`, Zeilen 2–23; die ursprüngliche Tabelle liegt ebenfalls unter [emulatoren.xlsx](emulatoren.xlsx). Alle 22 Konsolenzeilen bleiben erhalten, einschließlich der kombinierten Alternativen. Nintendo 64 verwendet Mupen64Plus als Standard. Originalbezeichnung, Quellenbeschreibung und Zeilennummer stehen als Herkunftsangaben im JSON; alte Rechtshinweise wurden durch den geforderten Satz und sachliche Installationshinweise ersetzt.

## Automatisch installierbare Windows-x64-Pakete

Für jeden Eintrag wurden der offizielle stabile GitHub-Release, die eindeutige Asset-Auswahl sowie das tatsächlich heruntergeladene ZIP geprüft. Die enthaltene Startdatei hat jeweils die PE-Architektur `0x8664` (x64). Ein untergeordneter Archivordner wird berücksichtigt. Die Anwendung fragt bei jeder Installation den aktuellen stabilen Release erneut ab; die hier genannten Versionen sind der Recherchezeitpunkt.

| Eintrag | Offizieller Release | Geprüftes Windows-Asset | Startdatei | SHA-256 der offiziellen API |
| --- | --- | --- | --- | --- |
| Mesen / MesenCE | [2.2.1](https://github.com/nesdev-org/MesenCE/releases/tag/2.2.1) | `Mesen_2.2.1_Windows.zip` | `Mesen.exe` | vorhanden, geprüft |
| bsnes | [v115](https://github.com/bsnes-emu/bsnes/releases/tag/v115) | `bsnes_v115-windows.zip` | `bsnes.exe` | nicht angeboten |
| SameBoy | [v1.0.3](https://github.com/LIJI32/SameBoy/releases/tag/v1.0.3) | `sameboy_winsdl_v1.0.3.zip` | `sameboy.exe` | vorhanden, geprüft |
| melonDS | [1.1](https://github.com/melonDS-emu/melonDS/releases/tag/1.1) | `melonDS-1.1-windows-x86_64.zip` | `melonDS.exe` | vorhanden, geprüft |
| Azahar | [2126.1.2](https://github.com/azahar-emu/azahar/releases/tag/2126.1.2) | `azahar-windows-mxe-2126.1.2.zip` | `azahar.exe` | vorhanden, geprüft |
| Cemu | [v2.6](https://github.com/cemu-project/Cemu/releases/tag/v2.6) | `cemu-2.6-windows-x64.zip` | `Cemu.exe` | nicht angeboten |
| PPSSPP | [v1.20.4](https://github.com/hrydgard/ppsspp/releases/tag/v1.20.4) | `PPSSPP-v1.20.4-Windows-x64.zip` | `PPSSPPWindows64.exe` | vorhanden, geprüft |
| Flycast | [v2.7](https://github.com/flyinghead/flycast/releases/tag/v2.7) | `flycast-win64-2.7.zip` | `flycast.exe` | vorhanden, geprüft |
| xemu | [v0.8.136](https://github.com/xemu-project/xemu/releases/tag/v0.8.136) | `xemu-0.8.136-windows-x86_64.zip` | `xemu.exe` | vorhanden, geprüft |

Die API-Abfrage erfolgt jeweils über `https://api.github.com/repos/<github_repo>/releases/latest`. `verified_asset_sha256` im Katalog dokumentiert ausschließlich die damals **offiziell angebotene** Prüfsumme; fehlende Prüfsummen bleiben `null`. Der aktuelle Download wird gegen die Prüfsumme des aktuell aufgelösten Assets geprüft, nicht gegen eine alte Katalog-Prüfsumme. Für bsnes und Cemu wurde kein offizieller SHA-256-Wert erfunden.

Die verankerten Dateinamenmuster in `catalog.json` schließen ARM64-, Debug-, Symbol-, Quellcode- und andere Betriebssystempakete aus. Bei xemu wird die versionierte Datei gewählt, weil im selben Release auch eine identische Alias-Datei angeboten wird. Bei Azahar wird das eigenständige MXE-Paket gewählt; `tests.exe`, `azahar-room.exe` und die Libretro-Pakete sind keine Hub-Startdateien. Bei SNES installiert der automatische Button **bsnes**; Snes9x bleibt die in der Excel-Zeile genannte manuelle Alternative.

### Mesen und zusätzliche Laufzeitumgebungen

Die [offizielle Mesen-Seite](https://www.mesen.ca/) verweist auf `nesdev-org/MesenCE`, nicht mehr auf den älteren Entwicklungsstand in `SourMesen/Mesen2`. Der [Release 2.2.1](https://github.com/nesdev-org/MesenCE/releases/tag/2.2.1) nennt für Windows keine zusätzliche Laufzeitinstallation. Der [Build am Release-Tag](https://github.com/nesdev-org/MesenCE/blob/2.2.1/.github/workflows/build.yml) erzeugt einen nativen AoT-Build mit `SelfContained=true`.

Das geprüfte Windows-ZIP enthält nur `Mesen.exe`. Der PE-CLR-Verzeichniseintrag ist `(0, 0)`: Die Startdatei ist nativ kompiliert und benötigt keine extern installierte .NET-Laufzeit. Ihre importierten Bibliotheken sind Windows-Systembibliotheken und die unter Windows 10/11 vorhandene Universal C Runtime; keine externe `vcruntime140.dll` oder `msvcp140.dll` wurde als Import gefunden. Daher bleibt die Windows-10+-Version automatisch installierbar. Diese Prüfung bezieht sich auf das konkrete Release-Paket und ersetzt keine neue Prüfung nach einer späteren Änderung des Paketformats.

## Manuelle Einträge und Gründe

| Konsolenzeile / Emulator | Offizielle Quelle | Entscheidung |
| --- | --- | --- |
| Game Boy Advance / mGBA | [mGBA Downloads](https://mgba.io/downloads.html) | Das tatsächlich geprüfte stabile Win64-7z `mGBA-0.10.5-win64.7z` verwendet den BCJ2-Filter. `py7zr 1.1.3` kann es nicht entpacken (`UnsupportedCompressionMethodError`). Die Anleitung nennt ein geeignetes Entpackprogramm bzw. den offiziellen Installer. |
| Nintendo 64 / Mupen64Plus | [Projektseite](https://www.mupen64plus.org/), [2.6.0](https://github.com/mupen64plus/mupen64plus-core/releases/tag/2.6.0) | Plugin-/Kommandozeilen-System; Startargumente und mögliche Frontends müssen bewusst eingerichtet werden. [Simple64](https://github.com/simple64/simple64) ist seit 14.02.2025 archiviert und wird nicht als Standard angeboten. |
| GameCube / Wii / Dolphin | [Downloads](https://dolphin-emu.org/download/?lang=en) | Die offiziellen Windows-Releases verlangen die Visual-C++-Runtime. Aktuelle Dateien und Voraussetzungen werden über die offizielle Anleitung gewählt; kein geratenes dynamisches Muster. |
| PlayStation 1 / DuckStation | [Projektseite](https://www.duckstation.org/), [Releases](https://github.com/stenzek/duckstation/releases) | Veränderlicher `latest`-Build-Kanal und Installer-/portable Auswahl. Ein als stabil behaupteter versionierter Updateweg wurde nicht unterstellt. |
| PlayStation 2 / PCSX2 | [Downloads](https://pcsx2.net/downloads/), [stabile Releases](https://github.com/PCSX2/pcsx2/releases) | Windows-7z bzw. Installer, zusätzliche Setup-/Runtime-Voraussetzungen; vollständig startfertige automatische Einrichtung auf einem sauberen System nicht bestätigt. |
| PlayStation 3 / RPCS3 | [Downloads](https://rpcs3.net/download) | Dynamische fortlaufende Build-Pakete und Prüfsummen auf der Seite; kein verifizierter stabiler API-Resolver. Der Rechercheabruf wurde mit HTTP 403 abgewiesen. Deshalb kein Direktlink geraten; manuelle SHA-256-Anleitung. |
| PS Vita / Vita3K | [Downloads](https://vita3k.org/download.html) | Die offizielle Seite bietet ausdrücklich Nightlies. Bewusste manuelle Build-Auswahl. |
| Master System / Mega Drive / BlastEm und Genesis Plus GX | [BlastEm Downloads](https://www.retrodev.com/blastem/downloads.html), [Genesis Plus GX](https://github.com/ekeeke/Genesis-Plus-GX), [RetroArch](https://www.retroarch.com/) | Kombinierte Tabellenzeile: BlastEm ist ein Programm, Genesis Plus GX ein Frontend-Core. Die Anleitung nennt beide getrennten Wege und den RetroArch-Core-Downloader. Der alte `rhope.retrodev.com`-Tabellenlink antwortete mit HTTP 502; die offizielle aktuelle BlastEm-Adresse wurde korrigiert. |
| Saturn / Mednafen und Yaba Sanshiro | [Mednafen Releases](https://mednafen.github.io/releases/), [Yaba Sanshiro](https://www.yabasanshiro.com/download) | Mednafen ist kommandozeilenorientiert; die Android-Alternative aus der Tabelle ist kein Windows-Programm. |
| Xbox 360 / Xenia Canary | [offizielle Canary-Releases](https://github.com/xenia-canary/xenia-canary/releases), [offizieller Quellenverweis](https://xenia.jp/download/) | Ausschließlich der verlinkte offizielle Canary-Kanal. Die aktuell angebotenen experimentellen Builds erhalten keine angebliche stabile Versionsprüfung. |
| Atari 2600 / Stella | [Downloads](https://stella-emu.github.io/downloads.html) | Offizielles x64-ZIP und `Stella.exe` bestätigt. Die Seite verlangt gegebenenfalls eine zusätzliche manuelle Visual-C++-Runtime; daher Anleitung. |
| PC Engine / TurboGrafx / Mednafen | [Releases](https://mednafen.github.io/releases/) | Derselbe Download wie Saturn; kommandozeilenorientiert. Eine vorhandene Installation kann für beide Konsolen registriert werden. |
| Neo Geo / Arcade / FinalBurn Neo und MAME | [FinalBurn Neo](https://github.com/finalburnneo/FBNeo/releases), [MAME Release](https://www.mamedev.org/release.html) | FinalBurn Neos aktueller Kanal bezeichnet sich als Nightly, auch wenn die API ihn nicht überall als prerelease markiert. MAME bleibt eine bewusst gewählte Alternative. Keine stabilen Asset-Muster oder Spiegel-URLs geraten. |

`todo`-Felder dokumentieren noch nicht verlässlich automatisierbare Resolver und Voraussetzungen. Sie bleiben bei `install_methode: "manuell"`. Es wird kein winget-Paket angeboten, dessen Herstellerherkunft und konkrete Installationsdateien nicht überprüft wurden.

## Reproduzierbarer Import und Katalogpflege

```powershell
.venv\Scripts\python.exe tools\import_catalog.py
```

`tools/catalog_enrichment.json` enthält geprüfte Quellen, Windows-Anleitungen, Dateimuster und Installationsentscheidungen. Der Import liest die tatsächlichen Excel-Hyperlinks und Werte über openpyxl. Leerzeilen und der abschließende Tabellenhinweis werden ausgelassen. Bei einer neuen oder fehlenden Tabellenzeile meldet der Import die konkrete Zeile, statt ungeprüfte Quellen automatisch zu übernehmen. Die App selbst benötigt nur `catalog.json`, keine Excel-Datei und kein openpyxl.

Neue Emulatoren können direkt als JSON-Eintrag ergänzt werden: eindeutige `id`, Kategorie aus `categories`, Tabelleninformationen, `official_url`, Installationsmethode, Dateimuster, Startdatei, manuelle Schritte und Rechtshinweis. Neue offizielle HTTPS-Seiten bzw. exakte Repository-Wurzeln müssen in `official_sources` stehen. Ein Eintrag in der Whitelist bezeichnet einen offiziellen Projektpfad, nicht pauschal ganz GitHub. Der Katalog wird beim Programmstart validiert.

Bei einer gebauten EXE hat eine `catalog.json` direkt neben `EmulatorHub.exe` Vorrang vor der eingebetteten Datei. So bleibt der Katalog nach dem Bauen editierbar. Die Recherche-Metadaten sind eine Dokumentation des Prüfstands, keine automatische Freigabe später veränderter Quellen oder Dateiformate.

Jeder Eintrag enthält den geforderten Hinweis:

> BIOS/Firmware und Spiele nur aus der eigenen Hardware oder direkt vom Rechteinhaber beziehen.
