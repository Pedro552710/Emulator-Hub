# Auf GitHub veröffentlichen

[Zur Startseite](../README.md) · [Entwicklung](development.md)

## Einmalige Vorbereitung

In `LICENSE` den Copyright-Platzhalter `[DEIN NAME]` durch den gewünschten Namen ersetzen. In GitHub ein **leeres** Repository `emulator-hub` ohne automatisch erzeugte README oder Lizenz anlegen. In den folgenden Befehlen `DEIN_GITHUB_NAME` durch deinen GitHub-Namen ersetzen. Git ist erforderlich; Anmeldung und Push verwendest du mit deinem eigenen Konto.

Im Projektordner:

```powershell
git init -b main
git status --short --ignored
git add .
git diff --cached --stat
git diff --cached
git commit -m "Erste öffentliche Version von Emulator Hub"
git remote add origin https://github.com/DEIN_GITHUB_NAME/emulator-hub.git
git push -u origin main
```

Die Ausgabe vor dem Commit prüfen: `.venv/`, `build/`, `dist/`, `Output/`, `test-artifacts/`, lokale Einstellungen, Spieleordner, Cache und Logs müssen ignoriert sein. Keine Zugangsdaten, heruntergeladenen Emulatoren, ROMs, BIOS- oder Firmware-Dateien hochladen. Eine `.gitignore` entfernt bereits verfolgte Dateien nicht automatisch; hier wird bewusst ein neues Repository angelegt. Es wird keine entfernte Veröffentlichung durch die lokale Projektvorbereitung ausgelöst.

## Erstes Release

`core/version.py` enthält `1.0.0`. Ein Tag muss exakt zur dortigen Version passen. Nach erfolgreichem Test-Workflow:

```powershell
git tag -a v1.0.0 -m "Emulator Hub 1.0.0"
git push origin v1.0.0
```

`.github/workflows/release.yml` baut unter `windows-latest` mit Python 3.12 und dem Lockfile, führt Offline-Tests aus, erstellt den PyInstaller-Ordner-Build und installiert Inno Setup für den Installer. Das Release erhält `EmulatorHub-Setup.exe`, `EmulatorHub-1.0.0-portable.zip` und `SHA256SUMS.txt`. Es werden keine Emulatoren oder eigenen Benutzerdaten eingebunden. Der Release-Job besitzt `contents: write`; sein Veröffentlichungs-Schritt verwendet GitHubs kurzlebiges `GITHUB_TOKEN`. Keine persönlichen Zugangsdaten im Repository hinterlegen.

Unter **Actions** den Build beobachten und anschließend den Bereich **Releases** prüfen. Fehlerhafte Tests oder abweichende Versions-Tags verhindern die Veröffentlichung. Die Ausführung auf GitHub ist erst nach dem Push testbar; ein lokaler erfolgreicher Probe-Build ersetzt diese Prüfung nicht.

## Prüfsummen und Paketprüfung

Nach einem Download kannst du eine Datei vergleichen:

```powershell
Get-FileHash .\EmulatorHub-Setup.exe -Algorithm SHA256
Get-FileHash .\EmulatorHub-1.0.0-portable.zip -Algorithm SHA256
```

Die Werte müssen zu `SHA256SUMS.txt` des betreffenden Releases passen. Prüfsummen erkennen beschädigte oder abweichende Dateien; sie ersetzen keine digitale Signatur. Windows SmartScreen kann bei den unsignierten Paketen warnen.

Vor dem Veröffentlichen komplette ZIP entpacken, Programm starten und beim Installer optionales Desktop-Icon, Startmenü, Installation ohne Administratorrechte und Deinstallation auf einem Testsystem prüfen. Die portable ZIP enthält `portable.flag`; die installierte Variante enthält ihn nicht. Drittanbieter-Lizenzen müssen in beiden Paketen vollständig mitgegeben werden. Rechte an Screenshots, Logos und Drittanbieter-Metadaten prüfen; gecachte Spielcover sind keine Release-Ressourcen.

## Weitere Versionen

`core/version.py` und `CHANGELOG.md` aktualisieren, Tests und Build durchführen, committen und einen passenden Tag wie `v1.0.1` pushen. Setup und ZIP verwenden automatisch die zentrale Programmversion. Tags nach einer Veröffentlichung nicht nachträglich auf einen anderen Commit verschieben.
