# Prüfbericht – 02.10.2026

Die Prüfung erfolgte lokal mit Python 3.12.4 auf Windows 11 x64. Windows 10 wurde in dieser Umgebung nicht separat gestartet.

## Vorbereitung der Veröffentlichung 1.0.0

- **227 Tests in einer sauberen Checkout-Simulation bestanden**, ohne übernommene `.venv`, Build- oder Laufzeitdateien. Python-Start mit XInput-/Credential-Backendprüfung und Audit der Kopie ebenfalls erfolgreich. Logs: `test-artifacts/ci-source-tests.log`, `ci-source-start.log`, `ci-source-audit.log`.
- **GitHub-Workflows mit Actionlint 1.7.12 geprüft.** Keine Fehler; der tatsächliche Actions-/Release-Lauf erfolgt erst nach dem Push.
- **Finaler Ordner-Build, portable ZIP und Installer erfolgreich.** EXE-Version 1.0.0 und Windows-Manifest `asInvoker`. Die entpackte ZIP legt ihre Daten relativ unter `data` an. Installation, Start und Deinstallation im isolierten Testordner erfolgreich; eigene synthetische Daten blieben erhalten, Testregistrierung entfernt. Verknüpfungen wurden mit `/NOICONS` ausgelassen. Zusätzlich Inno Setup 7.1 erfolgreich kompiliert.
- **Paketierung bereinigt:** ungenutzte VirtualKeyboard-/PDF-Plugins ausgeschlossen, ursprüngliche Lizenz-Unterordner erhalten und keine UCRT/API-Set-Kopien aus dem lokalen Java-`PATH` übernommen. Die finale EXE, ZIP und installierte EXE starteten auch nach dieser Bereinigung erfolgreich.
- **Sicherheitscheck und Git-Dateiliste:** keine echten Zugangsdaten oder persönlichen Benutzerpfade in den 111 geplanten Repository-Dateien gefunden. Die tatsächlichen lokalen Emulator-/Boot-ROM-Funde unter `test-artifacts/` sind vollständig ausgeschlossen. Details: [security-audit.md](security-audit.md), [repository-files.txt](repository-files.txt), [vollständige Änderungsliste](publication-report.md).

Die folgenden Abschnitte dokumentieren frühere interne Entwicklungsstände; deren Einzeldatei-Builds sind historische Ergebnisse. Aktuelle Releases verwenden ausschließlich `dist/EmulatorHub/EmulatorHub.exe` mit vollständigem Programmordner.

## Cover, Controller und Vollbild – 02.10.2026

### Phase 1: Cover und Spielinfos

- **34 gezielte Tests bestanden**, einschließlich 21 neuer Offline-Backendtests, nativer Cover-UI-Tests und der bisherigen Bibliotheks-/Settings-UI-Prüfungen. Geprüft: bereinigte Dateinamen, Plattformfilter und einzelne/multiple unsichere Treffer, ausschließlich sichere Credential-Backends, keine Secrets in JSON oder Protokoll, kleine erlaubte HTTPS-Bilddownloads, Bildvalidierung, atomarer Cache, wiederverwendete Treffer/Bilder, Offlinebetrieb und portable Coverpfade.
- **Rate-Limits und Abbruch geprüft:** numerisches und HTTP-Datum-`Retry-After`, keine vorzeitige Wiederholung langer Pausen, begrenzte Wiederholungen bei Verbindungsfehlern, Abbruch während einer Antwort, ScreenScraper-Minuten-/Tageskontingente und fehlende eigene Entwicklerdaten. HTTP-Anmeldungen, Dienste und Bildantworten wurden simuliert; keine echten Konto-Zugangsdaten eingegeben.
- **Optionaler Cache bleibt optional:** beschädigte JSON-Dateien und ungültige Metadatenfelder werden erklärt und vor unbeabsichtigtem Überschreiben geschützt; sie verhindern keinen Programmstart. Cacheleeren verändert weder Spiele noch Bibliotheksfavoriten, Settings oder Zugangsdaten.
- **Python-Fensterstart nach Phase 1 erfolgreich**, Exit-Code 0, `test-artifacts/cover-phase1.png`. Native Rasteransicht, Zugangsdatenbereich und Details wurden ebenfalls dargestellt; Bilder: `covers-grid-phase1.png`, `cover-settings-phase1.png`, `covers-detail-phase1.png` unter `test-artifacts/`. Testcover und Spielinfos sind lokale künstliche Testdaten.

Die Anbindungen richten sich nach den offiziellen Dokumentationen von [IGDB](https://api-docs.igdb.com/), [Twitch OAuth](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth/) und [ScreenScraper](https://www.screenscraper.fr/webapi2.php). Es wurde keine erfolgreiche Live-Anmeldung behauptet: IGDB erfordert eigene Twitch-Appdaten, ScreenScraper zusätzlich eigene freigeschaltete Entwicklerdaten. Diensttexte werden nicht automatisch übersetzt; ScreenScraper liefert nach Möglichkeit deutsche Informationen. Geheimnisse bleiben auch im portablen Modus im Windows-Anmeldeinformationsmanager.

### Phase 2: Controller-Assistent

- **23 gezielte Tests bestanden**, einschließlich 13 Controller-Backendtests, vier nativer Assistententests sowie Katalog-/Bibliotheksintegration. Die Controllerantworten wurden simuliert; Windows-XInput wird ohne zusätzliche SDL-Abhängigkeit über `ctypes` eingebunden.
- **Python-Fensterstart nach Phase 2 erfolgreich**, Exit-Code 0, `test-artifacts/controller-phase2.png`.
- Der automatische Adapter beschränkt sich auf Dolphins vorhandenes aktives `GCPadNew.ini`-Profil für GameCube-Port 1 und ein XInput-Gamepad. Vorhandene Profilstruktur und Standard-Gerät an Port 1 werden geprüft. Vorschau und Dateiänderung sind getrennt; Übernahme und Rücknahme erfordern Bestätigung. Vor dem Schreiben entstehen exakte Backups, nachträgliche externe Änderungen verhindern ein Überschreiben. Übrige Emulatoren und Wii bleiben manuell mit eigener Anleitung.

Die technischen Grenzen ergeben sich aus der [Windows-XInput-Dokumentation](https://learn.microsoft.com/en-us/windows/win32/xinput/getting-started-with-xinput) und den geprüften Dolphin-Eingabequellen. XInput unterstützt bis zu vier Anschlussnummern und Gerätetypen, liefert aber keine zuverlässigen Produktnamen; reine HID-/DirectInput-Geräte werden nicht erfasst. Es wurden keine physischen Controller angeschlossen und keine echten Benutzerprofile mit Dolphin verändert. Die Tests verwenden eigene kleine Konfigurationsdateien.

### Phase 3 und Abschlussprüfung

- **15 native Couch-Tests und vier Integrationsprüfungen bestanden.** Geprüft: Konsolen-/Spielkacheln, große lokale Cover, Tastatur, simulierte Gamepad-Tasten und Sticks, Fokus und Wiederholungen, Menü/Zurück/Esc sowie Wiederverwendung der vorhandenen Spielstartlogik und Rückkehr in das Hauptfenster. Sichtbare Covers werden in begrenzten Hintergrund-Threads geladen; ein blockierter Cover-Lesevorgang blockiert die Oberfläche nicht.
- **Auswahldialoge per Gamepad geprüft:** konsolen-/emulatorbezogene Qt-Comboauswahl, fokussierte Bestätigung und Abbruch sowie ein echter `launchRequested → QInputDialog.exec()`-Ablauf mit laufendem Poll-Timer. Nach einem Zielwechsel müssen Tasten zuerst losgelassen werden. Fremde Fenster erhalten keine Eingaben; bei inaktivem Hub wird ausschließlich die ausdrücklich gehaltene Rückkehrkombination ausgewertet.
- **Python-Fensterstart nach Phase 3 erfolgreich**, Exit-Code 0, `test-artifacts/comfort-phase3.png`. Das integrierte Vollbildfenster wurde tatsächlich geöffnet und visuell geprüft (`couch-phase3.png`), ebenso der Assistent im Dunkel-Design (`controller-assistant-phase2.png`).
- **Windows Credential Manager tatsächlich geprüft:** eigener eindeutig benannter Dummy-Testeintrag gespeichert, korrekt gelesen und wieder entfernt. Es wurden keine echten Zugangsdaten verwendet oder ausgegeben. Der Starttest mit `--check-integrations` prüft XInput und das Windows-Keyring-Backend auch ohne Konto oder Netzwerkverbindung.
- **Gesamte Testsuite: 218 Tests bestanden** (28 Sekunden). Nach der abschließenden Anpassung der Navigationsbreite wurden die neun betroffenen Fenster-/Integrationsprüfungen und der Python-Start mit Laufzeitprüfung zusätzlich erfolgreich wiederholt. `pip check` meldet keine Konflikte; der Excel-Import reproduziert auch alle Controller-Metadaten.
- **Aktuelle EXE neu gebaut und erfolgreich gestartet**, Exit-Code 0, mit `--smoke-test --check-integrations`. Eingebettet sind der aktuelle Katalog und die neuen Metadaten-/Controller-/Couch-Module sowie Pillow, Windows-Keyring und win32ctypes. Auch der Windows-Keyring-Zugriff und XInput wurden im gebauten Programm geprüft. Ergebnisbild: `test-artifacts/exe-smoke.png`.
- **Erneute Prüfung der bestehenden Umsetzung:** 36 Cover-/Bibliotheksprüfungen, 23 Controller-/Katalogprüfungen und 19 Couch-/Integrationsprüfungen bestanden. Nach jeder Gruppe startete das Python-Programm erfolgreich; auch die vorhandene EXE startete mit `--check-integrations` und erzeugte `test-artifacts/exe-comfort-recheck.png`. Der eingebettete Katalog, die Logos und die fünf Komfortmodule entsprechen dem aktuellen Projekt; alle 22 Controller-Profile stimmen mit den Importergänzungen überein. Es waren keine weiteren Programmänderungen erforderlich.

Der Hub steuert nur seine eigenen Fenster. Esc benötigt Hub-Fokus; Start+Select verlässt die Couch-Ansicht auch bei einem aktiven Emulator. Windows entscheidet über die anschließende Fokusanforderung. Die Rückkehr beendet keinen laufenden Emulator und sendet keine Eingaben an fremde Anwendungen. Echte Konto-Anmeldungen, Spielstarts, physische Controller und Windows 10 benötigen zusätzliche praktische Prüfung. Es wurden weiterhin keine Spiele, ROMs, BIOS-Dateien oder Firmware heruntergeladen oder ausgeführt.

## Logo – 02.10.2026

- **154 Tests bestanden**, einschließlich sechs neuer Logo-Prüfungen. Geprüft: alle ICO-Größen (16, 32, 48, 64, 128 und 256 Pixel), transparente Ränder, unveränderte PNG-Quelldateien, erhaltene Seitenverhältnisse, Schutz vorhandener Ausgaben bei ungültigem SVG sowie externe PNG-/SVG-Auswahl und Fallback.
- **Python-Fensterstart erfolgreich**, einschließlich Logo in der Seitenleiste. Bilder: `test-artifacts/logo-start.png` und `test-artifacts/logo-sidebar-200.png`; letzteres wurde bei 200 % Bildschirmskalierung erzeugt und geprüft.
- **Windows-AppUserModelID tatsächlich gesetzt und zurückgelesen:** `EmulatorHub.Desktop`. Die Anwendung setzt sie vor dem ersten Fenster. `pip check` meldet keine Konflikte.
- **EXE neu gebaut und erfolgreich gestartet** (Exit-Code 0, `test-artifacts/exe-smoke.png`). Die drei eingebetteten Logo-Dateien sind bytegleich mit `assets/`; das Windows-Icon in den PE-Ressourcen enthält alle sechs Größen. Die aktuelle EXE ist 52.097.949 Bytes groß.

## Ordnerbuttons – 02.10.2026

- **148 Tests bestanden**, einschließlich fünf neuer Ordnerprüfungen und drei nativer Karten-/Menütests. Geprüft: gespeicherter manueller Installationsordner, verständliche Meldung bei fehlendem Ordner, automatische Ordneranlage für nicht installierte Emulatoren, gespeicherte Auswahl und Zurücksetzen, Windows-sichere eindeutige Namen sowie portable Pfade nach einem Ordnerumzug.
- **Keine Spiel-Dateien verändert.** Die Prüfungen vergleichen eigene Testdateien vor und nach Öffnen, Ändern und Zurücksetzen. Die Bibliotheksordner bleiben unverändert. Explorer-Aufrufe und der Dokumentordner wurden für die automatischen Tests simuliert.
- **Native Darstellung geprüft**, einschließlich schmaler Zweispaltenansicht, ausgegrautem Ordnerbutton, SVG-Icons und echtem dunklem Rechtsklick-Menü. Bilder: `test-artifacts/card-folders-native.png` und `card-folders-menu.png`.
- **Python-Fensterstart erfolgreich.** Frischer Datenordner mit echtem Systemcheck; Ergebnisbild `test-artifacts/folder-buttons-start.png`.
- **Aktuelle EXE neu gebaut und erfolgreich gestartet**, einschließlich eingebetteter SVG-Symbole und QtSvg-Laufzeit. Der Build-Starttest endete mit Code 0 und erneuerte `test-artifacts/exe-smoke.png`.

## Erweiterte Version 2.0

- **140 Offline- und native Qt-Tests bestanden** (`unittest discover`, 01.10.2026). Zusätzlich zu den bisherigen Funktionen geprüft: konfigurierbare Hardwareeinstufung, unerkannte GPU, Hardware-RAM-Toleranz, persistente Favoriten/Verlauf, fortgesetzte Sammelupdates nach Fehlern, Bibliotheksscans und manuelle Konsolenzuordnung, passende Startargumente ohne Shell sowie Dateierhalt.
- **Nach jeder Phase erfolgreich gestartet.** Phase 1: 33 gezielte Tests und frischer Python-Fensterstart mit echtem Systemcheck. Phase 2: 47 gezielte Tests und erneuter Python-Fensterstart. Phase 3: Backend-, native Dialog- und Gesamtprüfungen sowie erfolgreicher Python-Fensterstart. PNGs liegen unter `test-artifacts/phase1.png`, `phase2.png`, `phase3.png` und `phase3-ui-*.png`.
- **BIOS und Sicherungen geprüft.** Eigene Testdateien, optionale BIOS-Dateien, eigene Pfade und native Portable-Markierungen; ZIP-Prüfsummen, unzulässige Profile, Traversal/Junctions, Sicherheitsbackup vor dem ersten Überschreiben, Rücknahme nach Schreibfehler, abgebrochene Sicherheitsabfrage und Schutz von Spiel-Dateien. Unlesbare Unterordner führen zu einem Fehler statt einer unvollständigen Erfolgsmeldung.
- **EXE gebaut und tatsächlich gestartet.** `dist/EmulatorHub.exe` ist 52.002.568 Bytes groß. Eingebetteter Profil-Code, aktueller Katalog und beide Standardkonfigurationen wurden zusätzlich am Build geprüft. Der reguläre EXE-Starttest erzeugte `test-artifacts/exe-smoke.png`.
- **Portabler EXE-Start und Ordnerumzug erfolgreich.** Eine isolierte EXE-Kopie mit `portable.flag` legte ihre Daten unter `data` an. Nach dem Kopieren des vollständigen Programmordners startete sie erneut mit der relativ gespeicherten Installationszuordnung. Beide Prozesse endeten mit Code 0; Ergebnis und Bildpfade stehen in `test-artifacts/portable-verification.json`. Die dafür hinterlegte minimale Test-EXE wurde nicht ausgeführt.
- **Portables Backup nach Umzug wiederhergestellt.** Einstellungen, lokale Spielepfade, Installationspfade und benutzerdefinierte Sicherungsprofilkennungen bleiben nach dem Umzug auflösbar; der Test stellte ein zuvor angelegtes ZIP im verschobenen Ordner wieder her. Externe Pfade bleiben absichtlich extern.
- **Excel-Import vollständig reproduzierbar**, einschließlich sämtlicher neuer Start-, BIOS- und Sicherungsmetadaten für alle 22 Einträge. `pip check` meldet keine Konflikte.

Es wurden keine echten Spiele oder BIOS-/Firmware-Inhalte gestartet oder heruntergeladen. Spielstarts wurden mit simulierten Prozessen und minimalen PE-Testdateien geprüft. Der Systemcheck bewertet grobe Hardwareklassen, keine tatsächliche Spielleistung. Der BIOS-Check prüft Existenz und Lesbarkeit, keine Echtheit oder Kompatibilität. Abweichende native Profilpfade erfordern die eigene Zuordnung; große HDD-Abbilder können die Sicherungsgrenze von 4 GiB überschreiten. Der Hub-Modus stellt native Emulatoren nicht automatisch auf deren eigenen portablen Modus um.

## Bereits vor den Erweiterungen geprüft

- **72 Offline- und native Qt-Tests bestanden.** Geprüft: Whitelist und Redirects, stabile Asset-Auswahl, ZIP/TAR/7z-Sicherheit, SHA-256, atomare Speicherung, Abbruch, Konfigurationserhalt, Rollback, sichere Deinstallation, manuelle Ordner, Direktdownloads, konservative WinGet-Manifeste und eine bedienbare Oberfläche während echter QThread-Arbeit.
- **Alle neun automatischen Katalogwege tatsächlich getestet.** Offizielle Downloads wurden durch den Hub aufgelöst, heruntergeladen, entpackt und als Windows-x64-EXE erkannt: Mesen, bsnes, SameBoy, melonDS, Azahar, Cemu, PPSSPP, Flycast, xemu. SHA-256 wurde bei allen sieben Quellen mit veröffentlichter Summe erfolgreich verglichen; bsnes und Cemu veröffentlichen für die geprüften Assets keine solche Summe.
- **Updateprüfung erfolgreich.** Gespeicherte Versionen wurden mit den aktuellen offiziellen stabilen Releases verglichen.
- **Echte Deinstallation erfolgreich.** melonDS und Flycast wurden im isolierten Testordner automatisch installiert und anschließend über den Hub wieder entfernt. Die Deinstallation manuell zugeordneter Ordner wird zusätzlich durch Dateierhaltungs-Tests abgesichert.
- **Excel-Import reproduzierbar.** Alle 22 Einträge wurden erneut importiert; der erzeugte Katalog entspricht dem ausgelieferten JSON.
- **Python- und EXE-Fensterstart erfolgreich.** Der einzelne PyInstaller-Build wurde tatsächlich gestartet, visuell geprüft und automatisch geschlossen. Die finale EXE ist etwa 52 MB groß und enthält den Katalog sowie Python-/Qt-Laufzeit und deutsche Qt-Dialogtexte.
- **Abhängigkeiten konsistent.** `pip check` meldet keine Konflikte. Die getesteten Versionen stehen in `requirements.lock.txt`.

Testinstallationen und PNG-Vorschauen liegen in `test-artifacts/` bzw. `ui/`. Der normale `%LOCALAPPDATA%\EmulatorHub`-Installationsordner wurde für die Downloadtests nicht benutzt. WinGet-Befehle und interaktive Direktinstaller wurden ausschließlich simuliert; es wurde kein zusätzliches Systempaket installiert.

Tests erneut ausführen:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
.\.venv\Scripts\python.exe main.py --smoke-test --data-dir test-artifacts\ui-data --screenshot test-artifacts\ui.png
.\.venv\Scripts\python.exe tools\verify_live.py
.\build.ps1
```

Die Quellenprüfung ist in [catalog_sources.md](catalog_sources.md) dokumentiert. Ein künftig verändertes Asset, fehlender Download oder unklarer Hash führt zum manuellen Fallback.
