# Beitragen

Fehler bitte mit Windows-Version, Emulator-Hub-Version, nachvollziehbaren Schritten und dem relevanten Logauszug melden. Benutzernamen, persönliche Pfade, Kontodaten und Tokens aus Logs und Screenshots entfernen. Keine ROMs, BIOS-Dateien, Firmware, Cover ohne passende Rechte oder Emulator-Binaries anhängen.

Für Änderungen einen Branch anlegen und vorhandenen Python-/PySide6-Stil beibehalten. Die Oberfläche ist auf Deutsch; lange Aufgaben gehören in einen Hintergrundauftrag. Neue Emulatorquellen müssen offizielle HTTPS-Quellen sein und im Katalog ausdrücklich geprüft werden. Eigene Spiele werden nicht verändert.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -t . -v
.\.venv\Scripts\python.exe main.py --smoke-test --data-dir test-artifacts\contribution-data
```

Im Pull Request Problem, Änderung und durchgeführte Prüfung kurz erklären. Relevante Dokumentation und Drittanbieter-Hinweise mitpflegen. Die Abhängigkeiten und der Build werden unter Windows x64 geprüft. Release-Dateien, lokale Einstellungen und Testausgaben werden nicht eingecheckt. Beiträge werden unter der [MIT-Lizenz](LICENSE) des Projekts veröffentlicht; für übernommenen fremden Code muss dessen Lizenz erhalten bleiben.
