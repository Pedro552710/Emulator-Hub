# Neue Konfigurationen und Katalogfelder

Alle Erweiterungen behalten `schema_version: 1`. Die neuen Katalogfelder sind optional, damit bisherige Einträge weiterhin geladen werden. Dauerhafte Änderungen auch in `tools/catalog_enrichment.json` eintragen, wenn `tools/import_catalog.py` später erneut verwendet wird.

## Ausgeblendete Einträge

`hidden` ist ein optionaler boolescher Wert, standardmäßig `false`. Mit `true` bleiben Eintrag, Quellen, Installationslogik und gespeicherte Nutzerdaten vollständig erhalten. Die standardmäßig ausgeschaltete Einstellung **Ausgeblendete Einträge anzeigen** steuert Kategorien, Karten, Suche, Favoriten/Verlauf, Systemcheck, Spielebibliothek und Vollbild-Modus; leere Kategorien fehlen ebenfalls. **Alle aktualisieren** verwendet nur sichtbare Einträge. shadPS4 und PS4 PKG Tool tragen vorübergehend `hidden: true`. Dauerhafte Reaktivierung auch in `tools/catalog_enrichment.json` pflegen, damit der Excel-Import `hidden: false` reproduziert.

## Offizielle Direktdownloads

`auto_direct` verwendet die überprüfte `direct_url`. Der optionale `direct_resolver: "winuae"` kennzeichnet den einzigen derzeit unterstützten dynamischen Seitenresolver: `id: "winuae"`, `official_url` und `direct_url` exakt `https://www.winuae.net/download/`, `exe: "winuae64.exe"`, `archive_type: "zip"`. Die aktuelle stabile Versionsüberschrift muss zum tatsächlich verlinkten `WinUAE<Versionsziffern>_x64.zip` unter `https://download.abime.net/winuae/releases/` passen. Kein Treffer, Mehrdeutigkeit, Beta-/Preview-Dateien oder fremde Hosts/Pfade verlangen manuelle Einrichtung. Die sicher erkannte stabile Version wird auch für Updates verwendet. `verified_release`/`verified_asset` dokumentieren nur den Recherchezeitpunkt und schreiben keinen dauerhaften Download fest.

Für WinUAE wurde keine offizielle Prüfsumme gefunden; `verified_asset_sha256: null` dokumentiert das ehrlich. Ohne `direct_resolver` bleibt der vorhandene geprüfte Direktlink-Weg mit optionaler `direct_version`, `sha256` oder `checksum_url` erhalten. Details: [geprüfte WinUAE-Quelle](catalog_sources.md#winuae-stabile-downloadseite-und-amiga-konfiguration).

## Systemcheck und Dateiendungen

`configs/system_requirements.json` enthält die Schwellen pro `pc_anforderung`, beispielsweise CPU-Kerne, RAM und GPU-Leistungsklasse. `ram_tolerance_gb: 0.5` berücksichtigt, dass Windows bei nominell 32 GiB etwas weniger nutzbaren RAM meldet. CPU-/GPU-Klassen sind grobe Heuristiken; unbekannte GPU-Daten dürfen keine sichere Zusage erzeugen. Der Systemcheck ist eine Einschätzung, keine Garantie für einzelne Spiele.

`configs/extensions.json` enthält `extensions`: Eine Endung mit einem Konsolennamen wird direkt zugeordnet; eine Liste verlangt die manuelle Auswahl. Konsolennamen müssen mit `konsole` im Katalog übereinstimmen. `.iso`, `.bin`, `.zip` und weitere mehrdeutige Formate werden nicht allein anhand ihres Inhalts erraten. Archive werden nicht geöffnet. Ein Scan speichert ausschließlich Pfade und Metadaten in `library.json`.

Für bestehende lokale Konfigurationen ergänzt der Hub fehlende Amiga-Endungen im Arbeitsspeicher. Bei unveränderten alten Standardlisten für `.iso` und `.cue` kommt Amiga als weiterer Kandidat hinzu. Individuell angepasste Zuordnungen und die gespeicherte Konfigurationsdatei bleiben erhalten.

Konfigurationen werden zuerst unter `<Datenordner>/configs`, dann unter `<Programmordner>/configs` und zuletzt aus den mitgelieferten Ressourcen geladen. Die UI zeigt den aktiven Datenordner. JSON-Dateien mit ungültigen Werten erzeugen verständliche Fehlermeldungen.

## Separate Hilfsprogramme und eigene PS4-Pakete

| Feld | Bedeutung |
| --- | --- |
| `entry_type` | Ohne Feld bleibt ein Eintrag ein Emulator. `"utility"` kennzeichnet ein Hilfsprogramm, das nicht als Spiel-Emulator gewählt und nicht durch **Alle aktualisieren** heruntergeladen wird. |
| `package_args` | Für PS4 PKG Tool ausschließlich `["{package}"]`: ein vollständiger eigener Paketpfad als einzelnes Argument ohne Shell. Dieser Aufruf öffnet den Mini PKG Viewer und installiert noch kein Spiel. |
| `download_notice` | Erforderlicher deutscher Drittanbieterhinweis vor jedem Hilfsprogramm-Download. Die Bestätigung ergänzt die tatsächlich aufgelöste offizielle Quelle und aktuelle SHA-256-Prüfsumme. |
| `ps4_setup_steps` | Genau fünf kurze Schritte auf der PS4-Karte. **PS4 einrichten** installiert nach Bestätigung oder öffnet das Tool-Hauptfenster. |
| `deprecated`, `deprecated_note`, `replacement_id` | Veralteten Eintrag für Altinstallationen erhalten; Installation/Updates sperren, ohne Nutzerdaten zu löschen. Ersatz-ID muss einen anderen vorhandenen Katalogeintrag benennen. |
| `license` | Lizenzhinweis des separat installierten Programms, bei PS4 PKG Tool `"GPL-3.0"`. Keine Einbettung in Hub-Pakete. |

Der Hilfseintrag `ps4-pkg-tool` steht unter **Sony PlayStation** als Hilfsprogramm, stammt ausschließlich aus dem geprüften Repository `pearlxcore/PS4PKGTool` und verwendet `auto_github` nur für ausdrücklich bestätigte stabile Releases. Bei fehlendem eindeutigem Asset oder fehlender offizieller SHA-256 bleibt die manuelle Alternative. Hilfsprogramme erhalten keine `launch_args`, `launch_profiles` oder `launch_extensions` für Emulator-Spielstarts.

Eine eigene `.pkg` wird unabhängig von einer lokalen Endungszuordnung ausschließlich als **Im PS4 PKG Tool installieren** behandelt. Die Bibliothek speichert `package_kind: "ps4_pkg"`, `launchable: false` und keine verwendete Emulator-ID. Die Paketübergabe erfasst keinen Spielstart oder Spielverlauf. Der Hub liest keine Paket-Inhalte und lädt weder Schlüssel noch Spiele herunter. Auch ausdrücklich für PS4 PKG Tool oder eine shadPS4-Altinstallation gespeicherte eigene Spieleordner werden beim Bibliotheksscan auf solche Pakete geprüft; dafür werden keine weiteren Dateien aus diesen Ordnern automatisch aufgenommen. [Manuelle Einrichtung](user-guide.md#eigene-ps4-pakete-mit-ps4-pkg-tool).

## Emulatoren über die Karte starten

| Feld | Bedeutung |
| --- | --- |
| `start_args` | Optionale feste Argumentliste für **Starten**, ohne Spielplatzhalter. Bei shadPS4 `["-b"]` für Big Picture. Ohne Feld bleibt der bisherige Kartenstart erhalten. |
| `start_note` | Deutscher Hinweis zum Kartenstart und dessen Voraussetzungen. |
| `launcher` | Optionales Frontend mit eigener Startdatei, festen `args` und einem relativen `directory` innerhalb des registrierten Kernordners. |

Die folgenden shadPS4-Metadaten dienen seit 1.0.3 ausschließlich vorhandenen Altinstallationen. Der Hub lädt und aktualisiert weder Kern noch QTLauncher; neue Einrichtung über **PS4 einrichten → Tools > shadPS4 Manager** im Tool.

shadPS4 behält `exe: "shadPS4.exe"` als registrierten Kern. Das manuell bereitgestellte Frontend steht unter `launcher.exe: "shadPS4QtLauncher.exe"`, `launcher.directory: "qtlauncher"` und `launcher.args: []`. Der Hub bevorzugt diese Startdatei im Unterordner oder direkt neben dem Kern. Fehlt sie, wird der Kern mit `start_args: ["-b"]` gestartet. Argumente werden als Liste ohne Shell übergeben. Kern und Launcher bleiben getrennt; die Launcher-Konfiguration wird nicht automatisch geschrieben.

Die Launcher-Quellen stehen in `official_url` und `github_repo` innerhalb von `launcher`; die exakte Repository-Wurzel muss in `official_sources` erlaubt sein. `download_muster` und `archive_type` dokumentieren das geprüfte Windows-Archiv. `verified_release`, `verified_prerelease`, `verified_asset` und `verified_asset_sha256` halten den Recherchezeitpunkt fest. `launcher.install_methode: "manuell"` kennzeichnet bei shadPS4 den fehlenden stabilen Launcher-Release. Das Datums-/Hash-Muster erlaubt keine automatische Installation dieses Pre-Releases. `launcher.note` erklärt die manuelle Einrichtung über Version Manager → Add Custom. Details stehen im [Handbuch](user-guide.md#playstation-4-mit-shadps4).

## Spiele starten

| Feld | Bedeutung |
| --- | --- |
| `launch_args` | Liste einzelner Argumente, beispielsweise `["-b", "-e", "{game}"]` für Dolphin. |
| `launch_profiles` | Parameter nach tatsächlichem EXE-Dateinamen, Groß-/Kleinschreibung egal. Das passende Profil hat Vorrang vor `launch_args`. `null` verlangt eine eigene Einrichtung. |
| `launch_extensions` | Optional zugelassene Endungen wie `[".bin", ".elf", ".self"]` für RPCS3. Ein anderer Dateityp wird mit Hinweis abgelehnt. |
| `launch_note` | Deutscher Hinweis zu Dateiformaten, notwendiger Einrichtung oder fehlenden Parametern. |

Unterstützte Platzhalter: `{game}` ist der vollständige eigene Dateipfad, `{game_dir}` dessen Ordner, `{game_stem}` der Dateiname ohne Endung und `{exe_dir}` der tatsächliche EXE-Ordner. Keine zusätzlichen Anführungszeichen eintragen: Jedes Listenelement wird als eigenes Argument übergeben. Der Start verwendet keinen Shell-Aufruf und ersetzt nur diese vier Platzhalter.

```json
"launch_profiles": {
  "fbneo64.exe": ["{game_stem}", "-w"],
  "mame.exe": ["-rompath", "{game_dir}", "{game_stem}"]
},
"launch_extensions": [".zip"]
```

MAME verwendet Set-Namen und den eigenen Suchordner. In FinalBurn Neo muss dieser Suchordner zuerst im Emulator eingerichtet werden. Für Genesis Plus GX in RetroArch bleibt das Profil `null`, bis der tatsächlich installierte Core mit `-L` hinterlegt ist. RPCS3 startet eigene entpackte native `.bin`/`.elf`/`.self`-Dateien; PS3-ISOs werden nicht automatisch umgewandelt. xemu erwartet ein eigenes Xbox-XISO. Vita3K kann ein eigenes VPK/ZIP über seinen CLI-Pfad installieren und starten; die ursprüngliche Spiel-Datei bleibt unverändert, der Emulator kann dabei selbst Daten in seinem Profil anlegen.

shadPS4 startet die eigene entschlüsselte `eboot.bin` über den registrierten SDL-Kern mit `["-g", "{game}"]`; das Profil erlaubt nur `.bin`. Dieser direkte Bibliotheksstart verwendet weder QTLauncher noch `start_args`. `-b` und `-g` werden nicht kombiniert, weil der geprüfte Kern bei `-b` vor dem Spielstart zurückkehrt. Der QTLauncher besitzt ebenfalls dokumentierte `-e`-/`-g`-Optionen, doch der Hub nutzt für Spiele ausschließlich den bereits bestätigten direkten Kernstart. Die Endung bleibt mehrdeutig und muss als PlayStation 4 zugeordnet werden. Vollständigen eigenen Spielordner beibehalten; `.pkg` bleibt ein nicht startbares Paket mit separater Viewer-Übergabe. Keine Entschlüsselung oder Paketinstallation durch den Hub. Firmware-Module, Controllerbelegung und gezielte eigene Sicherungspfade bleiben manuell. Details und Quellen stehen unter [shadPS4 im Handbuch](user-guide.md#playstation-4-mit-shadps4).

WinUAE erlaubt ausschließlich vorbereitete eigene `.uae`-Konfigurationen mit `launch_args: ["-f", "{game}", "-s", "use_gui=no"]` und `launch_extensions: [".uae"]`. Rohabbilder erhalten den Hinweis **über WinUAE-Konfiguration zu starten**. Modell, eigene Disk-/Festplatten-/CD-Dateien und legales Kickstart müssen im Profil eingerichtet sein. Die [.uae-Erkennung](https://github.com/tonioni/WinUAE/blob/6030/zfile.cpp#L320), [CLI](https://github.com/tonioni/WinUAE/blob/6030/main.cpp#L1012) und [Konfigurationsoption](https://github.com/tonioni/WinUAE/blob/6030/cfgfile.cpp#L76) sind am stabilen Tag 6030 belegt.

Geprüfte CLI-Grundlagen: [DuckStation-Argumente](https://github.com/stenzek/duckstation/wiki/Command-Line-Arguments), [PPSSPP-Argumente](https://www.ppsspp.org/docs/reference/command-line/), [MAME-Argumente](https://docs.mamedev.org/commandline/commandline-all.html), [FinalBurn-Neo-CLI](https://github.com/finalburnneo/FBNeo/blob/master/src/burner/win32/main.cpp), [RPCS3-Startcode](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/rpcs3.cpp), [Vita3K-CLI](https://github.com/Vita3K/Vita3K/blob/master/vita3k/config/src/config.cpp), [xemu-Argumente](https://github.com/xemu-project/xemu/blob/master/system/vl.c), [shadPS4-Argumente am Release-Tag](https://github.com/shadps4-emu/shadPS4/blob/v.0.19.0/src/main.cpp).

## Eigene BIOS-Dateien prüfen

`bios` ist eine Liste erwarteter eigener lokaler Dateien. Jeder Eintrag enthält `label`, `root`, `directory`, `filenames` und optional `required`, `any_of`, `note` und `portable`.

```json
"bios": [{
  "label": "Eigenes regionales PlayStation-BIOS",
  "root": "localappdata",
  "directory": "DuckStation/bios",
  "filenames": ["scph5500.bin", "scph5501.bin", "scph5502.bin"],
  "required": true,
  "any_of": true,
  "note": "Die passende Region muss im Emulator eingestellt werden.",
  "portable": {"marker": "portable.txt", "directory": "bios"}
}]
```

`any_of: true` bedeutet, dass eine der Dateien reicht; sonst werden alle geprüft. `required: false` kennzeichnet einen optionalen oder spielabhängigen Bedarf. Bei Mednafen Saturn ist die für das Spiel passende BIOS-Region erforderlich; die beiden regionalen Prüfungen sind Alternativen. PC-Engine-CD benötigt eine eigene Systemkarte, HuCard-Spiele benötigen sie nicht. Aktuelle melonDS-Versionen können beim direkten DS-Start Ersatzdaten verwenden; DSi benötigt zusätzliche eigene Systemdateien.

Der Checker prüft lediglich, ob eine Datei vorhanden, nicht leer und lesbar ist. Er prüft keine Echtheit, Prüfsumme, Version, Region oder vollständige Firmware-Installation. Für PCSX2, xemu, RPCS3, Vita3K und WinUAE wäre ein universeller Dateiname irreführend. WinUAE verwendet einen selbst konfigurierten ROMs-/Kickstart-Pfad und benötigt ein eigenes lizenziertes oder selbst gesichertes Kickstart; deshalb `bios: []` plus Einrichtungsanleitung. Es gibt keine Kickstart-, Spiele- oder Workbench-Downloads oder Links. `bios_note` erklärt deshalb die eigene Einrichtung und die Oberfläche erlaubt die Auswahl tatsächlich verwendeter eigener Dateien. Diese liegen als `bios_overrides[emulator_id]` in `settings.json`; das Zurücksetzen entfernt die Auswahl. Es gibt keine BIOS-/Firmware-Downloads oder Bezugsquellen.

## Sicherungsprofile

`backup_paths` ist eine Liste gezielter Save-/Einstellungspfade mit `label`, `root`, `directory` und `type: "directory"` oder `"file"`. `backup_note` erklärt Besonderheiten. Ganze Installations-, Benutzer- und Spieleordner sind keine Sicherungsprofile.

| `root` | Basisordner |
| --- | --- |
| `emulator` | Ordner der registrierten EXE, auch bei verschachtelt entpackten Paketen. |
| `localappdata` | `%LOCALAPPDATA%`. |
| `roamingappdata` | `%APPDATA%`. |
| `userprofile` | `%USERPROFILE%`. |
| `documents` | Windows-Known-Folder „Dokumente“, einschließlich OneDrive-/anderer Umleitungen. |

`directory` ist ein Windows-sicherer relativer Pfad. Absolute Pfade, `..`, reservierte Windows-Namen und leere/gesamte Profilordner werden im Katalog abgelehnt. Für BIOS darf `directory: "."` den Basisordner bezeichnen. Benutzer dürfen in der Oberfläche eigene absolute gezielte Pfade wählen; sie ersetzen die Standardprofile über `profile_overrides[id].backup_paths`. Save-Dateien wie `.sav`/`.srm` oder gezielte Save-Unterordner innerhalb eines Spieleordners sind erlaubt.

Ein Profilordner darf keinen konfigurierten Spieleordner oder registrierte Bibliotheksdateien enthalten. Bekannte Spielpfade und eindeutig erkennbare Spiel-Dateiendungen werden vor dem Lesen eines Backups und vor dem Entpacken einer Wiederherstellung abgewiesen. Mehrdeutige `.bin`/`.zip` werden über die registrierten Bibliothekspfade geschützt, damit native Einstellungen oder eigene Firmware mit solchen Endungen möglich bleiben. Daher die Bibliothek aktuell halten und eigene Sicherungspfade ausschließlich auf Saves/Einstellungen begrenzen.

Das ZIP enthält ein Manifest mit Emulator-ID, stabilen Profilkennungen und SHA-256 pro Datei. Vor der Wiederherstellung werden ZIP-Pfade, Größe, Prüfsummen und die aktuellen erlaubten Zielprofile geprüft. Links, Windows-Junctions und beliebige Zielpfade aus Archiven werden abgelehnt. Danach entsteht automatisch ein Backup des aktuellen Stands unter `<Datenordner>/backups/<Emulator-ID>`; erst anschließend werden Dateien ersetzt. Ein fehlgeschlagener Schreibschritt setzt die bereits geänderten Dateien zurück. Dateien, die nicht im ZIP stehen, bleiben erhalten. Die Oberfläche verlangt vor dem Wiederherstellen eine Sicherheitsbestätigung. Eine Sicherung ist auf insgesamt 4 GiB und 50.000 Dateien begrenzt; xemu-HDD-Abbilder können diese Grenze überschreiten.

Emulatoren vor Sicherung/Wiederherstellung schließen: Hub und Emulator teilen keinen Datenbank-/Dateilock. Benutzerdefinierte native Speicherorte werden nicht automatisch aus sämtlichen Emulator-Konfigurationen gelesen. Fehlende Standardpfade werden protokolliert und leere Profile bleiben als solche im Manifest erkennbar. Bei bsnes/SameBoy liegen Saves häufig neben den eigenen Spielen; diese konkreten Save-Dateien manuell ergänzen. RPCS3/Vita3K/Azahar benutzen umfangreiche native Datenstrukturen; nur konkret passende Save-Unterordner wählen. Dolphin `Wii/title` und Xenia `content` werden nicht pauschal gesichert, weil sie auch installierte Spiele oder Kanäle enthalten können.

## Native portable Profile und Hub-Modus

Ein einzelner BIOS-/Backup-Eintrag kann ein alternatives natives Profil beschreiben:

```json
"portable": {
  "marker": "portable.txt",
  "marker_type": "file",
  "directory": "User/Config"
}
```

Die Markierung wird relativ zur tatsächlichen EXE geprüft. `marker_type` ist `file` (Standard) oder `directory`; `markers` kann mehrere alternative Namen enthalten und ersetzt dann `marker`. `directory` bezeichnet den Profilpfad relativ zur EXE. `path_from_marker: true` ist ausschließlich für PCSX2-artige `portable.txt` vorgesehen: Ein vorhandener nicht leerer Dateiinhalt legt den Profilbasisordner fest, relativ zur EXE oder absolut. Der Checker erstellt oder verändert keine native Markierung und stellt keine bestehenden Emulatorprofile um.

| Emulator | Berücksichtigte bestehende Markierung | Natives Profil |
| --- | --- | --- |
| Mesen 2 | `settings.json` | Neben der EXE. |
| Dolphin | `portable.txt` | `User` neben der EXE. |
| DuckStation | `portable.txt` | Neben der EXE. |
| PCSX2 | `portable.txt` oder `portable.ini` | Neben der EXE bzw. Pfad aus `portable.txt`. |
| Azahar | Verzeichnis `user` | Dieses Verzeichnis. |
| melonDS | Verzeichnis `portable` | Dieses Verzeichnis. |
| xemu | `xemu.toml` | Diese Datei neben der EXE. |

Profilgrundlagen: [Mesen-Konfigurationspfade](https://github.com/SourMesen/Mesen2/blob/master/UI/Config/ConfigManager.cs), [Dolphin-Benutzerordner](https://dolphin-emu.org/docs/guides/controlling-global-user-directory/), [PCSX2-Konfigurationspfade](https://github.com/PCSX2/pcsx2/blob/master/pcsx2/Pcsx2Config.cpp), [Azahar-Dateipfade](https://github.com/azahar-emu/azahar/blob/master/src/common/file_util.cpp), [melonDS-Konfigurationspfade](https://github.com/melonDS-emu/melonDS/blob/master/src/frontend/qt_sdl/main.cpp), [xemu-Einstellungspfade](https://github.com/xemu-project/xemu/blob/master/ui/xemu-settings.cc), [PPSSPP-Speicherorte](https://www.ppsspp.org/docs/getting-started/save-data-and-storage-windows/), [Stella-Einstellungen](https://stella-emu.github.io/docs/index.html).

Der Hub-Modus ist unabhängig davon: Eine `portable.flag` neben der Hub-EXE legt Hub-Daten in `data` neben dem Programm ab. Das umfasst installierte Emulatorpakete, `settings.json`, `installed.json`, `library.json` und automatische Sicherheitsbackups. Programmlokale Pfade werden intern relativ gespeichert und bleiben nach dem Verschieben des Programmordners nutzbar; externe eigene Pfade bleiben extern. Manuell gewählte ZIP-Zielordner werden respektiert. Native Emulatoren können weiterhin eigene AppData-/Dokumente-Profile benötigen; für vollständige Portabilität ihren dokumentierten portablen Modus selbst aktivieren und die tatsächlichen Save-Pfade prüfen.
