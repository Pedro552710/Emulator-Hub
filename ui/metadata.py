"""Lokale Cover-Anzeige und ausdrückliche Auswahl externer Metadatentreffer."""

from pathlib import Path

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)

from .dialogs import label


def game_metadata(service, identifier):
    metadata = getattr(service, "metadata", None)
    if metadata is None:
        return {}
    result = metadata.get(identifier)
    return result if isinstance(result, dict) else {}


def cover_icon(service, identifier):
    """Qt lädt Cover erst bei Bedarf; der Platzhalter benötigt keine Bilddatei."""
    data = game_metadata(service, identifier)
    path = data.get("cover_path")
    if path and Path(path).is_file():
        return QIcon(str(path))
    pixmap = QPixmap(180, 240)
    pixmap.fill(QColor("#192432"))
    painter = QPainter(pixmap)
    painter.setPen(QColor("#34465c"))
    painter.drawRoundedRect(8, 8, 164, 224, 12, 12)
    painter.setPen(QColor("#91a3bb"))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "Kein Cover")
    painter.end()
    return QIcon(pixmap)


class CoverSettingsPanel(QWidget):
    saveRequested = Signal(str, object, bool)
    loadRequested = Signal(str)
    clearRequested = Signal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 0)
        layout.addWidget(label("Cover & Infos", "sectionTitle"))
        layout.addWidget(label("Optional: Lade nur Cover und Informationen aus IGDB oder ScreenScraper. Zugangsdaten liegen im Windows Credential Manager, auch im portablen Modus. Die Bibliothek bleibt ohne Konto und offline nutzbar.", "muted"))
        self.provider = QComboBox()
        self.provider.addItem("IGDB / Twitch", "igdb")
        self.provider.addItem("ScreenScraper", "screenscraper")
        self.provider.setAccessibleName("Dienst für Cover und Infos")
        self.provider.setCurrentIndex(max(0, self.provider.findData(service.settings.get("metadata_provider", "igdb"))))
        layout.addWidget(self.provider)
        self.forms = QStackedWidget()
        self.fields = {}
        definitions = {
            "igdb": [("client_id", "Twitch Client-ID", False), ("client_secret", "Twitch Client-Secret", True)],
            "screenscraper": [("username", "Benutzername", False), ("password", "Passwort", True),
                              ("developer_id", "Eigene Entwickler-ID", False), ("developer_password", "Entwicklerpasswort", True)],
        }
        for provider, fields in definitions.items():
            form = QWidget()
            rows = QFormLayout(form)
            rows.setContentsMargins(0, 0, 0, 0)
            self.fields[provider] = {}
            for key, title, secret in fields:
                field = QLineEdit()
                field.setAccessibleName(title)
                field.setEchoMode(QLineEdit.EchoMode.Password if secret else QLineEdit.EchoMode.Normal)
                self.fields[provider][key] = field
                rows.addRow(title, field)
            self.forms.addWidget(form)
        layout.addWidget(self.forms)
        self.provider.currentIndexChanged.connect(self.forms.setCurrentIndex)
        self.forms.setCurrentIndex(self.provider.currentIndex())
        layout.addWidget(label("ScreenScraper benötigt neben deinem Konto zusätzlich eigene freigeschaltete API-Entwicklerdaten. Der Hub enthält keine fremden API-Schlüssel. Beachte die Bedingungen und Kontingente des gewählten Dienstes; die Quelle wird in den Spieldetails genannt.", "footnote"))
        actions = QHBoxLayout()
        self.load_button = QPushButton("Zugangsdaten laden")
        self.load_button.clicked.connect(lambda: self.loadRequested.emit(self.provider.currentData()))
        actions.addWidget(self.load_button)
        self.save_button = QPushButton("Zugangsdaten speichern")
        self.save_button.clicked.connect(lambda: self._save(False))
        actions.addWidget(self.save_button)
        self.test_button = QPushButton("Verbindung testen")
        self.test_button.setToolTip("Leere Felder verwenden bereits sicher gespeicherte Zugangsdaten. Ausgefüllte Felder werden vor dem Test gespeichert.")
        self.test_button.clicked.connect(lambda: self._save(True))
        actions.addWidget(self.test_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.clear_button = QPushButton("Cache leeren")
        self.clear_button.clicked.connect(self.clearRequested.emit)
        layout.addWidget(self.clear_button, alignment=Qt.AlignmentFlag.AlignLeft)
        warning = getattr(getattr(service, "metadata", None), "last_warning", "")
        if not isinstance(warning, str):
            warning = ""
        self.result_label = label(warning or "Cover werden ausschließlich auf deinen Wunsch geladen.", "footnote")
        layout.addWidget(self.result_label)

    def _save(self, test):
        provider = self.provider.currentData()
        self.saveRequested.emit(provider, {key: widget.text() for key, widget in self.fields[provider].items()}, test)

    def show_credentials(self, provider, values):
        for key, widget in self.fields[provider].items():
            widget.setText(str(values.get(key, "")))
        self.result_label.setText("Gespeicherte Zugangsdaten geladen. Passwörter bleiben verdeckt.")

    def set_busy(self, busy):
        for widget in (self.load_button, self.save_button, self.test_button, self.clear_button, self.provider, self.forms):
            widget.setEnabled(not busy)


class CandidateDialog(QDialog):
    """Unsichere Treffer werden nie ohne ausdrückliche Auswahl übernommen."""

    def __init__(self, game, candidates, parent=None):
        super().__init__(parent)
        self.candidates = candidates
        self.setWindowTitle("Cover & Infos – Treffer bestätigen")
        self.resize(700, 500)
        layout = QVBoxLayout(self)
        layout.addWidget(label(f"Welcher Treffer gehört zu {game['name']}?", "sectionTitle"))
        layout.addWidget(label(f"Konsole: {game.get('console') or 'Noch zuordnen'}\nDatei: {game['path']}", "muted"))
        self.results = QListWidget()
        for candidate in candidates:
            platforms = ", ".join(str(p) for p in candidate.get("platforms", [])) or "Konsole nicht bestätigt"
            title = candidate.get("title", "Unbekannter Titel")
            year = candidate.get("year") or "Jahr unbekannt"
            item = QListWidgetItem(f"{title} · {year}\n{platforms} · Daten von {candidate.get('source', '')}")
            item.setSizeHint(QSize(0, 58))
            self.results.addItem(item)
        layout.addWidget(self.results, 1)
        layout.addWidget(label("Die Dateinamen-Suche kann ähnliche Titel finden. Es werden nur die Informationen des ausdrücklich gewählten Treffers gespeichert.", "footnote"))
        buttons = QHBoxLayout()
        stop = QPushButton("Laden beenden")
        stop.clicked.connect(lambda: self.done(2))
        buttons.addWidget(stop)
        buttons.addStretch()
        skip = QPushButton("Spiel überspringen")
        skip.clicked.connect(self.reject)
        buttons.addWidget(skip)
        self.choose_button = QPushButton("Treffer übernehmen")
        self.choose_button.setObjectName("primary")
        self.choose_button.setEnabled(False)
        self.results.currentRowChanged.connect(lambda row: self.choose_button.setEnabled(row >= 0))
        self.choose_button.clicked.connect(self.accept)
        buttons.addWidget(self.choose_button)
        layout.addLayout(buttons)

    @property
    def candidate(self):
        row = self.results.currentRow()
        return self.candidates[row] if row >= 0 else None


class GameDetailsDialog(QDialog):
    def __init__(self, service, game, parent=None):
        super().__init__(parent)
        data = game_metadata(service, game["id"])
        self.setWindowTitle("Spieldetails")
        self.resize(800, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(label(data.get("title") or game["name"], "sectionTitle"))
        body = QHBoxLayout()
        cover = QLabel()
        cover.setFixedSize(225, 300)
        cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cover.setPixmap(cover_icon(service, game["id"]).pixmap(QSize(225, 300)))
        body.addWidget(cover, alignment=Qt.AlignmentFlag.AlignTop)
        info = QVBoxLayout()
        info.addWidget(label(f"{game.get('console') or 'Konsole noch zuordnen'} · {data.get('year') or 'Jahr unbekannt'}", "muted"))
        info.addWidget(label("Genre: " + (", ".join(data.get("genres", [])) or "Nicht angegeben"), "muted"))
        description = QPlainTextEdit()
        description.setReadOnly(True)
        description.setPlainText(data.get("description") or "Noch keine Beschreibung geladen. Mit Cover & Infos laden kannst du diesen Titel suchen.")
        info.addWidget(description, 1)
        info.addWidget(label(f"Daten von {data.get('source', 'keinem Dienst – nur eigene Dateimetadaten')}", "footnote"))
        if data.get("source_url"):
            info.addWidget(label(str(data["source_url"]), "footnote"))
        body.addLayout(info, 1)
        layout.addLayout(body, 1)
        layout.addWidget(label(game["path"], "footnote"))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText("Schließen")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
