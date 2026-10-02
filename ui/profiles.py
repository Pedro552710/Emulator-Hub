"""Lokale BIOS-Prüfung und Sicherungswerkzeuge pro Emulator."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QListWidget,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from .dialogs import label


class ProfileDialog(QDialog):
    checkRequested = Signal()
    ownBiosRequested = Signal()
    defaultBiosRequested = Signal()
    backupRequested = Signal()
    restoreRequested = Signal()
    pathsRequested = Signal()

    def __init__(self, entry, profiles, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setWindowTitle(f"BIOS und Sicherung · {entry['emulator']}")
        self.resize(820, 760)
        self.setMinimumSize(670, 650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(label(entry["emulator"], "sectionTitle"))
        layout.addWidget(label("BIOS / Firmware deiner eigenen Hardware", "cardTitle"))
        layout.addWidget(label("Lege deine eigenen Dateien an den unten genannten Pfaden ab oder wähle bereits vorhandene Dateien aus. Der Checker prüft Vorhandensein und Lesbarkeit; Echtheit, Region und Kompatibilität werden nicht geprüft. Es werden keine Dateien heruntergeladen und keine Bezugsquellen verlinkt.", "muted"))
        if entry.get("bios_note"):
            layout.addWidget(label(entry["bios_note"], "footnote"))
        self.bios_report = QPlainTextEdit()
        self.bios_report.setReadOnly(True)
        self.bios_report.setMinimumHeight(130)
        self.bios_report.setPlainText("Prüfung wird vorbereitet …")
        layout.addWidget(self.bios_report, 1)
        bios_actions = QHBoxLayout()
        self.check_button = QPushButton("BIOS prüfen")
        self.check_button.clicked.connect(self.checkRequested.emit)
        bios_actions.addWidget(self.check_button)
        self.own_bios_button = QPushButton("Eigene Dateien auswählen")
        self.own_bios_button.clicked.connect(self.ownBiosRequested.emit)
        bios_actions.addWidget(self.own_bios_button)
        self.default_bios_button = QPushButton("Standardpfade prüfen")
        self.default_bios_button.clicked.connect(self.defaultBiosRequested.emit)
        bios_actions.addWidget(self.default_bios_button)
        layout.addLayout(bios_actions)
        layout.addWidget(label("Spielstände und Einstellungen sichern", "cardTitle"))
        layout.addWidget(label("Sichere die vorgesehenen Profilordner als ZIP in einem Ordner deiner Wahl. Vor einer Wiederherstellung wird der aktuelle Stand automatisch gesichert, bevor Dateien überschrieben werden.", "muted"))
        if entry.get("backup_note"):
            layout.addWidget(label(entry["backup_note"], "footnote"))
        self.profile_report = QPlainTextEdit()
        self.profile_report.setReadOnly(True)
        self.profile_report.setMaximumHeight(115)
        self.set_profiles(profiles)
        layout.addWidget(self.profile_report)
        backup_actions = QHBoxLayout()
        self.backup_button = QPushButton("ZIP-Sicherung erstellen")
        self.backup_button.setObjectName("primary")
        self.backup_button.clicked.connect(self.backupRequested.emit)
        backup_actions.addWidget(self.backup_button)
        self.restore_button = QPushButton("Wiederherstellen")
        self.restore_button.clicked.connect(self.restoreRequested.emit)
        backup_actions.addWidget(self.restore_button)
        self.paths_button = QPushButton("Sicherungspfade wählen")
        self.paths_button.clicked.connect(self.pathsRequested.emit)
        backup_actions.addWidget(self.paths_button)
        layout.addLayout(backup_actions)
        self.operation_label = label("", "footnote")
        layout.addWidget(self.operation_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        self.result_label = label("", "footnote")
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.result_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Schließen")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_profiles(self, profiles):
        text = "\n\n".join(f"{profile.get('label', 'Profil')}\n{profile['path']}" for profile in profiles)
        self.profile_report.setPlainText(text or "Für diese Installation sind keine Standardpfade hinterlegt. Wähle gezielte Spielstand- und Einstellungsordner über Sicherungspfade wählen.")

    def set_bios_report(self, rows):
        self.bios_report.setPlainText("\n\n".join(f"{row['label']}: {row['status']}\n{row.get('path', '')}\n{row.get('reason', '')}" for row in rows))

    def set_busy(self, busy):
        for button in (self.check_button, self.own_bios_button, self.default_bios_button, self.backup_button, self.restore_button, self.paths_button):
            button.setEnabled(not busy)
        self.operation_label.setText("Der Vorgang läuft im Hintergrund. Fortschritt und Protokoll werden im Hauptfenster angezeigt." if busy else "")
        self.progress_bar.setVisible(busy)
        if busy:
            self.progress_bar.setRange(0, 0)
            self.result_label.clear()

    def set_progress(self, percent, phase):
        self.operation_label.setText(phase or "Vorgang läuft …")
        self.progress_bar.setRange(0, 0 if percent < 0 else 100)
        if percent >= 0:
            self.progress_bar.setValue(max(0, min(100, percent)))


class ProfilePathsDialog(QDialog):
    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.use_defaults = False
        self.setWindowTitle("Eigene Sicherungspfade festlegen")
        self.resize(740, 460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(label("Spielstände und Einstellungen", "sectionTitle"))
        layout.addWidget(label("Wähle nur gezielte Profilordner oder einzelne Einstellungsdateien. Ganze Emulator-, Spiele- oder Benutzerordner sind dafür nicht vorgesehen. Die Auswahl verändert keine Dateien.", "muted"))
        self.paths = QListWidget()
        self.paths.addItems([str(path) for path in paths])
        layout.addWidget(self.paths, 1)
        actions = QHBoxLayout()
        folder = QPushButton("Ordner hinzufügen")
        folder.clicked.connect(self._add_folder)
        actions.addWidget(folder)
        files = QPushButton("Dateien hinzufügen")
        files.clicked.connect(self._add_files)
        actions.addWidget(files)
        remove = QPushButton("Entfernen")
        remove.clicked.connect(lambda: self.paths.takeItem(self.paths.currentRow()))
        actions.addWidget(remove)
        layout.addLayout(actions)
        defaults = QPushButton("Standardpfade aus dem Katalog verwenden")
        defaults.clicked.connect(self._defaults)
        layout.addWidget(defaults)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Speichern")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_paths(self):
        return [self.paths.item(row).text() for row in range(self.paths.count())]

    def _add(self, values):
        existing = self.selected_paths()
        for value in values:
            if value not in existing:
                self.paths.addItem(value)
                existing.append(value)

    def _add_folder(self):
        selected = QFileDialog.getExistingDirectory(self, "Gezielten Spielstand- oder Einstellungsordner auswählen")
        if selected:
            self._add([selected])

    def _add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Eigene Einstellungsdateien auswählen", "", "Alle Dateien (*)")
        self._add(paths)

    def _defaults(self):
        self.use_defaults = True
        self.accept()
