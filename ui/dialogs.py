"""Native Dialoge für Anleitungen, Verknüpfungen und das Protokoll."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.catalog import LEGAL_NOTICE


def label(text: str, name: str | None = None, wrap: bool = True) -> QLabel:
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    result.setWordWrap(wrap)
    if name:
        result.setObjectName(name)
    return result


class ShortcutDialog(QDialog):
    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Installation vorbereiten")
        self.setMinimumWidth(450)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(12)
        layout.addWidget(label(entry["emulator"], "sectionTitle"))
        layout.addWidget(label("Der Emulator wird im eigenen Emulator-Hub-Ordner installiert. Wähle die gewünschten Verknüpfungen.", "muted"))
        self.desktop = QCheckBox("Verknüpfung auf dem Desktop")
        self.startmenu = QCheckBox("Verknüpfung im Startmenü")
        self.startmenu.setChecked(True)
        layout.addWidget(self.desktop)
        layout.addWidget(self.startmenu)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Jetzt installieren")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setObjectName("primary")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Abbrechen")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def shortcuts(self) -> dict[str, bool]:
        return {"desktop": self.desktop.isChecked(), "startmenu": self.startmenu.isChecked()}


class ManualDialog(QDialog):
    def __init__(self, entry: dict, on_open: Callable, on_register: Callable, parent=None, allow_register: bool = True):
        super().__init__(parent)
        self.setWindowTitle(f"Anleitung · {entry['emulator']}")
        self.resize(700, 610)
        self.setMinimumSize(540, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 22)
        layout.setSpacing(12)
        layout.addWidget(label("INSTALLATION & EINRICHTUNG", "eyebrow"))
        layout.addWidget(label(entry["emulator"], "title"))
        layout.addWidget(label(entry.get("konsole", ""), "muted"))
        explanation = (
            "Für diesen Emulator erfolgt die Einrichtung manuell. Folge der offiziellen Anleitung und verknüpfe anschließend den Installationsordner."
            if entry.get("install_methode") == "manuell"
            else "Diese Anleitung hilft dir bei der manuellen Einrichtung, falls die automatische Installation nicht funktioniert."
        )
        layout.addWidget(label(explanation, "subtitle"))

        area = QScrollArea()
        area.setWidgetResizable(True)
        body = QWidget()
        steps_layout = QVBoxLayout(body)
        steps_layout.setContentsMargins(0, 8, 10, 8)
        steps_layout.setSpacing(18)
        steps = entry.get("manuelle_schritte") or [
            "Öffne die offizielle Downloadseite.",
            "Lade dort die Windows-Version herunter und folge den Anweisungen des Projekts.",
            "Wähle anschließend den Ordner mit der ausführbaren Emulator-Datei aus.",
        ]
        if isinstance(steps, str):
            steps = [steps]
        for index, step in enumerate(steps, 1):
            row = QHBoxLayout()
            row.setSpacing(14)
            number = label(f"{index:02d}", wrap=False)
            number.setFixedWidth(30)
            number.setStyleSheet("color: #62dfb6; font-size: 14pt; font-weight: 700;")
            row.addWidget(number, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(label(str(step)), 1)
            steps_layout.addLayout(row)
        note = str(entry.get("hinweis", "")).replace(LEGAL_NOTICE, "").strip()
        if note:
            steps_layout.addWidget(label(f"Hinweis: {note}", "muted"))
        steps_layout.addWidget(label(LEGAL_NOTICE, "legal"))
        steps_layout.addStretch()
        area.setWidget(body)
        layout.addWidget(area, 1)

        official = QPushButton("Offizielle Downloadseite im Browser öffnen")
        official.setObjectName("primary")
        official.clicked.connect(on_open)
        layout.addWidget(official)
        folder = QPushButton("Ordner auswählen, in den ich es entpackt habe")
        folder.setEnabled(allow_register)
        if not allow_register:
            folder.setToolTip("Bitte warte, bis der laufende Vorgang beendet ist.")

        def pick_folder():
            selected = QFileDialog.getExistingDirectory(self, "Installationsordner auswählen")
            if selected:
                self.accept()
                on_register(Path(selected))

        folder.clicked.connect(pick_folder)
        layout.addWidget(folder)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Schließen")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class LogDialog(QDialog):
    def __init__(self, lines: list[str], log_path: Path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Emulator Hub · Protokoll")
        self.resize(880, 570)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(label("Aktivitätsprotokoll", "sectionTitle"))
        layout.addWidget(label("Downloads, Einrichtung und Fehlermeldungen werden hier protokolliert.", "muted"))
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setMaximumBlockCount(1200)
        self.editor.setPlainText("\n".join(lines) or "Noch keine Aktivitäten in dieser Sitzung.")
        cursor = self.editor.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.editor.setTextCursor(cursor)
        layout.addWidget(self.editor, 1)
        path = label(str(log_path), "footnote")
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Schließen")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def append(self, text: str) -> None:
        self.editor.appendPlainText(text)
