# Emulator Hub – Handbuch

[Zur Projektstartseite](../README.md) · [Entwicklung und Build](development.md) · [Veröffentlichen](releasing.md)

Natives Desktop-Programm für Windows 10/11 x64 mit Python 3.12 und PySide6. Der Katalog enthält die 25 Einträge des Blatts **Emulatoren** aus `docs/emulatoren_mit_downloadanleitungen.xlsx`, verteilt auf acht Kategorien. Standardmäßig sind 23 Emulator-Einträge sichtbar, einschließlich **Commodore / Amiga** mit **WinUAE**. shadPS4 und PS4 PKG Tool unter **Sony PlayStation** bleiben erhalten und sind vorübergehend ausgeblendet. Die Anwendung liest den JSON-Katalog und verändert die Excel-Dateien nicht.

## Start

Nach dem Einrichten der virtuellen Umgebung (siehe [Entwicklung](development.md)) direkt starten:

```powershell
.\.venv\Scripts\python.exe main.py
```

Nach einer Aktualisierung die Abhängigkeiten erneut mit `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` installieren. Für die sichere Zugangsdatenablage ist `keyring>=25,<26` hinzugekommen; die Controllerabfrage nutzt vorhandene Windows-XInput-Bibliotheken ohne weitere Python-Pakete.

Auf einem neuen Rechner mit Python 3.12:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

Falls PowerShell die Aktivierung nicht erlaubt, sind dieselben Schritte ohne Aktivierung möglich:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Die Oberfläche bietet Kategorien, eine Suche, farbige PC-Anforderungen, Installationsstatus, Starten, Deinstallieren, offizielle Seiten, nummerierte Anleitungen, optionale Desktop-/Startmenü-Verknüpfungen, eine Updateprüfung und ein Aktivitätsprotokoll. Dazu kommen die Startseite mit Favoriten und zuletzt benutzten Emulatoren, ein Systemcheck, die Bibliothek eigener Spiel-Dateien, optionale Cover und Spielinfos, ein Controller-Assistent, der Vollbild-Modus sowie BIOS-Prüfung und ZIP-Sicherungen. Downloads, Scans, Hardwareabfragen, Dienstabfragen und Sicherungen laufen in einem QThread. Es wird jeweils ein Auftrag ausgeführt; die Oberfläche bleibt bedienbar. Beim Schließen während eines Auftrags kann der Auftrag sicher abgebrochen werden.

## Startseite, Systemcheck und gemeinsame Updates

Unter **Einstellungen → Ausgeblendete Einträge anzeigen** kannst du ausgeblendete Katalogeinträge wieder sichtbar machen. Die Option ist standardmäßig aus. Solange sie aus ist, erscheinen shadPS4 und PS4 PKG Tool weder in Kategorien/Karten, Suche, Favoriten und Verlauf noch im Systemcheck, der Spielebibliothek oder im Vollbild-Modus. Leere Kategorien werden ebenfalls ausgeblendet. **Alle aktualisieren** überspringt ausgeblendete Einträge. Die Option ändert nur die Anzeige und Auswahl: vorhandene Installationen, gespeicherte Zuordnungen, Favoriten, Bibliotheksmetadaten und eigene Spieleordner werden nicht gelöscht oder deinstalliert. Für eine spätere dauerhafte Reaktivierung kann `hidden` in den Katalogquellen wieder auf `false` gesetzt werden.

Mit dem Stern auf einer Emulator-Karte wird der Emulator zum Favoriten. Auf der **Startseite** stehen diese Favoriten und **Zuletzt benutzt**; ein Emulatorstart oder Spielstart aktualisiert den Verlauf. Favoriten, Verlauf, Spieleordner und der letzte Systemcheck liegen in `settings.json`.

Rechts neben den Aktionen jeder Karte stehen zwei kleine Symbolbuttons: **Emulator-Ordner öffnen** öffnet den gespeicherten Installationsordner im Windows-Explorer, auch bei manueller Zuordnung. Ohne Installation ist der Button ausgegraut. **Spiele-Ordner öffnen** funktioniert unabhängig davon und legt beim ersten Klick einen eigenen Ordner unter `Dokumente\EmulatorHub\Games\<Emulator-Name>\` an. Die Namen werden für Windows bereinigt; bei gleichen Namen unterscheidet die Emulator-ID die Ordner. Ein Rechtsklick bietet **Spiele-Ordner ändern…** und **Auf Standard zurücksetzen**. Die Pfade werden pro Emulator unter `games_dir` in `settings.json` gespeichert. Im portablen Modus liegt der Standard unter `<Programmordner>\Games\<Emulator-Name>\`. Öffnen, Ändern und Zurücksetzen kopieren oder verschieben keine Spiel-Dateien; diese Ordner werden auch nicht automatisch zur Bibliothek hinzugefügt.

Beim ersten Start erfolgt automatisch ein **Systemcheck**. Der gleichnamige Button wiederholt ihn, etwa nach einem Hardwarewechsel. Der Hub liest CPU, physische Kerne, Threads, RAM und die lokal gemeldeten Grafikkarten aus; unter Windows werden ergänzende CPU-/GPU-Daten über PowerShell und CIM/WMI abgefragt. Jede Karte erhält zur bisherigen **PC-Anforderung** eine Einstufung **Läuft gut**, **Grenzwertig** oder **Zu schwach** mit kurzer Begründung. Nicht zuverlässig erkannte Hardware wird ausdrücklich genannt.

Die Schwellen in `configs/system_requirements.json` bestimmen Mindestwerte und empfohlene Werte für **Sehr niedrig** bis **Sehr hoch**. GPU-Namen werden anhand bearbeitbarer Schlüsselwörter einer groben Klasse zugeordnet. `ram_tolerance_gb` erlaubt standardmäßig 0,5 GiB Abweichung für hardwareseitig reservierten Arbeitsspeicher, damit beispielsweise 31,92 GiB bei nominell 32 GiB nicht allein eine schlechtere Einstufung verursachen. Die Einschätzung ist **keine Garantie und kein Benchmark**: CPU-Architektur und Takt, GPU-Treiber, Auflösung, Emulatoreinstellungen und das einzelne Spiel beeinflussen die tatsächliche Leistung. Bei mehreren GPUs verwendet der Check die höchste erkannte Klasse; die vom Emulator tatsächlich gewählte GPU kann abweichen. Änderungen an den Schwellen werden mit einem neuen Systemcheck übernommen.

**Alle aktualisieren** prüft sämtliche sichtbaren zugeordneten Emulatoren auf Updates und installiert verfügbare, automatisch verwaltete Updates nacheinander. Gesamtfortschritt und Aktivitätsprotokoll zeigen den Stand. Ein Fehler bei einem Emulator verhindert die folgenden Aktualisierungen nicht. Manuelle Zuordnungen und Einträge ohne verlässlichen Versionsvergleich werden erklärt und bleiben zur manuellen Aktualisierung vorgesehen. Bereits aktuelle Installationen werden übersprungen; ein Abbruch beendet die restliche Warteschlange.

PS4 PKG Tool nimmt nicht an der Sammelaktualisierung teil. Jeder Download des separaten Hilfsprogramms benötigt einen eigenen ausdrücklichen Klick und den Quellen-/Prüfsummenhinweis.

## Bibliothek eigener Spiel-Dateien

Unter **Einstellungen** lassen sich ein oder mehrere Spieleordner hinzufügen oder entfernen. **Speichern und scannen** beziehungsweise **Bibliothek scannen** durchsucht ihre Unterordner im Hintergrund. Der Fortschritt zeigt zunächst die Suche und anschließend die Erfassung. Doppelte Dateien aus überlappenden Ordnern werden nur einmal erfasst. Symlinks, Windows-Junctions und der eigene Hub-Datenordner werden übersprungen. Nicht lesbare oder fehlende Ordner werden im Protokoll erklärt; die übrigen Ordner werden weiter gescannt.

`configs/extensions.json` enthält die Zuordnung von Dateiendungen zu Konsolen. Ein einzelner Konsolenname ordnet beispielsweise `.nes`, `.sfc`/`.smc`, `.gb`/`.gbc`, `.gba`, `.z64`/`.n64`/`.v64`, `.nds`, `.3ds`, `.gcm`/`.rvz`/`.wbfs`, `.gen`/`.md` oder `.cdi`/`.gdi` direkt zu. Eine Liste kennzeichnet eine mehrdeutige Endung: `.iso`, `.cue`, `.bin`, `.chd`, `.cso`, `.elf` und `.zip` verlangen eine Auswahl. Auch ZIP-Archive können zu verschiedenen Konsolen gehören; der Hub öffnet oder entpackt sie für die Erkennung nicht. Weitere mitgelieferte Zuordnungen umfassen etwa `.vpk` für PS Vita und `.self` für PlayStation 3. Für Amiga werden eigene `.adf`, `.adz`, `.dms`, `.ipf`, `.hdf`, `.lha` und `.uae` zugeordnet; `.cue` und `.iso` bleiben mehrdeutig und bieten zusätzlich Amiga an. Eigene Images sind **über WinUAE-Konfiguration zu starten**; direkt startet der Hub nur vorbereitete `.uae`-Konfigurationen. Änderungen dieser Konfiguration werden nach einem Neustart und erneutem Scan verwendet.

Auf der Seite **Bibliothek** stehen die Spiele nach Konsole gruppiert. Suche nach Name oder Dateipfad, Konsolenfilter, **Nur Favoriten** sowie Sortierung nach Name oder zuletzt gespielt lassen sich kombinieren. Ein Stern markiert einen Spiel-Favoriten. **Konsole zuordnen** korrigiert eine Erkennung oder löst eine mehrdeutige Endung auf; diese manuelle Wahl bleibt bei weiteren Scans erhalten.

Ein **Doppelklick** oder **Spiel starten** startet die eigene Datei mit einem passenden installierten Emulator. Bei ungeklärter Konsole erscheint zuerst die Auswahl; bei mehreren passenden Emulatoren lässt sich der Emulator wählen. Fehlt der Emulator, bietet der Hub direkt **Installieren** mit dem vorhandenen automatischen oder manuellen Installationsweg an. Anschließend kann das Spiel erneut gestartet werden. Die tatsächlich gewählte Emulator-ID und der Zeitpunkt eines erfolgreichen Prozessstarts werden gespeichert; sie sind keine Bestätigung, dass das Spiel im Emulator erfolgreich läuft.

`library.json` speichert ausschließlich Dateipfade und Metadaten wie Konsole, Favorit und zuletzt gespielt. Der Scan kopiert und verändert keine Spiel-Dateien und lädt keine Spiele herunter. Verschobene oder gelöschte Dateien bleiben mit ihren Metadaten als **Datei fehlt** sichtbar. Ein abgebrochener Scan ersetzt die bisherige Bibliothek nicht.

Bei aktivierter Anzeige ausgeblendeter Einträge werden eigene `.pkg`-Dateien aus einem Bibliotheksordner oder dem zugeordneten Spieleordner einer PS4-Karte als **Im PS4 PKG Tool installieren** erfasst. Sie erhalten keinen Spielstart; auch eine gespeicherte alte Zuordnung macht sie nicht startbar. Der gesonderte Button **Im PS4 PKG Tool installieren** übergibt genau diese Datei an das externe Hilfsprogramm. Fehlt das Tool, bietet der Hub dessen ausdrückliche Installation mit Downloadhinweis an. Ein Doppelklick auf ein Paket führt zu dieser Hilfe statt zu einem Emulatorstart. Der [PS4-Paketablauf](#eigene-ps4-pakete-mit-ps4-pkg-tool) beschreibt die anschließenden manuellen Schritte.

Der Spielstart verwendet die im Katalog dokumentierten `launch_args` und gegebenenfalls ein `launch_profiles`-Profil für die tatsächlich ausgewählte EXE. Argumente werden als Liste ohne Shell übergeben; Leerzeichen und Sonderzeichen im Dateipfad bleiben erhalten. Fehlt ein bestätigtes Startprofil, erscheint eine verständliche Anleitung. `launch_extensions` begrenzt bei Bedarf die direkt startbaren Dateitypen.

Emulatorinterne Ersteinrichtung bleibt erforderlich, beispielsweise für Controller, eigene Firmware und Grafik. RPCS3 benötigt ein passend vorbereitetes, entpacktes eigenes Spiel, etwa `EBOOT.BIN`, statt eines beliebigen ISO-Abbilds. Vita3K verarbeitet unterstützte eigene Pakete; dabei kann der Emulator selbst das Spiel zunächst installieren und benötigt seine eigene Einrichtung. FinalBurn Neo verwendet den standardisierten Spiel-/Treibernamen; den Ordner mit den eigenen Arcade-Dateien muss man einmal im Emulator einstellen. MAME verwendet ein eigenes Argumentprofil mit Spielordner und Spielnamen. RetroArch benötigt einen passend eingerichteten Core und ein ausdrückliches Startprofil im Katalog; die BlastEm-Argumente werden dafür nicht automatisch übernommen. Welche Datei ein konkreter Emulator unterstützt, hängt zudem vom Spiel und seiner Version ab.

## Amiga mit WinUAE

Die Kategorie **Commodore / Amiga** enthält **WinUAE** für **Amiga (A500, A1200, CD32 …)**, Plattform **Windows**, PC-Anforderung **Niedrig**. Diese Einstufung ist eine grobe Einschätzung; aufwendige Erweiterungen und CPU-/JIT-Einstellungen können mehr Leistung verlangen.

**Installieren** ruft ausschließlich die [offizielle Downloadseite](https://www.winuae.net/download/) ab. Der Hub vergleicht die aktuelle stabile Versionsüberschrift mit dem tatsächlich verlinkten 64-Bit-ZIP und lädt dieses aus `https://download.abime.net/winuae/releases/`. Das Archiv wird mit Fortschritt in den Hub-Emulatorordner entpackt; Startdatei ist die im echten Archiv bestätigte `winuae64.exe`. Desktop-/Startmenü-Verknüpfungen sind optional. Beta-Dateien, alte Versionen und Zusatzpakete werden nicht ausgewählt. Ist die Seite nicht eindeutig erkennbar oder passt der Dateiname nicht zur aktuellen Version, bleibt die manuelle Anleitung; vorhandene Installationen bleiben erhalten.

Bei der Prüfung am **03.10.2026** nennt die Seite **6.0.3** und verlinkt diese vier Programmdateien, jeweils von `download.abime.net`:

| Paket | 32 Bit | 64 Bit |
| --- | --- | --- |
| MSI-Installer | `InstallWinUAE6030.msi` | `InstallWinUAE6030_x64.msi` |
| ZIP | `WinUAE6030.zip` | `WinUAE6030_x64.zip` |

Die aktuelle stabile Version steht getrennt von Erweiterungen und alten Versionen. Derzeit enthält die Downloadseite keinen Beta-Link oder eigenen Beta-Bereich; der Resolver akzeptiert nur den aktuellen stabilen WinUAE-Abschnitt. Es wurde keine dedizierte Versions-/Prüfsummen-API und keine offizielle SHA-256-Angabe gefunden. Die WordPress-JSON-Ausgabe enthält lediglich dieselbe HTML-Seite. Der lokale berechnete Downloadhash ist deshalb keine Hersteller-Prüfsumme. **Auf Updates prüfen** und **Alle aktualisieren** vergleichen bei automatisch verwalteten WinUAE-Installationen die sicher erkannte stabile Version; manuell zugeordnete Installationen und nicht eindeutig auflösbare Seiten werden als manuell zu prüfen erklärt. Details und Quellen: [Katalogprüfung](catalog_sources.md#winuae-stabile-downloadseite-und-amiga-konfiguration).

**WinUAE enthält kein Kickstart-ROM.** Du brauchst ein lizenziertes bzw. aus eigener Amiga-Hardware selbst gesichertes Kickstart, beispielsweise gekauft mit Amiga Forever. Der Hub lädt, verlinkt oder bündelt keine Kickstart-ROMs, Spiele, ADF-Abbilder oder Workbench-Dateien. In WinUAE unter **Paths** den **ROMs**-Ordner auswählen und in der ROM-Auswahl das zum Hardwaremodell passende eigene Kickstart einstellen. Pfad und Dateiname hängen vom Modell und der eigenen Konfiguration ab; der BIOS-Checker behauptet keinen festen universellen Pfad. Tatsächlich verwendete eigene Dateien lassen sich im Hub manuell für die Prüfung zuordnen.

Richte Hardwaremodell, eigene Disk-/Festplatten-/CD-Abbilder und Controller in WinUAE ein und speichere deine Konfiguration als **`.uae`**. Diese vorbereitete Konfiguration lädt der Bibliotheksstart mit `-f <eigene Konfiguration> -s use_gui=no`, als Argumentliste ohne Shell. Rohe Images werden mit **über WinUAE-Konfiguration zu starten** gekennzeichnet, weil sie allein kein vollständiges Amiga-/Kickstart-Profil bestimmen. Der Hub erzeugt kein geratenes Direktstartprofil. Für die manuelle Installation auf der offiziellen Seite das aktuelle **Download (64-bit)**-ZIP wählen, vollständig entpacken und den Ordner mit `winuae64.exe` im Hub zuordnen.

Auch mit einer älteren lokalen Dateiendungs-Konfiguration werden fehlende Amiga-Endungen erkannt. Bei unveränderten Standardlisten für `.iso` und `.cue` steht Amiga zusätzlich zur Auswahl. Individuell geänderte Zuordnungen und die gespeicherte Konfigurationsdatei bleiben erhalten.

## PlayStation 4 mit shadPS4

**Vorübergehend ausgeblendet:** Die folgende vorhandene PS4-Anleitung gilt bei aktivierter Option **Einstellungen → Ausgeblendete Einträge anzeigen**. Alle Quellen, Startprofile und installierten Daten bleiben erhalten. Mit ausgeschalteter Option werden auch PS4-Spiele/Pakete in der Bibliothek ausgeblendet und PS4 nicht geprüft oder aktualisiert.

PS4 wird über die Karte **PS4 PKG Tool** eingerichtet. Der Hub verwaltet den Emulator und QTLauncher nicht mehr selbst. Bei aktivierter Anzeige erscheint auch die veraltete shadPS4-Karte; vorhandene Installationen bleiben startbar, neue Hub-Installationen und Updates bleiben gesperrt. Ihre Dateien, Zuordnungen, Favoriten und bisherigen Startprofile bleiben erhalten. Neue Installationen und Updates übernimmt der Manager im Tool. Wird später `hidden: false` gesetzt, gilt wieder die bisherige Anzeige ausschließlich für Altinstallationen.

### Eigene PS4-Pakete mit PS4 PKG Tool

**PS4 einrichten** bietet beim ersten Klick die Installation des Drittprogramms aus einem stabilen offiziellen Release an. Vor dem Download musst du Quelle, SHA-256 und den Drittanbieter-/Antivirus-Hinweis ausdrücklich bestätigen. Bei fehlendem stabilem Asset oder fehlender offizieller Prüfsumme bleibt die manuelle Anleitung. Bei installiertem Tool öffnet der Button dessen Hauptfenster ohne zusätzliche Argumente.

Die fünf Schritte auf der Karte:

1. **PS4 PKG Tool** mit **PS4 einrichten** starten.
2. **Tools > shadPS4 Manager** öffnen, shadPS4 über **Install shadPS4** und QTLauncher installieren.
3. Im Manager den Spielebibliotheksordner festlegen.
4. Eigene Basis-PKG und passende Update-PKG laden und **Install to shadPS4** wählen.
5. QTLauncher starten.

Der Ablauf ist in der [offiziellen Release-Anleitung](https://github.com/pearlxcore/PS4PKGTool/releases/tag/v1.8.0) und im [README](https://github.com/pearlxcore/PS4PKGTool/blob/v1.8.0/README.md#shadps4-setup-and-use) belegt. Menünamen können sich in neuen Versionen oder Übersetzungen ändern.

**Ordner für Spiele-PKGs öffnen** öffnet deinen eigenen Paketordner. Ein Rechtsklick erlaubt das Ändern oder Zurücksetzen seiner Zuordnung; dabei werden persönliche Dateien nicht gelöscht. Dieser Ordner enthält die ursprünglichen PKGs und ist vom Spielebibliotheksordner zu unterscheiden, den du im Tool festlegst. Nur eigene Spiele verwenden.

Die Bibliothek zeigt Pakete als **Im PS4 PKG Tool installieren**. Der Paketbutton übergibt genau einen Dateipfad als **`[exe, pkg_path]`** ohne Shell und öffnet den PKG Viewer; die eigentliche Installation erfolgt im Hauptfenster. Das Tool wird nicht automatisch beim Scan installiert, und der Hub liest keine PKG-Inhalte. Installierte Spiele verwaltest und startest du in QTLauncher bzw. im Tool.

Geprüft ist das offizielle [GPL-3.0-Projekt](https://github.com/pearlxcore/PS4PKGTool/blob/v1.8.0/LICENSE) mit dem stabilen Windows-x64-Asset **`PS4-PKG-Tool-v1.8.0.zip`**, Startdatei **`PS4 PKG Tool.exe`**, .NET-10-Desktop-Laufzeit. SHA-256: `1ef9bb1f4ec1ad4e10f5a7d814e216323019385977c5b4409c911c5943884ea1`. Für eine manuelle Tool-Zuordnung das vollständige offizielle stabile ZIP entpacken und den Ordner über **Anleitung → Ordner auswählen** registrieren.

Das Tool wird weder im Repository noch in Release-Paketen mitgeliefert. Der Hub entschlüsselt oder entpackt keine PS4-Pakete, enthält keine Schlüssel und bietet keine Spiele-, PKG-, BIOS- oder Firmware-Links. Reale Tool-/Spielinstallation und Runtime-Einrichtung wurden nicht ausgeführt; Prozesse und API-Antworten werden in Tests simuliert.

## Cover und Spielinfos

Unter **Einstellungen → Cover & Infos** lässt sich **IGDB / Twitch** oder **ScreenScraper** auswählen. Die Funktion ist optional; ohne Konto bleibt die eigene Bibliothek vollständig nutzbar. Es gibt keine Hintergrundabfragen beim Programmstart. Beide Dienste können getrennt eingerichtet werden; für einen Ladevorgang wird die ausgewählte Quelle verwendet.

Für **IGDB** wird ein eigenes Twitch-Konto mit aktivierter Zwei-Faktor-Anmeldung und eine im Twitch Developer Portal registrierte Anwendung benötigt. Den Anwendungstyp **Confidential** verwenden, damit sich ein Client-Secret erzeugen lässt; eine Redirect-URL wie `http://localhost` genügt für diese Nutzung. **Twitch Client-ID** und **Twitch Client-Secret** im Hub eintragen. Die Anwendung verwendet einen OAuth-App-Token im Arbeitsspeicher. IGDB beschreibt Einrichtung und Nutzung für nicht kommerzielle Anwendungen in der [offiziellen API-Dokumentation](https://api-docs.igdb.com/#getting-started); die [Twitch-OAuth-Dokumentation](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/#client-credentials-grant-flow) erklärt den verwendeten Anmeldeweg.

Für **ScreenScraper** werden **Benutzername**, **Passwort**, eine **eigene freigeschaltete Entwickler-ID** und das zugehörige **Entwicklerpasswort** benötigt. Ein Benutzerkonto allein genügt für diese API-Anbindung nicht. Der Hub enthält keine gemeinsamen oder fremden Entwickler-Schlüssel. Freigabe, Kontingente und aktuelle Bedingungen stehen auf der [offiziellen ScreenScraper-API-Seite](https://www.screenscraper.fr/webapi2.php).

**Zugangsdaten speichern** legt die Werte über `keyring` ausschließlich im **Windows-Anmeldeinformationsmanager** ab. Geheimnisse stehen weder im Quellcode noch in `settings.json`, `catalog.json`, Cache oder Protokoll; es gibt keinen unverschlüsselten Ersatzspeicher. **Zugangsdaten laden** liest gespeicherte Werte in die Eingabefelder, Passwörter bleiben verdeckt. **Verbindung testen** verwendet bei vollständig leeren Feldern bereits gespeicherte Werte; vollständig ausgefüllte Zugangsdaten werden vor dem Test gespeichert. Unter Windows verwendet `keyring` den [Windows-Credential-Manager-Backend](https://keyring.readthedocs.io/en/latest/#what-is-python-keyring-lib).

In der **Bibliothek** lädt **Cover & Infos laden** Informationen zum ausgewählten Spiel. **Cover & Infos für die Bibliothek laden** bearbeitet Spiele mit zugeordneter Konsole und ohne gespeicherte Dienst-Metadaten nacheinander; einzelne Fehler stoppen die übrigen Spiele nicht. Die Suche verwendet einen von Regions-, Dump- und Disc-Markierungen bereinigten Dateinamen und die zugeordnete Konsole. Ähnliche oder mehrere Treffer werden zur Bestätigung angezeigt; ein Spiel lässt sich dabei überspringen oder der Vorgang beenden. Ein einzelner exakt passender Titel mit bestätigter Plattform darf direkt übernommen werden. Die Zuordnung bleibt eine Namenssuche und kann bei ungewöhnlichen Dateinamen falsch oder erfolglos sein.

Die Ansichten **Liste** und **Raster mit Covern** verwenden dieselbe Suche, Konsolenfilter, Sortierung und Favoriten. **Details** zeigt Titel, Cover, Jahr, Genres und Beschreibung sowie **Daten von IGDB** beziehungsweise **Daten von ScreenScraper** und die Quelladresse. Ohne Bild erscheint ein neutraler Platzhalter. Die Bedienoberfläche ist auf Deutsch; Spieltitel, Genres und Beschreibungen bleiben in der vom Dienst gelieferten Sprache. ScreenScraper-Inhalte werden nach Möglichkeit auf Deutsch ausgewählt.

Cover liegen unter `<Datenordner>\cache\covers\`, bestätigte Infos und Suchtreffer unter `cache\metadata.json`. Bereits vorhandene Treffer und Bilder werden wiederverwendet; Details und Cover funktionieren auch offline. Relative Coverpfade bleiben beim Umzug eines portablen Hub-Ordners gültig. **Cache leeren** entfernt nach Bestätigung nur Dienst-Metadaten und vom Hub erzeugte Cover. Eigene Spiel-Dateien, Bibliothekszuordnungen, Favoriten und Zugangsdaten bleiben erhalten. Danach können Infos neu gesucht werden. Ein beschädigter Cache blockiert den Programmstart nicht; neue Abfragen schreiben ihn erst nach ausdrücklichem Leeren wieder.

Dienstabfragen und Bildprüfung laufen im Hintergrund und lassen sich abbrechen. Der Hub fragt seriell ab, begrenzt IGDB auf weniger als vier Anfragen pro Sekunde und verwendet bei ScreenScraper die gemeldeten Minuten- und Tageskontingente. Wartezeiten, begrenzte Wiederholungen und `Retry-After` werden berücksichtigt; ein aufgebrauchtes Tageskontingent wird erklärt. Netzwerkaufrufe haben Zeitlimits, deshalb kann ein Abbruch während eines laufenden Requests kurz dauern. Es werden nur Infos und überprüfte, größenbegrenzte Coverbilder von freigegebenen HTTPS-Zielen geladen; keine Spiele, ROMs, BIOS-Dateien oder Firmware. Beachte die Nutzungsbedingungen des ausgewählten Dienstes.

## Controller-Assistent

**Controller einrichten** öffnet einen Assistenten mit angeschlossenen **XInput-Geräten**, Gerätetyp, Anschlussnummer und Livetest für Tasten, beide Sticks und Trigger. Es werden bis zu vier XInput-Geräte erkannt. XInput liefert keine verlässlichen Produktnamen; Anzeigen wie **XInput-Controller 1** bezeichnen einen Anschluss, dessen Nummer sich nach erneutem Verbinden ändern kann. Reine DirectInput-/HID-Geräte werden hier nicht automatisch erkannt; falls das Gerät einen XInput-Modus unterstützt, diesen aktivieren. Die Abfrage nutzt die Windows-API über `ctypes`, benötigt keine zusätzliche SDL-/pygame-Installation und läuft über einen Timer mit Pausen für leere Anschlüsse. Grundlage sind die [offiziellen XInput-Hinweise](https://learn.microsoft.com/en-us/windows/win32/xinput/getting-started-with-xinput).

`controller_config` im Katalog kennzeichnet **auto** oder **manuell**. Automatisches Schreiben ist ausschließlich für **Dolphin, GameCube-Port 1, XInput-Gamepad** vorgesehen. Voraussetzung sind ein bereits eingerichtetes aktives Profil mit vorhandener `GCPadNew.ini` und ein Standard-Controller an Port 1. In `Dolphin.ini` entspricht dies `[Core] SIDevice0 = 6`; bei fehlendem Eintrag gilt der native Standardwert. Zuerst Dolphin öffnen, GameCube-Port 1 einrichten und speichern, danach Dolphin vollständig schließen. Falls der Hub das aktive Profil nicht findet, **Konfigdatei wählen** verwenden. Wii-Eingaben und andere GameCube-Ports werden nicht geändert. Die Zuordnungen richten sich nach Dolphins [XInput-Eingabecode](https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/InputCommon/ControllerInterface/XInput/XInput.cpp) und [Konfigurationsformat](https://github.com/dolphin-emu/dolphin/blob/master/Source/Core/InputCommon/ControllerEmu/ControlGroup/ControlGroup.cpp).

**Vorschau erstellen** zeigt die geplante Belegung, ohne zu schreiben: XInput A/B/X/Y werden GameCube A/B/X/Y, RB wird Z; linker Stick wird Hauptstick, rechter Stick C-Stick. Übernehmen verlangt eine ausdrückliche Bestätigung, dass Dolphin geschlossen ist und die Datei zum aktiven Profil gehört. Vor jeder Änderung entsteht eine exakte Sicherung unter `<Datenordner>\controller-backups\`; die Datei wird atomar ersetzt und erneut auf Änderungen seit der Vorschau geprüft. **Rückgängig machen** verlangt ebenfalls Bestätigung, sichert den aktuellen Stand und stellt die letzte Belegung wieder her. Eine außerhalb des Hubs nachträglich geänderte Konfiguration wird dabei nicht überschrieben.

Für die übrigen Emulatoren und alternative Programmvarianten zeigt der Assistent eine kurze passende Anleitung für deren Eingabemenü. Es gibt keine pauschale automatische Belegung für unterschiedliche Konfigformate oder Eingabe-Plugins. Den jeweiligen Emulator nach einer Konfigurationsänderung neu starten und mit dem eigenen Controller testen; spezielle Lenkräder, Wii-Eingaben und spielbezogene Profile bleiben manuell.

## Vollbild-Modus

**Vollbild-Modus** öffnet eine große Ansicht mit Konsolenkacheln und anschließend den eigenen Spielen mit großen Covern, Schrift und deutlicher Mint-Fokusmarkierung. Lokale Cover werden bei Bedarf im Hintergrund geladen; ohne Cover erscheint ein Platzhalter. Fokuswechsel animieren nur kurz, ohne die Kachelanordnung zu verändern. Die Ansicht funktioniert auch ohne Internet oder eingerichteten Dienst.

| Aktion | XInput-Gamepad | Tastatur |
| --- | --- | --- |
| Navigieren | Steuerkreuz oder linker Stick | Pfeiltasten; Tab/Shift+Tab |
| Konsole wählen / Spiel starten | A | Enter, Leertaste oder A |
| Eine Ebene zurück | B | Rücktaste oder B |
| Menü öffnen | Start | M, Menütaste oder F10 |
| Normale Ansicht wiederherstellen | Start + Zurück/Select mindestens 1,2 Sekunden halten | Esc |

Der Gamepad-Status wird regelmäßig per Timer abgefragt; Stick-Totzonen und Tastenflanken vermeiden ungewollte Mehrfachaktionen. **Spiel starten** verwendet die bestehende Konsolen-/Emulatorauswahl und die Katalog-Startargumente. Auch die zugehörigen Qt-Dialoge sind per Gamepad bedienbar: oben/unten wählt Einträge, links/rechts oder LB/RB wechselt den Fokus, A bestätigt und B bricht die Abfrage ab. Das Polling bleibt während eines geöffneten Auswahldialogs aktiv.

**Esc** gilt bei Eingabefokus im Hub. **Start + Zurück/Select** verlässt die eigene Couch-Ansicht auch, während ein Emulator im Vordergrund läuft. Normale Tasten werden dann ausschließlich vom Emulator verarbeitet; der Hub sendet keine Eingaben an fremde Fenster und beendet den Emulator nicht. Er zeigt anschließend seine normale Ansicht und fordert den Fokus an; Windows kann diese Fokusanforderung beschränken. Für die erstmalige Einrichtung externer Emulatoren, Websites und native Windows-Dateiauswahl wird weiterhin deren eigene Bedienung verwendet.

## Eigene BIOS-Dateien und ZIP-Sicherungen

Der Kartenbutton **BIOS & Sicherung** öffnet die lokalen Prüf- und Sicherungsfunktionen. **BIOS prüfen** zeigt pro hinterlegter Datei **vorhanden** oder **fehlt** sowie den erwarteten Dateinamen und Ordner. Die Hinweise erklären, wo die eigenen Dateien abgelegt und welche Pfade gegebenenfalls im Emulator eingestellt werden müssen. **Eigene Dateien auswählen** erlaubt abweichende lokale BIOS-/Firmware-Dateien; **Standardpfade prüfen** kehrt zu den Katalogpfaden zurück. Optionale Dateien werden als optional erklärt. Der Check prüft Vorhandensein, Lesbarkeit und eine nicht leere Datei; er bestätigt weder Echtheit noch Region oder Versionskompatibilität. Für manche Emulatoren wird die Firmware innerhalb des Emulators eingerichtet und nicht allein durch eine lose Datei aktiviert.

**ZIP-Sicherung erstellen** sichert die im Katalog hinterlegten Spielstand- und Einstellungsdateien beziehungsweise Ordner in einem gewählten Zielordner. Über **Sicherungspfade wählen** lassen sich gezielte eigene Ordner oder einzelne Dateien zuordnen; alternativ gelten wieder die Standardpfade aus dem Katalog. Die Sicherung ist kein vollständiges Abbild der Emulatorinstallation oder der Spielebibliothek. Fehlende Profilpfade werden im Protokoll genannt. Schließe den betreffenden Emulator vor einer Sicherung oder Wiederherstellung, damit er die Dateien währenddessen nicht verändert.

**Wiederherstellen** akzeptiert Emulator-Hub-ZIPs für denselben Emulator und die passenden Profilzuordnungen. Nach einer Sicherheitsabfrage wird das gesamte Archiv mit Pfaden, Manifest und Dateiprüfsummen geprüft. Vor dem ersten Überschreiben entsteht zwingend eine neue Sicherung des aktuellen Stands unter `backups\<emulator-id>\` im Hub-Datenordner. Schlägt diese Sicherung fehl, beginnt die Wiederherstellung nicht. Bei einem Fehler oder Abbruch werden bereits ersetzte Dateien zurückgesetzt; der Pfad zur vorher angelegten Sicherung wird angezeigt. Dateien, die nicht Bestandteil des gewählten Backups sind, bleiben erhalten. Verknüpfungen, unsichere ZIP-Pfade, nicht zugeordnete Profile und beschädigte Sicherungen werden abgelehnt.

Bekannte Spiel-Dateipfade aus der Bibliothek und eindeutige Spiel-Dateiendungen sind auch vor versehentlichem Sichern oder Überschreiben durch die Profilwerkzeuge geschützt. Ganze Spieleordner werden abgelehnt. Gezielte Save-Ordner und eigene `.sav`-/`.srm`-Dateien dürfen dagegen innerhalb eines Spieleordners liegen. Sicherungen sind auf 4 GiB unkomprimierte Daten und 50.000 Dateien begrenzt; große HDD-Abbilder müssen anderweitig gesichert werden.

Der Hub lädt **keine ROMs, BIOS-Dateien oder Firmware** herunter und bietet keine Quellen dafür an. Diese Funktionen arbeiten ausschließlich mit selbst bereitgestellten lokalen Dateien.

## Windows-Pakete bauen

```powershell
.\build.ps1
```

Der Build erzeugt den vollständigen Ordner `dist\EmulatorHub\` mit `EmulatorHub.exe` und `_internal\`. Beide gehören zusammen; eine einzelne EXE kann nicht separat weitergegeben werden. Python, Qt, Standardkonfigurationen, Katalog, Logo und Windows-Zugangsdatenbackend werden mitgeliefert, keine Emulatoren oder Spieldateien. Ein Fenstertest prüft das fertige Programm.

Danach entsteht `Output\EmulatorHub-<Version>-portable.zip` mit dem kompletten Programmordner und `portable.flag`. Ist der Compiler von Inno Setup verfügbar, wird zusätzlich `Output\EmulatorHub-Setup.exe` erzeugt; andernfalls erklärt das Skript, dass nur der Installer fehlt. Die Installer-Installation erfolgt pro Benutzer. Die Version stammt aus `core/version.py`. Details, Voraussetzungen, Lizenzdateien und die Release-Automatisierung stehen unter [Entwicklung und Build](development.md) und [Veröffentlichen](releasing.md).

## Logo austauschen und Icons erzeugen

`assets/logo.svg` enthält das eigene Controller-Logo in den Farben des Dunkel-Designs. Es erscheint oben in der Seitenleiste sowie als Fenster- und Taskleistensymbol. Die SVG-Darstellung passt sich der Bildschirmskalierung an; PNG-Logos werden mit erhaltenem Seitenverhältnis angezeigt. Unter Windows setzt der Hub vor dem ersten Fenster die eigene AppUserModelID `EmulatorHub.Desktop` für die Taskleistenzuordnung. Die verwendete Windows-Funktion ist in der [Microsoft-Dokumentation](https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nf-shobjidl_core-setcurrentprocessexplicitappusermodelid) beschrieben.

Zum Austauschen die SVG-Datei durch ein eigenes, eigenständiges SVG ersetzen. Für ein PNG-Logo `assets/logo.svg` entfernen oder umbenennen und das eigene Bild als `assets/logo.png` ablegen, möglichst mit mindestens 256 Pixeln. Sind beide vorhanden, hat SVG Vorrang. Danach ausführen:

```powershell
.\.venv\Scripts\python.exe tools\make_icons.py
```

Das Hilfsskript verwendet QtSvg und Pillow und erzeugt aus SVG `assets/logo.png` mit 1024 × 1024 Pixeln sowie `assets/icon.ico` mit **16, 32, 48, 64, 128 und 256 Pixeln**. Ein bereits als Quelle verwendetes PNG bleibt unverändert. Nicht quadratische Logos erhalten transparente Ränder. Ungültige Eingaben ersetzen keine vorhandenen Ausgaben. Die ICO-Größen werden nach dem Schreiben geprüft; Details zum Format stehen in der [Pillow-Dokumentation](https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#ico).

`.\build.ps1` führt das Hilfsskript automatisch vor dem EXE-Build aus. Für das Explorer-Symbol der EXE muss die EXE nach einem Logowechsel neu gebaut werden. Das Programm bevorzugt zur Laufzeit einen eigenen `assets`-Ordner neben der EXE; ohne diesen Ordner verwendet es die eingebauten Dateien über die vorhandene Ressourcenauflösung mit `sys._MEIPASS`. Ein externer PNG-Ordner hat auch gegenüber einem eingebauten SVG Vorrang. Für einen anderen Logoordner kann das Hilfsskript mit `--assets-dir "C:\Pfad\assets"` ausgeführt werden.

## Automatische Installation

Neun sichtbare Emulator-Einträge sowie das ausgeblendete PS4-Hilfsprogramm verwenden **stabile offizielle GitHub-Releases** und ein eindeutig überprüftes Windows-x64-ZIP. Die konkrete Version wird bei jeder Installation über die API bestimmt; es wird keine Versionsnummer als Dauer-Download festgeschrieben.

| Emulator | Konsole | Automatischer Weg / Besonderheit |
| --- | --- | --- |
| Mesen | NES | Offizielles Windows-ZIP; native, eigenständig gebaute Windows-EXE. |
| bsnes | SNES | Offizielles Windows-ZIP. Die Tabellenalternative Snes9x wird separat manuell eingerichtet. |
| SameBoy | Game Boy / GBC | Offizielles Windows-SDL-ZIP. |
| melonDS | Nintendo DS | Offizielles Windows-x86_64-ZIP. |
| Azahar | Nintendo 3DS | Windows-MXE-ZIP; die grafische Startdatei wird eindeutig gewählt. |
| Cemu | Wii U | Offizielles portables Windows-x64-ZIP. |
| PPSSPP | PSP | Offizielles Windows-x64-ZIP; Start über PPSSPPWindows64.exe. |
| Flycast | Dreamcast | Offizielles Win64-ZIP. |
| xemu | Xbox | Offizielles versioniertes Windows-x86_64-ZIP; Debug-/Symbolpakete werden ausgeschlossen. |
| PS4 PKG Tool (ausgeblendet) | PlayStation 4 (Hilfsprogramm) | **PS4 einrichten**: bestätigter stabiler Tool-Download; shadPS4 und QTLauncher im shadPS4 Manager des Tools einrichten. |
| shadPS4 (ausgeblendet, veraltet, nur Altinstallation) | PlayStation 4 | Bestehende Installation bleibt startbar. Keine neue Installation oder Updates durch den Hub. |

WinUAE ergänzt diese Wege als `auto_direct`: ausschließlich das aktuelle stabile Windows-x64-ZIP aus der offiziellen Downloadseite, mit Versions-/Dateinamenprüfung und manueller Alternative.

Eine erfolgreiche Installation bedeutet, dass das Programm eingerichtet und seine Startdatei gefunden wurde. Emulatorinterne Ersteinrichtung kann anschließend erforderlich sein. Die in der Tabelle genannten übrigen Plattformen dienen der Information; der Hub installiert Windows-x64-Pakete.

## Manuelle Einrichtung

| Emulator / Tabellenalternative | Grund für den manuellen Weg |
| --- | --- |
| mGBA | Das überprüfte Windows-7z verwendet BCJ2; py7zr unterstützt dieses Verfahren nicht. Offiziellen Installer oder eine geeignete lokale Archivsoftware verwenden. |
| Mupen64Plus | Kommandozeilen-/Plugin-System mit gesonderter Frontend-Einrichtung. Ersetzt das archivierte Simple64 als N64-Standard. |
| Dolphin | Windows-Runtime-Voraussetzungen und aktuelle Paketwahl werden über die offizielle Anleitung geklärt. |
| DuckStation | Veränderlicher „latest“-Build-Kanal und eigene Voraussetzungen. |
| PCSX2 | Windows-Runtime-Voraussetzungen und 7z-/Installer-Auswahl; vollständig startfertige automatische Einrichtung nicht bestätigt. |
| RPCS3 | Fortlaufende Builds, dynamische Downloadseite und dort veröffentlichte Prüfsummen; kein zuverlässig bestätigter stabiler API-Resolver. |
| Vita3K | Nightlies statt stabiler Releases. |
| BlastEm / Genesis Plus GX | BlastEm ist ein eigenes Programm; Genesis Plus GX wird als Core über RetroArch eingerichtet. Die Anleitung unterscheidet beide Wege. |
| Mednafen – Saturn | Kommandozeilenorientiert; die Tabellenalternative Yaba Sanshiro betrifft Android. |
| Xenia Canary | Ausschließlich die offizielle Canary-Releases-Seite; experimenteller Build-Kanal. |
| Stella | Offizielles portables Paket vorhanden; zusätzliche Windows-Runtime kann erforderlich sein. |
| Mednafen – PC Engine | Kommandozeilenorientiert; keine automatische Einrichtung einer grafischen Oberfläche. |
| FinalBurn Neo / MAME | Nightly-Kanal und unterschiedliche Programmpakete; bewusste manuelle Wahl. |
| Snes9x | Alternative zur automatisch installierten bsnes-Anwendung; eigener offizieller Download. |

Bei diesen Einträgen öffnet **Installieren** die Anleitung. Dort stehen konkrete nummerierte Schritte, die offizielle Downloadseite und die Ordnerauswahl. Nach der Ordnerauswahl wird die dokumentierte Startdatei gesucht und als Windows-EXE geprüft. Bei mehreren Treffern bitte einen spezifischeren Unterordner auswählen. Manuelle Zuordnungen erhalten die Version „unbekannt“; eine automatische Versionsbehauptung wird vermieden. Die Updateprüfung nennt solche Fälle im Protokoll und verweist auf die offizielle Seite.

Wenn eine automatische Quelle ihr Dateinamenformat ändert, ein Download scheitert oder eine Prüfsumme nicht stimmt, wird die vorhandene Installation erhalten. Der Fehlerdialog bietet die manuelle Anleitung an.

Alle Quellen, geprüften Dateinamen und Gründe sind zusätzlich in [docs/catalog_sources.md](catalog_sources.md) dokumentiert (bisherige Quellen: 01.10.2026; PS4 und WinUAE: 03.10.2026).

## Lokale Daten und Deinstallation

Standardordner: `%LOCALAPPDATA%\EmulatorHub\`

- `emulators\<id>\`: automatisch verwaltete portable Programme.
- `installed.json`: Pfad, Startdatei, Version, UTC-Installationsdatum, Installationsmethode und Verknüpfungen; bei automatischen Downloads auch der berechnete SHA-256-Hash.
- `settings.json`: Anzeige ausgeblendeter Einträge, Emulator-Favoriten, zuletzt benutzte Emulatoren, Bibliotheksordner, Spiele-Ordner pro Emulator (`games_dir`), Systemcheck, gewählte Metadatenquelle und Bibliotheksansicht sowie eigene BIOS-/Sicherungs-/Controllerprofilpfade und Controller-Änderungsverlauf. Keine Zugangsdaten.
- `library.json`: eigene Spiel-Dateipfade, Konsolenzuordnung, Spiel-Favoriten und zuletzt gespielt.
- `configs\system_requirements.json`: bearbeitbare Hardware-Schwellen und GPU-Klassen.
- `configs\extensions.json`: bearbeitbare Dateiendungszuordnung für die Bibliothek.
- `backups\<id>\`: Sicherheitsbackups vor Wiederherstellungen; reguläre ZIP-Sicherungen liegen im gewählten Zielordner.
- `cache\covers\` und `cache\metadata.json`: eigene lokale Kopien geladener Cover, bestätigte Dienst-Metadaten und Suchtreffer.
- `controller-backups\`: exakte Sicherungen vor Controller-Konfigurationsänderungen und vor deren Rücknahme.
- `hub.log`: rotierendes UTF-8-Protokoll mit bis zu zwei Sicherungsdateien.

Installationsliste, Einstellungen und Bibliothek werden atomar geschrieben. Eine beschädigte Datei erzeugt beim Start eine verständliche Meldung und wird nicht stillschweigend überschrieben. `hub.lock` verhindert zwei gleichzeitige Instanzen für denselben Datenordner.

Beim ersten Start werden die beiden Konfigdateien in den Datenordner kopiert. Bereits vorhandene Anpassungen werden nicht ersetzt. Der Hub bevorzugt die Kopie unter `<Datenordner>\configs\`; danach folgen eine Konfiguration unter `configs\` neben dem Programm und schließlich die eingebauten Standardwerte. Bearbeite daher im normalen Betrieb die Dateien im angezeigten Datenordner. `system_requirements.json` verwendet `levels` mit `minimum` und `recommended` für `cpu_cores`, `ram_gb` und `gpu_score`; `gpu_keywords` und `gpu_classes` steuern die grobe GPU-Einstufung. In `extensions.json` steht unter `extensions` für jede kleingeschriebene Endung entweder ein Konsolenname oder eine Liste möglicher Konsolen. Die Konsolennamen müssen zu den Katalogeinträgen passen, damit ein Emulator gefunden wird.

### Portabler Modus

Liegt eine leere Datei **`portable.flag` neben `EmulatorHub.exe`**, verwendet der Hub `<Programmordner>\data\` anstelle von `%LOCALAPPDATA%\EmulatorHub\`. Automatische Emulatorinstallationen, Hub-Einstellungen, Installationsliste, Bibliotheksmetadaten, Cover-Cache, Konfigurationen, Protokoll und Sicherheitsbackups liegen dann in diesem Ordner. Kopiere beim Umzug den vollständigen Programmordner einschließlich `_internal` und `data`. Pfade zu Dateien innerhalb des Programmordners werden in den Hub-JSON-Dateien relativ gespeichert und nach einem Umzug wieder aufgelöst. Selbst gewählte externe Spielordner und manuelle Emulatorinstallationen außerhalb des Programmordners müssen am Zielrechner weiterhin erreichbar sein. Dienst-Zugangsdaten bleiben im Windows-Anmeldeinformationsmanager des angemeldeten Benutzers; sie reisen nicht mit dem portablen Ordner und müssen auf einem anderen Rechner erneut eingerichtet werden.

Der portable Modus des Hubs ändert nicht automatisch das Speicherverhalten eines Emulators. Ein Emulator kann seine eigenen Spielstände oder Einstellungen weiterhin unter AppData oder im Benutzerprofil ablegen. Richte bei Bedarf dessen eigenen portablen Modus und die passenden Sicherungspfade ein; die Hinweise im Dialog nennen solche Besonderheiten. Bereits vorhandene, im Katalog dokumentierte native Portable-Markierungen werden bei den Profilpfaden berücksichtigt; der Hub legt diese nicht selbst an. Windows-Dokumentordner werden einschließlich einer möglichen OneDrive-Umleitung aufgelöst. Das Anlegen oder Entfernen von `portable.flag` wählt einen anderen Datenordner und verschiebt vorhandene Daten nicht automatisch. Der Programmordner muss beschreibbar sein. Ein ausdrücklich übergebener Parameter **`--data-dir`** hat Vorrang vor dem Flag.

Updates werden zunächst in einen temporären eigenen Ordner entpackt und erst nach erfolgreicher Prüfung übernommen. Zusätzliche Benutzerdaten sowie bestehende Einstellungen in INI/CFG/JSON/TOML/YAML/XML-Dateien werden übernommen. Da jede Anwendung andere Einstellungen verwenden kann, vor wichtigen Updates persönliche Daten zusätzlich sichern.

**Deinstallieren** entfernt bei einer automatisch verwalteten portablen Installation den gesamten eigenen Emulatorordner einschließlich dort gespeicherter persönlicher Daten und Hub-Verknüpfungen. Der Bestätigungsdialog nennt diesen Umfang. Bei manuell gewählten Ordnern wird ausschließlich die Hub-Zuordnung entfernt; die Dateien bleiben erhalten. Fremde Löschpfade, symbolische Links und Windows-Reparse-Points werden abgelehnt.

## Quellen und Prüfsummen

`official_sources` im Katalog ist die explizite HTTPS-Whitelist. GitHub-Einträge sind auf das jeweilige Projekt-Repository begrenzt. Die API wird daraus abgeleitet. Weiterleitungen werden vor dem nächsten Request geprüft; GitHub-Release-Downloads dürfen ausschließlich zusätzlich auf die bekannten GitHub-Asset-CDNs wechseln. HTTP, fremde Repositories, Zugangsdaten in URLs und unsichere Pfade werden abgelehnt.

Der Hub prüft automatisch den offiziellen GitHub-Asset-Digest `sha256`, eine passende veröffentlichte SHA-256-Datei oder eine explizit konfigurierte Prüfsumme. Wenn eine veröffentlichte Summe nicht eindeutig gelesen werden kann oder abweicht, wird nicht installiert. Gibt es keine offizielle Prüfsumme, wird dies im Protokoll ausdrücklich vermerkt; ein berechneter eigener Hash ersetzt keine veröffentlichte Summe. ZIP-/7z-/TAR-Archive werden auf Pfadtraversal, Links, Windows-Sonderpfade, doppelte Namen und Entpackgröße geprüft. Heruntergeladene Programme werden bei der Installation nicht automatisch gestartet.

BIOS/Firmware und Spiele nur aus der eigenen Hardware oder direkt vom Rechteinhaber beziehen.

## Katalog ohne Codeänderung ergänzen

Beim Python-Start wird `catalog.json` im Projekt geladen. Die EXE bevorzugt eine `catalog.json` direkt neben der EXE; ohne diese Datei verwendet sie den eingebauten Katalog. Zum Bearbeiten daher den Projektkatalog neben die EXE kopieren.

Einträge benötigen `id`, `kategorie`, `hersteller`, `konsole`, `emulator`, `plattformen`, `pc_anforderung`, `official_url`, `download_anleitung`, `hinweis`, `install_methode`, `download_muster`, `exe` und `manuelle_schritte`. Der Rechtshinweis muss in `hinweis` enthalten sein. Neue Kategorien werden in `categories` ergänzt, neue geprüfte offizielle Quellen in `official_sources`. IDs bleiben nach der Installation unverändert.

- `auto_github`: zusätzlich `github_repo` und ein eindeutiger regulärer Ausdruck in `download_muster`; `archive_type` typischerweise `zip`.
- `auto_direct`: zusätzlich eine überprüfte `direct_url`, gegebenenfalls `direct_version`, `sha256` oder `checksum_url`. Bei WinUAE bezeichnet `direct_url` die offizielle Downloadseite und `direct_resolver: "winuae"` die sichere aktuelle stabile Link-/Versionsauflösung; kein festgeschriebener Archivlink oder erfundener Herstellerhash. Archive werden wie GitHub-Downloads geprüft. Bei `archive_type: "installer"` wird der offizielle Installer gestartet; nach Abschluss muss dessen Ordner manuell zugeordnet werden.
- `winget`: nur für separat geprüfte Pakete und Manifeste verwenden; die 25 erhaltenen Katalogeinträge benötigen diese Methode nicht. Details und Sicherheitsgrenzen stehen weiter unten.
- `manuell`: leeres Downloadmuster erlaubt; nachvollziehbare nummerierte Schritte und eine passende Startdatei hinterlegen. `alternative_exes` erlaubt alternative Dateinamen, etwa `retroarch.exe` bei einem Core.

Für die neuen Funktionen können Einträge außerdem `start_args`, `start_note` und `launcher` für den Kartenstart sowie `launch_args`, `launch_profiles`, `launch_extensions` und `launch_note` für Bibliotheksspiele, `bios`/`bios_note` und `backup_paths`/`backup_note` enthalten. Sie beschreiben bestätigte Startparameter, erwartete eigene BIOS-Dateien und gezielte Sicherungsprofile. Spielargumentvorlagen unterstützen `{game}`, `{game_dir}`, `{game_stem}` und `{exe_dir}`. Alternative EXE-Dateien brauchen ihr eigenes bestätigtes Spielprofil; `null` bedeutet, dass dafür noch kein direkter Spielstart hinterlegt ist. Das Format und Beispiele stehen in [docs/new_catalog_fields.md](new_catalog_fields.md). Für dauerhafte Änderungen beim Excel-Import dieselben Felder auch in `tools/catalog_enrichment.json` pflegen.

`controller_config` ist `"auto"` oder `"manuell"`, `controller_manual` enthält die deutsche Anleitung. Für den ausdrücklich unterstützten Dolphin-Adapter kommt `controller_adapter: "dolphin_gc_xinput"` hinzu. Ein bloßes Setzen von `"auto"` macht einen anderen Emulator nicht automatisch kompatibel; der Code akzeptiert nur einen vorhandenen geprüften Adapter. Diese Felder enthalten keine Dienst-Zugangsdaten.

Unbekannte Muster sind in `todo` vermerkt und verwenden `manuell`. Der Excel-Import ist reproduzierbar:

```powershell
.\.venv\Scripts\python.exe tools\import_catalog.py
```

`tools/catalog_enrichment.json` enthält die geprüften Ergänzungen und korrigierten Quellen. Neue Excel-Zeilen müssen dort ausdrücklich geprüft ergänzt werden. **Der Import erzeugt catalog.json neu und ersetzt direkte Änderungen daran.** Für dauerhafte Anpassungen entweder nur den JSON-Katalog pflegen oder auch die Importergänzungen aktualisieren.

## Optionaler WinGet-Weg

`core/winget.py` führt für ausdrücklich konfigurierte Pakete `winget install` aus. Er akzeptiert nur einen engen, geprüften Teil des Microsoft-Manifestformats: `winget_id`, `winget_version` und `winget_manifest_url` müssen festgelegt sein. Das Manifest muss aus dem offiziellen `microsoft/winget-pkgs`-Repository stammen und eine unveränderliche Git-Revision mit 40 Hexadezimalzeichen verwenden. Manifestadresse, Hersteller-Repository und `https://cdn.winget.microsoft.com/cache` müssen ausdrücklich in `official_sources` stehen.

Freigegeben sind ausschließlich eindeutige x64-Pakete für den aktuellen Benutzer, vom Typ `portable` oder `zip` mit portablem Inhalt, ohne zusätzliche Abhängigkeiten, Installerschalter oder Admin-Rechte. Bewegliche Download-Tags werden abgelehnt. Der offizielle GitHub-Release-Download wird vor dem Aufruf über die Hub-Whitelist heruntergeladen und gegen die Manifest-Prüfsumme geprüft. Anschließend wird die lokale WinGet-Quelle gegen die offizielle Microsoft-Quelle geprüft und die genaue Paketversion mit aktivierter WinGet-Hashprüfung installiert. Es wird keine lokale Manifestfreigabe eingeschaltet und keine Systemeinstellung geändert.

Fehlendes WinGet, nicht freigegebene Manifeste oder eine unerwartete Installationsstruktur führen zur manuellen Anleitung. WinGet übernimmt die Paketdeinstallation; der Hub löscht diese Verzeichnisse nicht rekursiv. Neue WinGet-Versionen werden erst angeboten, wenn ein neues geprüftes Manifest im Katalog hinterlegt ist. Dieser Erweiterungsweg wurde mit isolierten Tests geprüft; keiner der mitgelieferten Einträge verwendet ihn, und es wurde kein zusätzliches reales WinGet-Paket auf deinem Rechner installiert. Ein laufender WinGet-Installationsschritt wird bei Abbruch sicher zu Ende geführt, bevor sich der Hub schließt.

Die verwendeten CLI-Optionen und Manifest-Prüfsummen sind in den offiziellen Microsoft-Dokumentationen beschrieben: [Installation](https://learn.microsoft.com/en-us/windows/package-manager/winget/install), [Quellen](https://learn.microsoft.com/en-us/windows/package-manager/winget/source), [Manifestformat](https://learn.microsoft.com/en-us/windows/package-manager/package/manifest).

## Verifikation

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
.\.venv\Scripts\python.exe main.py --smoke-test --data-dir test-artifacts\ui-data --screenshot test-artifacts\ui.png
.\.venv\Scripts\python.exe main.py --smoke-test --check-integrations --data-dir test-artifacts\runtime-data
.\.venv\Scripts\python.exe tools\verify_live.py
```

Die Offline-Tests prüfen Quellen/Redirects, sichere Archive, Prüfsummen, atomare Speicherung, Installations-Rollback, Updates, manuelle Ordner, sichere Deinstallation und echte Qt-Threads. Für die Erweiterungen werden Hardwareeinstufung, Favoriten und Verlauf, fortgesetzte gemeinsame Updates, sichere Bibliotheksscans einschließlich Windows-Junctions, Metadatenerhalt, native Bibliotheksdialoge, die passende Emulatorwahl sowie BIOS-Prüfung und ZIP-Sicherung/Wiederherstellung geprüft. Spielstarts verwenden simulierte Prozesse und kleine Test-EXEs; es werden keine echten Spiele ausgeführt. `verify_live.py` lädt standardmäßig melonDS und Flycast aus den offiziellen Releases und prüft Installation, persistierte Versionen, Updates und Deinstallation im isolierten Testordner. `--keep` behält diese Testinstallationen; `--id <id>` kann mehrfach angegeben werden. Der normale Benutzerordner wird für diese Tests nicht verwendet.

Aktueller Abschlussstand: **218 Tests bestanden**. Nach jeder neuen Phase startete das Python-Programm erfolgreich; die EXE wurde mit den neuen Modulen und dem Windows-Zugangsdatenbackend neu gebaut und erfolgreich gestartet. Geprüft wurden sichere Credentials, Metadaten-/Cover-Cache, Rate-Limits und Abbruch, Auswahl unsicherer Treffer, Controller-Vorschau/Bestätigung/Backup/Rücknahme, Couch-Navigation und Gamepad-Bedienung echter Qt-Auswahldialoge. Windows Credential Manager wurde zusätzlich mit einem eigenen Dummy-Eintrag tatsächlich geprüft und dieser danach entfernt. Dienstaufrufe verwenden in den automatischen Tests simulierte Antworten; echte IGDB-/ScreenScraper-Zugangsdaten wurden nicht verwendet. Physische Controller und echte Dolphin-Konfigurationsänderungen wurden nicht auf Benutzerprofilen getestet. Details stehen in [docs/verification.md](verification.md).

Die Logo-Prüfungen bestätigen alle sechs ICO-Größen, PNG-/SVG-Auswahl, erhaltene Seitenverhältnisse und scharfe Darstellung bei 200 % Skalierung. Die Ordnerprüfungen bestätigen Pfaderhalt nach einem portablen Umzug, eigene Installationsordner, gespeicherte Auswahl und unveränderte Spiel-Dateien. Echte Spiel-/Firmware-Inhalte wurden nicht ausgeführt oder heruntergeladen. Windows 10 wurde nicht separat getestet; die Prüfung lief unter Windows 11 x64. Vor den Erweiterungen waren außerdem alle neun automatischen Katalogwege mit echten Downloads geprüft.

Ein 7z-Entpackschritt lässt sich erst nach Ende des Bibliotheksaufrufs abbrechen. Netzwerkaufrufe haben feste Zeitlimits. Nach dem Abbruch werden nur temporäre eigene Dateien entfernt; die bisherige Installation bleibt erhalten.

## Projektstruktur

```text
main.py                     Start, Instanzsperre, deutsche Qt-Dialoge
ui/                         Hauptfenster, Karten, Dialoge, QThread, Design
ui/branding.py              Gemeinsames Logo für Anwendung und Seitenleiste
ui/metadata.py              Zugangsdatenfelder, Trefferwahl und Spieldetails
ui/controllers.py           Controller-Assistent mit Livetest und Bestätigung
ui/couch.py                 Große Vollbildkacheln, Fokus und Gamepad-Bedienung
assets/                     SVG-Logo, PNG-Vorschau und Windows-Icon
core/catalog.py             Validierter JSON-Katalog
core/installer.py           Downloads, Installation, Updates, Deinstallation
core/github.py              Stabile Releases und Asset-Auswahl
core/security.py            HTTPS-Whitelist und Redirect-Prüfung
core/archives.py             Sichere Archivextraktion
core/storage.py              Atomare Installationsliste
core/shortcuts.py            Benutzerbezogene Windows-Verknüpfungen
core/winget.py               Optionaler geprüfter WinGet-Weg
core/paths.py                Ressourcen und Konfigurationspfade
core/portable.py             Portabler Datenordner und verschiebbare Pfade
core/folders.py              Emulator- und eigene Spiele-Ordner öffnen
core/state.py                Atomare Speicherung neuer JSON-Daten
core/settings.py             Favoriten, Verlauf und lokale Einstellungen
core/systemcheck.py          Hardwaredaten und grobe Einstufung
core/library.py              Scan und Metadaten eigener Spiel-Dateien
core/metadata.py             Coverdienste, Windows-Zugangsdaten und Offline-Cache
core/controllers.py          XInput und gesicherte Dolphin-Konfiguration
core/launch.py               Spielstart mit Katalogargumenten
core/profiles.py             Eigene BIOS-Dateien und Profilpfade
core/backup.py               Gezielte ZIP-Sicherung und Wiederherstellung
catalog.json                Bearbeitbarer Katalog
configs/                    Hardware-Schwellen und Dateiendungszuordnung
tools/                      Excel-Import, Icon-Erzeugung und optionaler Downloadtest
tools/make_icons.py         Logo-PNG und Windows-Icon neu erzeugen
tests/                      Offline- und native Qt-Tests
build.ps1                   Ordner-Build, Installer und portable ZIP mit Starttest
requirements.txt            Abhängigkeiten
requirements.lock.txt       Im Test verwendete exakte Versionen
docs/catalog_sources.md     Offizielle Quellen und Installationsentscheidungen
docs/new_catalog_fields.md  Spielstart-, BIOS- und Sicherungsfelder
```
