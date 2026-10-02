# Neue Konfigurationen und Katalogfelder

Alle Erweiterungen behalten `schema_version: 1`. Die neuen Katalogfelder sind optional, damit bisherige Einträge weiterhin geladen werden. Dauerhafte Änderungen auch in `tools/catalog_enrichment.json` eintragen, wenn `tools/import_catalog.py` später erneut verwendet wird.

## Systemcheck und Dateiendungen

`configs/system_requirements.json` enthält die Schwellen pro `pc_anforderung`, beispielsweise CPU-Kerne, RAM und GPU-Leistungsklasse. `ram_tolerance_gb: 0.5` berücksichtigt, dass Windows bei nominell 32 GiB etwas weniger nutzbaren RAM meldet. CPU-/GPU-Klassen sind grobe Heuristiken; unbekannte GPU-Daten dürfen keine sichere Zusage erzeugen. Der Systemcheck ist eine Einschätzung, keine Garantie für einzelne Spiele.

`configs/extensions.json` enthält `extensions`: Eine Endung mit einem Konsolennamen wird direkt zugeordnet; eine Liste verlangt die manuelle Auswahl. Konsolennamen müssen mit `konsole` im Katalog übereinstimmen. `.iso`, `.bin`, `.zip` und weitere mehrdeutige Formate werden nicht allein anhand ihres Inhalts erraten. Archive werden nicht geöffnet. Ein Scan speichert ausschließlich Pfade und Metadaten in `library.json`.

Konfigurationen werden zuerst unter `<Datenordner>/configs`, dann unter `<Programmordner>/configs` und zuletzt aus den mitgelieferten Ressourcen geladen. Die UI zeigt den aktiven Datenordner. JSON-Dateien mit ungültigen Werten erzeugen verständliche Fehlermeldungen.

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

Geprüfte CLI-Grundlagen: [DuckStation-Argumente](https://github.com/stenzek/duckstation/wiki/Command-Line-Arguments), [PPSSPP-Argumente](https://www.ppsspp.org/docs/reference/command-line/), [MAME-Argumente](https://docs.mamedev.org/commandline/commandline-all.html), [FinalBurn-Neo-CLI](https://github.com/finalburnneo/FBNeo/blob/master/src/burner/win32/main.cpp), [RPCS3-Startcode](https://github.com/RPCS3/rpcs3/blob/master/rpcs3/rpcs3.cpp), [Vita3K-CLI](https://github.com/Vita3K/Vita3K/blob/master/vita3k/config/src/config.cpp), [xemu-Argumente](https://github.com/xemu-project/xemu/blob/master/system/vl.c).

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

Der Checker prüft lediglich, ob eine Datei vorhanden, nicht leer und lesbar ist. Er prüft keine Echtheit, Prüfsumme, Version, Region oder vollständige Firmware-Installation. Für PCSX2, xemu, RPCS3 und Vita3K wäre ein universeller Dateiname irreführend. `bios_note` erklärt deshalb die eigene Einrichtung und die Oberfläche erlaubt die Auswahl tatsächlich verwendeter eigener Dateien. Diese liegen als `bios_overrides[emulator_id]` in `settings.json`; das Zurücksetzen entfernt die Auswahl. Es gibt keine BIOS-/Firmware-Downloads oder Bezugsquellen.

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
