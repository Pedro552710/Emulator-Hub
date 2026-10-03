# Änderungen

## 1.0.4 – 03.10.2026

- PS4 vorübergehend ausgeblendet: shadPS4 und PS4 PKG Tool bleiben mit Quellen, Anleitungen und Tests erhalten. **Ausgeblendete Einträge anzeigen** macht sie wieder sichtbar; Installationen, Einstellungen und eigene Spieleordner werden nicht gelöscht.
- WinUAE (Amiga) ergänzt: aktuelles stabiles Windows-x64-ZIP ausschließlich aus der offiziellen Downloadseite ermitteln, automatisch entpacken und auf Updates prüfen. Uneindeutige oder geänderte Seiten führen zur manuellen Anleitung; Betas bleiben ausgeschlossen.
- Amiga-Dateiendungen und belegter Start eigener `.uae`-Konfigurationen ergänzt. Kickstart wird selbst lizenziert oder gesichert und in WinUAE eingerichtet; der Hub lädt oder verlinkt keine Kickstart-ROMs, Spiele oder Workbench-Dateien.
- Excel-Katalogquelle, Importergänzungen, Dokumentation und Tests aktualisiert; standardmäßig 23 sichtbare Einträge, 25 erhaltene Datensätze in acht Kategorien.

## 1.0.3 – 03.10.2026

- PS4-Karte auf **PS4 einrichten** vereinheitlicht: bestätigter offizieller Tool-Download und Start des Hauptfensters, fünf Schritte für den shadPS4 Manager und eigener PKG-Ordnerbutton.
- shadPS4-Alteintrag als veraltet erhalten, ohne neue Hub-Installation oder Updates. Bestehende Installationen bleiben startbar; keine Nutzerdaten werden gelöscht.
- PKG-Erkennung mit kurzem Hinweis **Im PS4 PKG Tool installieren** beibehalten; Whitelist unverändert, keine Tool-Mitlieferung oder eigene Paketverarbeitung.
- Katalogquelle, Dokumentation und Tests angepasst; Version auf 1.0.3 erhöht.

## 1.0.2 – 03.10.2026

- Eigene PS4-Pakete aus Bibliotheks- und zugeordneten PS4-Spieleordnern erscheinen als „PS4-Paket – muss erst installiert werden“. Direkte Spielstarts sind gesperrt; der neue Button übergibt genau den gewählten PKG-Pfad an den externen grafischen Viewer, als Argumentliste ohne Shell.
- PS4 PKG Tool als Hilfsprogramm ergänzt: nur stabile Releases des geprüften pearlxcore-Repositories, ausdrückliche Downloadbestätigung mit Quelle, SHA-256 und Drittanbieter-/Antivirus-Hinweis sowie manuelle Alternative. Das Tool wird nicht mitgeliefert; der Hub verarbeitet keine PKG-Inhalte und enthält keine Schlüssel.
- Belegte Anleitung für Install to shadPS4 und QTLauncher, Katalogquelle, reproduzierbaren Excel-Import und Offline-Tests aktualisiert. Der belegte shadPS4-Spielstart über eigene entschlüsselte Startdateien bleibt unverändert. Keine Spiele- oder Firmware-Downloads.

## 1.0.1 – 03.10.2026

- shadPS4: Start über QTLauncher bzw. Big-Picture-Modus. Der offizielle QTLauncher bietet derzeit nur Pre-Releases und wird ausschließlich manuell eingerichtet; der automatische Kern-Download bleibt stabilen Releases vorbehalten.
- shadPS4 (PlayStation 4) ergänzt: offizieller stabiler Windows-x64-SDL-Download mit manueller Alternative und belegtem Start eigener entschlüsselter `eboot.bin`-Dateien.
- Katalogquelle, Systemcheck-Hinweis, Dokumentation und Tests um den neuen Eintrag erweitert. Keine Spiele oder Firmware werden mitgeliefert.

## 1.0.0 – 02.10.2026

Erste öffentliche Version. Die bisherigen internen Entwicklungsstände sind in dieser Veröffentlichung zusammengefasst.

- Deutscher Emulator-Katalog mit offiziellen Quellen, automatischer Installation und manueller Alternative, Updateprüfung und Ordner-Verknüpfungen.
- Favoriten, Verlauf, grober Hardware-Systemcheck und Bibliothek eigener Spiel-Dateien.
- Optionale Cover und Infos mit sicherer Zugangsdatenablage und lokalem Cache.
- XInput-Controller-Assistent, gesicherte Dolphin-Belegung und Couch-Modus mit Tastatur/Gamepad.
- BIOS-Prüfung eigener Dateien, ZIP-Sicherungen und portabler Datenmodus.
- Eigenes Controller-Logo, Windows-Ordner-Build, Installer und portable ZIP.
- Offline-Tests, Windows-Startprüfung und GitHub-Actions-Workflows für Tests und Releases.

Einschränkungen: Hardwareeinstufung bleibt eine Schätzung; reine DirectInput-/HID-Controller werden nicht automatisch erkannt. Die automatische Controllerbelegung unterstützt nur Dolphin/GameCube-Port 1. Cover-Dienste benötigen eigene Zugangsdaten; ScreenScraper zusätzlich freigeschaltete Entwickler-Zugangsdaten. Keine Emulatoren, Spiele, ROMs, BIOS-Dateien oder Firmware werden mitgeliefert.
