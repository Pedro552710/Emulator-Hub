"""Das native, deutschsprachige Hauptfenster des Emulator Hub."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.catalog import LEGAL_NOTICE
from core.version import VERSION

from .branding import HubLogo
from .metadata import CandidateDialog, GameDetailsDialog
from .controllers import ControllerDialog
from .couch import CouchDialog
from .dialogs import LogDialog, ManualDialog, ShortcutDialog, label
from .theme import STYLESHEET
from .icons import folder_icon
from .library import LibraryPage, SettingsPage
from .profiles import ProfileDialog, ProfilePathsDialog
from .worker import Worker


class EmulatorCard(QFrame):
    installRequested = Signal(object)
    startRequested = Signal(object)
    uninstallRequested = Signal(object)
    officialRequested = Signal(object)
    manualRequested = Signal(object)
    favoriteRequested = Signal(object)
    profilesRequested = Signal(object)
    emulatorFolderRequested = Signal(object)
    gamesFolderRequested = Signal(object)
    gamesFolderMenuRequested = Signal(object, object)

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.entry = entry
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 19, 20, 15)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        heading.setSpacing(12)
        badge = label(self._initials(entry["emulator"]), wrap=False)
        badge.setFixedSize(43, 43)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet("background: #243b50; color: #90d8e2; border-radius: 10px; font-size: 12pt; font-weight: 700;")
        heading.addWidget(badge)
        names = QVBoxLayout()
        names.setSpacing(1)
        self.name_label = label(entry["emulator"], "cardTitle")
        names.addWidget(self.name_label)
        console = label(entry.get("konsole", ""), "console")
        names.addWidget(console)
        heading.addLayout(names, 1)
        self.favorite_button = QPushButton("☆")
        self.favorite_button.setFixedSize(34, 34)
        self.favorite_button.setObjectName("quiet")
        self.favorite_button.setAccessibleName(f"{entry['emulator']} als Favorit markieren")
        self.favorite_button.clicked.connect(lambda: self.favoriteRequested.emit(entry))
        heading.addWidget(self.favorite_button)
        layout.addLayout(heading)

        metadata = QHBoxLayout()
        self.requirement = label("PC: " + entry.get("pc_anforderung", "Unbekannt"), "badge", False)
        requirement = entry.get("pc_anforderung", "").lower()
        if "sehr hoch" in requirement:
            foreground, background = "#ffada7", "#4a303b"
        elif "hoch" in requirement:
            foreground, background = "#f2c282", "#463b2e"
        elif "mittel" in requirement:
            foreground, background = "#adbcfa", "#303951"
        else:
            foreground, background = "#96deba", "#233e36"
        self.requirement.setStyleSheet(f"color: {foreground}; background: {background};")
        metadata.addWidget(self.requirement)
        metadata.addStretch()
        self.status_label = label("Nicht installiert", "badge", False)
        metadata.addWidget(self.status_label)
        layout.addLayout(metadata)
        self.compatibility_label = label("Systemcheck noch nicht durchgeführt", "cardNote")
        layout.addWidget(self.compatibility_label)

        method = entry.get("install_methode", "manuell")
        method_text = "Manuelle Einrichtung mit Anleitung" if method == "manuell" else "Automatische Installation aus offizieller Quelle"
        if method != "manuell" and entry.get("auto_emulator"):
            method_text = f"Automatische Installation: {entry['auto_emulator']}"
        self.method_label = label(method_text, "cardNote")
        self.method_label.setToolTip("\n\n".join(str(entry.get(key, "")) for key in ("install_begruendung", "hinweis") if entry.get(key)))
        layout.addWidget(self.method_label)
        layout.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.install_button = QPushButton("Installieren")
        self.install_button.setObjectName("primary")
        self.install_button.clicked.connect(lambda: self.installRequested.emit(entry))
        self.start_button = QPushButton("Starten")
        self.start_button.clicked.connect(lambda: self.startRequested.emit(entry))
        self.uninstall_button = QPushButton("Deinstallieren")
        self.uninstall_button.setToolTip("Installation oder Registrierung entfernen")
        self.uninstall_button.clicked.connect(lambda: self.uninstallRequested.emit(entry))
        for button in (self.install_button, self.start_button, self.uninstall_button):
            button.setProperty("cardAction", True)
        self.emulator_folder_button = self._folder_button("folder", "Emulator-Ordner öffnen")
        self.emulator_folder_button.clicked.connect(lambda: self.emulatorFolderRequested.emit(entry))
        self.games_folder_button = self._folder_button("gamepad", "Spiele-Ordner öffnen")
        self.games_folder_button.clicked.connect(lambda: self.gamesFolderRequested.emit(entry))
        self.games_folder_button.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.games_folder_button.customContextMenuRequested.connect(
            lambda position: self.gamesFolderMenuRequested.emit(entry, self.games_folder_button.mapToGlobal(position))
        )
        actions.addWidget(self.install_button, 1)
        actions.addWidget(self.start_button)
        actions.addWidget(self.uninstall_button)
        actions.addWidget(self.emulator_folder_button)
        actions.addWidget(self.games_folder_button)
        layout.addLayout(actions)
        links = QHBoxLayout()
        links.setSpacing(14)
        official = QPushButton("Offizielle Seite ↗")
        official.setObjectName("quiet")
        official.clicked.connect(lambda: self.officialRequested.emit(entry))
        self.manual_button = QPushButton("Anleitung")
        self.manual_button.setObjectName("quiet")
        self.manual_button.clicked.connect(lambda: self.manualRequested.emit(entry))
        links.addWidget(official)
        links.addWidget(self.manual_button)
        links.addStretch()
        layout.addLayout(links)
        self.profiles_button = QPushButton("BIOS && Sicherung")
        self.profiles_button.setObjectName("quiet")
        self.profiles_button.clicked.connect(lambda: self.profilesRequested.emit(entry))
        layout.addWidget(self.profiles_button, 0, Qt.AlignmentFlag.AlignLeft)
        legal = label(LEGAL_NOTICE, "legal")
        layout.addWidget(legal)
        self.setMinimumHeight(270)

    @staticmethod
    def _folder_button(kind: str, tooltip: str) -> QPushButton:
        button = QPushButton()
        button.setObjectName("folderAction")
        button.setFixedSize(32, 32)
        button.setIcon(folder_icon(kind))
        button.setIconSize(QSize(20, 20))
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        return button

    @staticmethod
    def _initials(name: str) -> str:
        letters = "".join(c for c in name if c.isalnum())
        return letters[:2].upper()

    def refresh(self, service, busy: bool) -> None:
        identifier = self.entry["id"]
        installed = service.is_installed(identifier)
        recorded = identifier in service.installed
        status = service.status(identifier)
        update = "update" in status.casefold()
        self.status_label.setText(status[:1].upper() + status[1:])
        color, background = ("#f3cb87", "#443b2e") if update else (("#82dab2", "#233e36") if installed else ("#97a9c0", "#263347"))
        self.status_label.setStyleSheet(f"color: {color}; background: {background};")
        self.install_button.setText("Aktualisieren" if update else ("Installiert" if installed else "Installieren"))
        self.install_button.setEnabled(not busy and (not installed or update))
        self.start_button.setEnabled(installed and not busy)
        self.uninstall_button.setEnabled(recorded and not busy)
        self.emulator_folder_button.setEnabled(installed and hasattr(service, "open_emulator_folder"))
        self.emulator_folder_button.setToolTip("Emulator-Ordner öffnen" if installed else "Noch nicht installiert")
        self.games_folder_button.setEnabled(hasattr(service, "open_games_folder"))
        record = service.installed.get(identifier, {})
        version = record.get("version")
        tooltip = str(record.get("path", ""))
        if version:
            tooltip = f"Version {version}\n{tooltip}"
        self.status_label.setToolTip(tooltip)
        settings = getattr(service, "settings", None)
        favorite = settings is not None and identifier in settings.favorites
        self.favorite_button.setText("★" if favorite else "☆")
        self.favorite_button.setToolTip("Aus Favoriten entfernen" if favorite else "Zu Favoriten hinzufügen")
        self.favorite_button.setEnabled(settings is not None and not busy)
        self.profiles_button.setEnabled(recorded and not busy and hasattr(service, "profile_paths"))
        self.profiles_button.setToolTip("Eigene BIOS-Dateien prüfen sowie Spielstände und Einstellungen sichern" if recorded else "Installiere den Emulator zuerst oder ordne seinen Ordner zu")
        if hasattr(service, "compatibility"):
            result = service.compatibility(self.entry)
            status = result.get("status", "Unbekannt")
            reason = result.get("reason", "")
            self.compatibility_label.setText(f"{status} · {reason}")
            self.compatibility_label.setToolTip("Grobe Einschätzung, keine Garantie. Die tatsächliche Leistung hängt vom Spiel und den Emulator-Einstellungen ab.")
            color = {"Läuft gut": "#82dab2", "Grenzwertig": "#f3cb87", "Zu schwach": "#ffada7"}.get(status, "#97a9c0")
            self.compatibility_label.setStyleSheet(f"color: {color}; font-size: 8pt;")


class MainWindow(QMainWindow):
    """Qt-Fenster; alle langsamen Dienste laufen über genau einen Worker."""

    def __init__(self, service, catalog):
        super().__init__()
        self.service = service
        self.catalog = catalog
        self.worker: Worker | None = None
        self._completion = None
        self._after_job = None
        self._metadata_pending = []
        self._job_entry: dict | None = None
        self._close_pending = False
        self._columns = 0
        self._log_lines: deque[str] = deque(maxlen=1000)
        self._log_dialog: LogDialog | None = None
        self._profile_dialog: ProfileDialog | None = None
        self._couch_dialog = None
        self.cards: dict[str, EmulatorCard] = {}
        self.recent_cards: dict[str, EmulatorCard] = {}
        self.visible_entries: list[dict] = []
        self.setWindowTitle(f"Emulator Hub · {VERSION}")
        self.resize(1280, 880)
        self.setMinimumSize(1020, 720)
        self.setStyleSheet(STYLESHEET)
        self.setFont(QFont("Segoe UI", 10))
        self._build_ui()
        self._load_log()
        self._build_cards()
        self.refresh()
        self.navigation.setCurrentRow(0 if hasattr(service, "settings") else 1)
        self.statusBar().showMessage("Bereit · Windows x64 · Downloads ausschließlich aus offiziellen Quellen")
        settings = getattr(service, "settings", None)
        if hasattr(service, "systemcheck") and settings is not None and not settings.get("system_report"):
            QTimer.singleShot(0, self.systemcheck)

    def _build_ui(self):
        central = QWidget()
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.setCentralWidget(central)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(232)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 26, 20, 22)
        side.setSpacing(16)
        branding = QHBoxLayout()
        branding.setSpacing(11)
        branding.addWidget(HubLogo())
        brand_text = QVBoxLayout()
        brand_text.setSpacing(0)
        brand_text.addWidget(label("Emulator", "brand", False))
        brand_text.addWidget(label("HUB / DESKTOP", "brandSub", False))
        branding.addLayout(brand_text)
        side.addLayout(branding)
        side.addSpacing(23)
        side.addWidget(label("DEINE BIBLIOTHEK", "eyebrow"))
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.navigation.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.navigation.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._category_rows: list[tuple[str, QLabel]] = []
        categories = [("home", "Startseite"), ("all", "Alle Emulatoren"), ("installed", "Installiert")]
        if hasattr(self.service, "library"):
            categories.extend([("library", "Bibliothek"), ("settings", "Einstellungen")])
        categories.extend((name, name) for name in self.catalog.categories)
        for index, (key, text) in enumerate(categories):
            item = QListWidgetItem(self.navigation)
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setSizeHint(QSize(0, 44 if index < 2 else 41))
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(10, 0, 11, 0)
            category_label = label(text, wrap=False)
            category_label.setStyleSheet("font-size: 9pt;" if len(text) > 15 else "")
            row_layout.addWidget(category_label, 1)
            count = label("0", wrap=False)
            count.setStyleSheet("color: #8ba1b6; font-size: 8pt;")
            row_layout.addWidget(count)
            self._category_rows.append((key, count))
            self.navigation.setItemWidget(item, row)
        self.navigation.setMinimumHeight(280)
        self.navigation.currentItemChanged.connect(lambda *_: self._filter_cards())
        side.addWidget(self.navigation, 1)
        self.couch_button = QPushButton("Vollbild-Modus")
        self.couch_button.setObjectName("sidebarButton")
        self.couch_button.clicked.connect(self.show_couch)
        side.addWidget(self.couch_button)
        source_badge = label("OFFIZIELLE QUELLEN", "eyebrow")
        source_badge.setStyleSheet("color: #71c7a9; font-size: 8pt; font-weight: 700;")
        side.addWidget(source_badge)
        side.addWidget(label("Deine Konsolen.\nDeine Sammlung.\nAlles an einem Ort.", "muted"))
        logs = QPushButton("Aktivitätsprotokoll öffnen")
        logs.setObjectName("sidebarButton")
        logs.clicked.connect(self.show_logs)
        side.addWidget(logs)
        outer.addWidget(sidebar)

        main = QWidget()
        content = QVBoxLayout(main)
        content.setContentsMargins(28, 26, 25, 10)
        content.setSpacing(18)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.setSpacing(4)
        heading.addWidget(label("ALLES BEREIT FÜR DEINE NÄCHSTE SESSION", "eyebrow"))
        heading.addWidget(label("Dein Emulator Hub", "title"))
        heading.addWidget(label("Entdecken, installieren und direkt starten.", "subtitle"))
        header.addLayout(heading, 1)
        content.addLayout(header)
        toolbar = QHBoxLayout()
        self.controller_button = QPushButton("Controller einrichten")
        self.controller_button.clicked.connect(self.show_controllers)
        toolbar.addWidget(self.controller_button)
        toolbar.addStretch()
        self.systemcheck_button = QPushButton("Systemcheck")
        self.systemcheck_button.clicked.connect(self.systemcheck)
        toolbar.addWidget(self.systemcheck_button)
        self.update_all_button = QPushButton("Alle aktualisieren")
        self.update_all_button.clicked.connect(self.update_all)
        toolbar.addWidget(self.update_all_button)
        self.update_button = QPushButton("Auf Updates prüfen")
        self.update_button.clicked.connect(self.check_updates)
        toolbar.addWidget(self.update_button)
        content.addLayout(toolbar)

        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.total_value = self._stat(stats, "EMULATOREN IM KATALOG", "0")
        self.installed_value = self._stat(stats, "INSTALLIERT & STARTBEREIT", "0")
        self.updates_value = self._stat(stats, "UPDATES VERFÜGBAR", "–")
        content.addLayout(stats)
        self.system_summary = label("Systemcheck: Grobe Einschätzung, keine Garantie. Die Leistung hängt auch vom Spiel und den Einstellungen ab.", "footnote")
        content.addWidget(self.system_summary)

        self.notice = QFrame()
        notice_layout = QHBoxLayout(self.notice)
        notice_layout.setContentsMargins(12, 9, 9, 9)
        self.notice_label = label("")
        notice_layout.addWidget(self.notice_label, 1)
        dismiss = QPushButton("Schließen")
        dismiss.setObjectName("quiet")
        dismiss.clicked.connect(self.notice.hide)
        notice_layout.addWidget(dismiss)
        self.notice.hide()
        content.addWidget(self.notice)

        self.operation_frame = QFrame()
        self.operation_frame.setObjectName("operation")
        operation = QVBoxLayout(self.operation_frame)
        operation.setContentsMargins(14, 12, 14, 12)
        operation.setSpacing(8)
        operation_header = QHBoxLayout()
        self.operation_label = label("Vorgang wird vorbereitet …")
        operation_header.addWidget(self.operation_label, 1)
        self.cancel_button = QPushButton("Abbrechen")
        self.cancel_button.setObjectName("quiet")
        self.cancel_button.clicked.connect(self.cancel_job)
        operation_header.addWidget(self.cancel_button)
        operation.addLayout(operation_header)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 0)
        operation.addWidget(self.progress_bar)
        content.addWidget(self.operation_frame)
        self.operation_frame.hide()

        self.emulator_filters = QWidget()
        filters = QHBoxLayout(self.emulator_filters)
        filters.setContentsMargins(0, 0, 0, 0)
        section = QVBoxLayout()
        section.setSpacing(1)
        self.category_title = label("Alle Emulatoren", "sectionTitle", False)
        self.results_label = label("", "footnote", False)
        section.addWidget(self.category_title)
        section.addWidget(self.results_label)
        filters.addLayout(section, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Emulator oder Konsole suchen …")
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(320)
        self.search.setMaximumWidth(420)
        self.search.setAccessibleName("Emulator oder Konsole suchen")
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(100)
        self._search_timer.timeout.connect(self._filter_cards)
        self.search.textChanged.connect(lambda _: self._search_timer.start())
        filters.addWidget(self.search)
        content.addWidget(self.emulator_filters)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.card_container = QWidget()
        card_layout = QVBoxLayout(self.card_container)
        card_layout.setContentsMargins(0, 0, 8, 0)
        card_layout.setSpacing(0)
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(16)
        self.grid.setVerticalSpacing(16)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.favorites_heading = label("Favoriten", "sectionTitle")
        self.recent_heading = label("Zuletzt benutzt", "sectionTitle")
        self.favorites_empty = label("Markiere Emulatoren mit dem Stern, um sie hier griffbereit zu haben.", "muted")
        self.recent_empty = label("Hier erscheinen Emulatoren, sobald du sie gestartet hast.", "muted")
        card_layout.addLayout(self.grid)
        self.empty_label = label("Keine Emulatoren gefunden.\nPasse deine Suche an oder wähle eine andere Kategorie.", "muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setMinimumHeight(200)
        card_layout.addWidget(self.empty_label)
        card_layout.addStretch()
        self.scroll.setWidget(self.card_container)
        self._layout_timer = QTimer(self)
        self._layout_timer.setSingleShot(True)
        self._layout_timer.setInterval(0)
        self._layout_timer.timeout.connect(self._responsive_layout)
        self.scroll.viewport().installEventFilter(self)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.scroll)
        if hasattr(self.service, "library"):
            self.library_page = LibraryPage(self.service)
            self.library_page.launchRequested.connect(self.launch_game)
            self.library_page.assignmentRequested.connect(self.assign_game_console)
            self.library_page.favoriteRequested.connect(self.toggle_game_favorite)
            self.library_page.settingsRequested.connect(lambda: self.select_page("settings"))
            self.library_page.scanRequested.connect(self.scan_library)
            self.library_page.metadataRequested.connect(self.load_game_metadata)
            self.library_page.metadataAllRequested.connect(lambda: self.load_game_metadata())
            self.pages.addWidget(self.library_page)
            self.settings_page = SettingsPage(self.service)
            self.settings_page.foldersChanged.connect(self.save_game_folders)
            self.settings_page.scanRequested.connect(self.scan_library)
            self.settings_page.cover_panel.saveRequested.connect(self.save_metadata_credentials)
            self.settings_page.cover_panel.loadRequested.connect(self.load_metadata_credentials)
            self.settings_page.cover_panel.clearRequested.connect(self.clear_metadata_cache)
            self.pages.addWidget(self.settings_page)
        content.addWidget(self.pages, 1)
        footer = label("Einmal einrichten. Immer griffbereit.   ·   Installationen werden in deinem Benutzerprofil verwaltet.", "footnote")
        if hasattr(self.service, "data_dir"):
            footer.setText(f"Dein Datenordner: {self.service.data_dir}")
        content.addWidget(footer)
        outer.addWidget(main, 1)

    @staticmethod
    def _stat(layout: QHBoxLayout, title: str, value: str) -> QLabel:
        frame = QFrame()
        frame.setObjectName("stat")
        body = QVBoxLayout(frame)
        body.setContentsMargins(16, 12, 16, 12)
        body.setSpacing(2)
        number = label(value, "statValue", False)
        body.addWidget(number)
        body.addWidget(label(title, "statLabel", False))
        layout.addWidget(frame, 1)
        return number

    def _build_cards(self) -> None:
        for entry in self.catalog.items:
            card = EmulatorCard(entry, self.card_container)
            self._connect_card(card)
            self.cards[entry["id"]] = card
            recent = EmulatorCard(entry, self.card_container)
            self._connect_card(recent)
            self.recent_cards[entry["id"]] = recent

    def _connect_card(self, card) -> None:
        card.installRequested.connect(self.install)
        card.startRequested.connect(self.start_emulator)
        card.uninstallRequested.connect(self.uninstall)
        card.officialRequested.connect(self.open_official)
        card.manualRequested.connect(self.show_manual)
        card.favoriteRequested.connect(self.toggle_emulator_favorite)
        card.profilesRequested.connect(self.show_profiles)
        card.emulatorFolderRequested.connect(self.open_emulator_folder)
        card.gamesFolderRequested.connect(self.open_games_folder)
        card.gamesFolderMenuRequested.connect(self.show_games_folder_menu)

    def open_emulator_folder(self, entry):
        try:
            self.service.open_emulator_folder(entry)
        except Exception as exc:
            self._message("Emulator-Ordner konnte nicht geöffnet werden", str(exc), error=True)

    def open_games_folder(self, entry):
        try:
            self.service.open_games_folder(entry)
        except Exception as exc:
            self._message("Spiele-Ordner konnte nicht geöffnet werden", str(exc), error=True)

    def show_games_folder_menu(self, entry, position):
        menu = QMenu(self)
        change = menu.addAction("Spiele-Ordner ändern…")
        reset = menu.addAction("Auf Standard zurücksetzen")
        selected = menu.exec(position)
        if selected == change:
            self.change_games_folder(entry)
        elif selected == reset:
            try:
                self.service.reset_games_directory(entry)
            except Exception as exc:
                self._message("Standard-Spiele-Ordner konnte nicht übernommen werden", str(exc), error=True)
        menu.deleteLater()

    def change_games_folder(self, entry):
        try:
            current = self.service.games_directory(entry)
            chosen = QFileDialog.getExistingDirectory(self, "Spiele-Ordner ändern", str(current))
            if chosen:
                self.service.set_games_directory(entry, chosen)
        except Exception as exc:
            self._message("Spiele-Ordner konnte nicht gespeichert werden", str(exc), error=True)

    def _category(self) -> str:
        current = self.navigation.currentItem()
        return current.data(Qt.ItemDataRole.UserRole) if current else "home"

    def _filter_cards(self) -> None:
        category = self._category()
        library = category == "library" and hasattr(self, "library_page")
        settings_page = category == "settings" and hasattr(self, "settings_page")
        self.emulator_filters.setVisible(not library and not settings_page)
        for value in (self.total_value, self.installed_value, self.updates_value):
            value.parentWidget().setVisible(not library and not settings_page)
        self.system_summary.setVisible(not library and not settings_page)
        self.pages.setCurrentWidget(self.library_page if library else self.settings_page if settings_page else self.scroll)
        if library or settings_page:
            self.visible_entries = []
            return
        query = self.search.text().strip().casefold()
        settings = getattr(self.service, "settings", None)
        favorites = list(settings.favorites) if settings is not None else []
        recent = [item["id"] for item in settings.recent_emulators] if settings is not None else []
        self.visible_entries = [
            entry for entry in self.catalog.items
            if (category == "all" or (category == "home" and entry["id"] in favorites + recent) or (category == "installed" and self.service.is_installed(entry["id"])) or entry.get("kategorie") == category)
            and (not query or query in " ".join(str(entry.get(key, "")) for key in ("emulator", "konsole", "kategorie")).casefold())
        ]
        self.category_title.setText({"home": "Deine Startseite", "all": "Alle Emulatoren", "installed": "Installierte Emulatoren"}.get(category, category))
        count = len(self.visible_entries)
        self.results_label.setText(f"{count} {'Emulator' if count == 1 else 'Emulatoren'}" + (f" · Suche: {self.search.text().strip()}" if query else " · Offizielle Projekte"))
        self._arrange_cards()

    def _arrange_cards(self) -> None:
        columns = 2 if self.scroll.viewport().width() >= 900 else 1
        self._columns = columns
        while self.grid.count():
            self.grid.takeAt(0)
        active = {entry["id"] for entry in self.visible_entries}
        for identifier, card in self.cards.items():
            card.setVisible(identifier in active)
        for card in self.recent_cards.values():
            card.hide()
        home = self._category() == "home"
        for heading in (self.favorites_heading, self.recent_heading, self.favorites_empty, self.recent_empty):
            heading.setVisible(home)
        if home:
            settings = getattr(self.service, "settings", None)
            favorites = list(settings.favorites) if settings is not None else []
            recent = [item["id"] for item in settings.recent_emulators] if settings is not None else []
            favorite_entries = [entry for entry in self.visible_entries if entry["id"] in favorites]
            recent_entries = sorted([entry for entry in self.visible_entries if entry["id"] in recent], key=lambda entry: recent.index(entry["id"]))
            for card in self.cards.values():
                card.hide()
            row = 0
            for heading, empty, entries, cards in ((self.favorites_heading, self.favorites_empty, favorite_entries, self.cards), (self.recent_heading, self.recent_empty, recent_entries, self.recent_cards)):
                self.grid.addWidget(heading, row, 0, 1, columns)
                row += 1
                empty.setVisible(not entries)
                if not entries:
                    self.grid.addWidget(empty, row, 0, 1, columns)
                    row += 1
                for index, entry in enumerate(entries):
                    card = cards[entry["id"]]
                    card.show()
                    self.grid.addWidget(card, row + index // columns, index % columns)
                row += (len(entries) + columns - 1) // columns
        else:
            for index, entry in enumerate(self.visible_entries):
                self.grid.addWidget(self.cards[entry["id"]], index // columns, index % columns)
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if columns == 2 else 0)
        self.empty_label.setVisible(not home and not self.visible_entries)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "_layout_timer"):
            self._layout_timer.start()

    def eventFilter(self, watched, event):
        if hasattr(self, "scroll") and watched == self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            self._layout_timer.start()
        return super().eventFilter(watched, event)

    def _responsive_layout(self):
        columns = 2 if self.scroll.viewport().width() >= 900 else 1
        if columns != self._columns:
            self._arrange_cards()

    def refresh(self) -> None:
        installed_count = sum(self.service.is_installed(entry["id"]) for entry in self.catalog.items)
        update_count = sum("update" in self.service.status(entry["id"]).casefold() for entry in self.catalog.items)
        self.total_value.setText(str(len(self.catalog.items)))
        self.installed_value.setText(str(installed_count))
        self.updates_value.setText(str(update_count))
        self.updates_value.setStyleSheet("color: #f3cb87;" if update_count else "color: #91a3bb;")
        busy = self.worker is not None
        self.update_button.setEnabled(not busy)
        self.update_all_button.setEnabled(not busy and hasattr(self.service, "update_all"))
        self.systemcheck_button.setEnabled(not busy and hasattr(self.service, "systemcheck"))
        self.controller_button.setEnabled(not busy and hasattr(self.service, "library"))
        self.couch_button.setEnabled(not busy and hasattr(self.service, "library"))
        self._update_system_summary(getattr(self.service, "system_report", None))
        settings = getattr(self.service, "settings", None)
        for key, count in self._category_rows:
            number = len(set(settings.favorites + [item["id"] for item in settings.recent_emulators])) if key == "home" and settings is not None else len(self.catalog.items) if key == "all" else installed_count if key == "installed" else sum(entry.get("kategorie") == key for entry in self.catalog.items)
            count.setText(str(len(self.service.library.games)) if key == "library" else "" if key == "settings" else str(number))
        for card in list(self.cards.values()) + list(self.recent_cards.values()):
            card.refresh(self.service, busy)
        if hasattr(self, "library_page"):
            self.library_page.set_busy(busy)
            self.library_page.refresh_games()
            self.settings_page.set_busy(busy)
        if self._profile_dialog is not None:
            self._profile_dialog.set_busy(busy)
        self._filter_cards()

    def show_controllers(self):
        if self.worker is None and hasattr(self.service, "library"):
            ControllerDialog(self.service, self).exec()

    def show_couch(self):
        if self.worker is not None or not hasattr(self.service, "library"):
            return
        if self._couch_dialog is None:
            self._couch_dialog = CouchDialog(self.service, self)
            self._couch_dialog.launchRequested.connect(self.launch_game)
            self._couch_dialog.finished.connect(self._couch_closed)
        self._couch_dialog.showFullScreen()
        self._couch_dialog.raise_()
        self._couch_dialog.activateWindow()

    def _couch_closed(self, *_):
        dialog, self._couch_dialog = self._couch_dialog, None
        if dialog is not None:
            dialog.deleteLater()
        if not self._close_pending:
            self.show()
            self.raise_()
            self.activateWindow()
            self.refresh()

    def show_profiles(self, entry):
        try:
            paths = self.service.profile_paths(entry)
        except Exception as exc:
            self._message("Profilpfade konnten nicht gelesen werden", str(exc), error=True)
            return
        dialog = ProfileDialog(entry, paths, self)
        self._profile_dialog = dialog
        dialog.checkRequested.connect(lambda: self.check_bios(entry))
        dialog.ownBiosRequested.connect(lambda: self.select_own_bios(entry))
        dialog.defaultBiosRequested.connect(lambda: self.reset_own_bios(entry))
        dialog.backupRequested.connect(lambda: self.create_backup(entry))
        dialog.restoreRequested.connect(lambda: self.restore_backup(entry))
        dialog.pathsRequested.connect(lambda: self.select_profile_paths(entry))
        self.check_bios(entry)
        dialog.exec()
        self._profile_dialog = None
        dialog.deleteLater()

    def check_bios(self, entry):
        def complete(rows):
            if self._profile_dialog is not None and self._profile_dialog.entry["id"] == entry["id"]:
                self._profile_dialog.set_bios_report(rows)
            self._notify("BIOS-Prüfung abgeschlossen. Der Checker prüft nur eigene lokale Dateien. Details im Protokoll.")
        self._run_job(f"{entry['emulator']} · Eigene BIOS-Dateien prüfen …", lambda progress, log, event: self.service.check_bios(entry, progress, log, event), complete)

    def select_own_bios(self, entry):
        paths, _ = QFileDialog.getOpenFileNames(self._profile_dialog or self, "Eigene BIOS- oder Firmware-Dateien auswählen", "", "Eigene Dateien (*)")
        if not paths:
            return
        try:
            overrides = self.service.settings.get("bios_overrides", {})
            overrides[entry["id"]] = [{"path": str(Path(path).absolute()), "label": Path(path).name} for path in paths]
            self.service.settings.set("bios_overrides", overrides)
        except Exception as exc:
            self._message("Eigene BIOS-Dateien konnten nicht zugeordnet werden", str(exc), error=True)
            return
        self.check_bios(entry)

    def reset_own_bios(self, entry):
        try:
            overrides = self.service.settings.get("bios_overrides", {})
            overrides.pop(entry["id"], None)
            self.service.settings.set("bios_overrides", overrides)
        except Exception as exc:
            self._message("Standardpfade konnten nicht übernommen werden", str(exc), error=True)
            return
        self.check_bios(entry)

    def select_profile_paths(self, entry):
        try:
            profiles = self.service.profile_paths(entry)
            dialog = ProfilePathsDialog([profile["path"] for profile in profiles], self._profile_dialog or self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            overrides = self.service.settings.get("profile_overrides", {})
            if dialog.use_defaults:
                overrides.pop(entry["id"], None)
            else:
                overrides[entry["id"]] = {"backup_paths": dialog.selected_paths()}
            from core.profiles import profile_paths
            candidate = profile_paths(entry, self.service.installed.get(entry["id"]), self.service.data_dir, {"profile_overrides": overrides, "game_folders": self.service.settings.get("game_folders", [])})
            self.service.settings.set("profile_overrides", overrides)
        except Exception as exc:
            self._message("Sicherungspfade konnten nicht gespeichert werden", str(exc), error=True)
            return
        if self._profile_dialog is not None:
            self._profile_dialog.set_profiles(candidate)

    def create_backup(self, entry):
        folder = QFileDialog.getExistingDirectory(self._profile_dialog or self, "Zielordner für die ZIP-Sicherung wählen", str(self.service.data_dir / "backups"))
        if not folder:
            return

        def complete(path):
            text = f"ZIP-Sicherung erstellt: {path}"
            self._notify(text)
            if self._profile_dialog is not None:
                self._profile_dialog.result_label.setText(text)

        self._run_job(f"{entry['emulator']} · Spielstände und Einstellungen sichern …", lambda progress, log, event: self.service.backup(entry, Path(folder), progress, log, event), complete)

    def restore_backup(self, entry):
        archive, _ = QFileDialog.getOpenFileName(self._profile_dialog or self, "Emulator-Hub-ZIP-Sicherung auswählen", str(self.service.data_dir / "backups"), "ZIP-Sicherungen (*.zip)")
        if not archive:
            return
        box = QMessageBox(self._profile_dialog or self)
        box.setWindowTitle("Sicherung wiederherstellen")
        box.setText(f"Spielstände und Einstellungen von {entry['emulator']} wiederherstellen?")
        box.setInformativeText(f"Sicherung: {archive}\n\nDer aktuelle Stand wird zuerst als Sicherheitsbackup im Hub-Datenordner gesichert. Erst danach werden Dateien aus dieser ZIP-Sicherung übernommen. Bestehende Dateien können dabei überschrieben werden. Schließe den Emulator vor der Wiederherstellung.")
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setIcon(QMessageBox.Icon.Warning)
        restore = box.addButton("Sichern und wiederherstellen", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() != restore:
            return

        def complete(result):
            text = f"{result.get('count', 0)} Dateien wiederhergestellt. Sicherheitsbackup: {result.get('safety_backup', '')}"
            self._notify(text)
            if self._profile_dialog is not None:
                self._profile_dialog.result_label.setText(text)

        self._run_job(f"{entry['emulator']} · Sicherheitsbackup und Wiederherstellung …", lambda progress, log, event: self.service.restore_backup(entry, Path(archive), progress, log, event), complete)

    def select_page(self, key):
        for row in range(self.navigation.count()):
            if self.navigation.item(row).data(Qt.ItemDataRole.UserRole) == key:
                self.navigation.setCurrentRow(row)
                return

    def save_game_folders(self, roots):
        try:
            self.service.library.set_roots(roots)
        except Exception as exc:
            self._message("Spieleordner konnten nicht gespeichert werden", str(exc), error=True)
            self.settings_page.folders.clear()
            self.settings_page.folders.addItems(self.service.settings.get("game_folders", []))

    def scan_library(self):
        roots = self.settings_page.roots()
        if not roots:
            self._notify("Füge zuerst einen Ordner mit deinen eigenen Spiel-Dateien in den Einstellungen hinzu.")
            self.select_page("settings")
            return
        try:
            self.service.library.set_roots(roots)
        except Exception as exc:
            self._message("Spieleordner konnten nicht gespeichert werden", str(exc), error=True)
            return
        self.select_page("library")

        def complete(result):
            text = f"Scan abgeschlossen: {result.get('total', 0)} Spiele, {result.get('added', 0)} neu, {result.get('ambiguous', 0)} noch zuzuordnen, {result.get('missing', 0)} Dateien fehlen."
            errors = result.get("errors", [])
            if errors:
                text += f" {len(errors)} Ordner/Dateien konnten nicht vollständig gelesen werden. Details im Aktivitätsprotokoll."
            self._notify(text, error=bool(errors))

        self._run_job("Bibliothek · Eigene Spiel-Dateien werden gesucht …", lambda progress, log, event: self.service.library.scan(roots, progress, log, event), complete)

    def _game(self, identifier):
        return next((game for game in self.service.library.games if game["id"] == identifier), None)

    def save_metadata_credentials(self, provider, values, test=False):
        if self.worker is not None:
            return
        has_values = any(str(value).strip() for value in values.values())
        if (has_values or not test) and not all(str(value).strip() for value in values.values()):
            self._notify("Bitte alle Zugangsdaten des Dienstes eintragen oder zuerst die gespeicherten Zugangsdaten laden.", error=True)
            return

        def operation(progress, log, event):
            progress(-1, "Zugangsdaten im Windows Credential Manager speichern …")
            if has_values:
                self.service.metadata.save_credentials(provider, values)
            self.service.settings.set("metadata_provider", provider)
            return self.service.metadata.test_connection(provider, progress, log, event) if test else None

        def complete(result):
            text = "Verbindung erfolgreich getestet." if test else "Zugangsdaten im Windows Credential Manager gespeichert."
            self.settings_page.cover_panel.result_label.setText(text)
            self._notify(text)

        self._run_job("Cover & Infos · Verbindung testen …" if test else "Cover & Infos · Zugangsdaten speichern …", operation, complete)

    def load_metadata_credentials(self, provider):
        self._run_job("Cover & Infos · Zugangsdaten aus Windows laden …",
                      lambda progress, log, event: self.service.metadata.load_credentials(provider),
                      lambda result: self.settings_page.cover_panel.show_credentials(provider, result))

    def clear_metadata_cache(self):
        box = QMessageBox(self)
        box.setWindowTitle("Cover-Cache leeren")
        box.setText("Lokal gespeicherte Cover und Dienst-Metadaten entfernen?")
        box.setInformativeText("Deine Spiel-Dateien, Bibliothekszuordnungen, Favoriten und Zugangsdaten bleiben erhalten. Cover und Infos müssen anschließend erneut geladen werden.")
        clear = box.addButton("Cache leeren", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() == clear:
            self._run_job("Cover & Infos · Cache leeren …", lambda progress, log, event: self.service.metadata.clear_cache(),
                          lambda result: self._notify("Cover- und Metadaten-Cache geleert."))

    def load_game_metadata(self, identifier=None):
        if self.worker is not None or not hasattr(self.service, "metadata"):
            return
        games = [self._game(identifier)] if identifier else self.service.library.games
        games = [game for game in games if game is not None and not game.get("missing")]
        if identifier and games and not games[0].get("console"):
            if not self.assign_game_console(identifier):
                return
            games = [self._game(identifier)]
        cached = [game for game in games if self.service.metadata.get(game["id"])]
        games = [game for game in games if game.get("console") and not self.service.metadata.get(game["id"])]
        if not games:
            if identifier and cached:
                GameDetailsDialog(self.service, cached[0], self).exec()
            else:
                self._notify("Alle zugeordneten Spiele sind bereits im Cache. Ordne unbekannte Konsolen zuerst zu; für neue Abfragen kannst du den Cache leeren.")
            return
        provider = self.settings_page.cover_panel.provider.currentData()
        self._metadata_pending = []

        def operation(progress, log, event):
            from core.errors import Cancelled
            self.service.metadata.test_connection(provider, lambda percent, phase: progress(0, phase), log, event)
            result = {"saved": 0, "pending": [], "failed": 0, "cancelled": False}
            for index, game in enumerate(games):
                if event.is_set():
                    result["cancelled"] = True
                    break

                def overall(percent, phase, index=index):
                    fraction = max(0, min(100, percent)) / 100
                    progress(int(100 * (index + fraction) / len(games)), f"{index + 1}/{len(games)} · {game['name']} · {phase}")
                try:
                    candidates = self.service.metadata.search(game, provider, overall, log, event)
                    if not candidates:
                        log(f"{game['name']}: Kein passender Treffer gefunden.")
                    elif candidates[0].get("requires_confirmation", True):
                        result["pending"].append((game, candidates))
                    else:
                        self.service.metadata.choose(game["id"], candidates[0], overall, log, event)
                        result["saved"] += 1
                except Cancelled:
                    result["cancelled"] = True
                    break
                except Exception as exc:
                    result["failed"] += 1
                    log(f"{game['name']}: {exc}")
                progress(int(100 * (index + 1) / len(games)), f"Cover & Infos · {index + 1}/{len(games)} Spiele bearbeitet")
            return result

        def complete(result):
            text = f"Cover & Infos: {result['saved']} gespeichert, {len(result['pending'])} Treffer zu bestätigen, {result['failed']} Fehler."
            if result["cancelled"]:
                text += " Laden abgebrochen; bereits gespeicherte Informationen bleiben verfügbar."
            self._notify(text, error=bool(result["failed"]))
            if result["pending"] and not result["cancelled"]:
                self._metadata_pending = result["pending"]
                self._after_job = self._confirm_metadata_candidate

        self._run_job("Cover & Infos · Bibliothek durchsuchen …", operation, complete)

    def _confirm_metadata_candidate(self):
        if self._close_pending or not self._metadata_pending:
            return
        game, candidates = self._metadata_pending.pop(0)
        dialog = CandidateDialog(game, candidates, self)
        result = dialog.exec()
        if result == 2:
            self._metadata_pending.clear()
            self._notify("Laden beendet. Bereits gespeicherte Cover und Infos bleiben verfügbar.")
        elif result != QDialog.DialogCode.Accepted or dialog.candidate is None:
            QTimer.singleShot(0, self._confirm_metadata_candidate)
        else:
            candidate = dialog.candidate

            def complete(metadata):
                self._notify(f"Cover & Infos für {metadata.get('title') or game['name']} gespeichert.")
                if metadata.get("cover_warning"):
                    self._notify(f"Infos gespeichert. {metadata['cover_warning']}", error=True)
                if self._metadata_pending:
                    self._after_job = self._confirm_metadata_candidate

            self._run_job(f"Cover & Infos · {game['name']} speichern …",
                          lambda progress, log, event: self.service.metadata.choose(game["id"], candidate, progress, log, event), complete)

    def assign_game_console(self, identifier):
        game = self._game(identifier)
        if game is None:
            return False
        candidates = game.get("candidates", [])
        consoles = list(dict.fromkeys(candidates + self.service.library.supported_consoles))
        current = consoles.index(game["console"]) if game.get("console") in consoles else 0
        chosen, accepted = QInputDialog.getItem(self, "Konsole zuordnen", f"Zu welcher Konsole gehört {game['name']}?\nDatei: {game['path']}", consoles, current, False)
        if not accepted or not chosen:
            return False
        try:
            self.service.library.set_console(identifier, chosen)
        except Exception as exc:
            self._message("Konsole konnte nicht zugeordnet werden", str(exc), error=True)
            return False
        self.refresh()
        return True

    def toggle_game_favorite(self, identifier):
        try:
            self.service.library.toggle_favorite(identifier)
        except Exception as exc:
            self._message("Spiel-Favorit konnte nicht gespeichert werden", str(exc), error=True)
        else:
            self.refresh()

    def launch_game(self, identifier):
        if self.worker is not None:
            self._notify("Bitte warte, bis der laufende Vorgang abgeschlossen ist.")
            return
        game = self._game(identifier)
        if game is None:
            return
        if game.get("missing"):
            self._notify("Die eigene Spiel-Datei fehlt. Prüfe den gespeicherten Dateipfad und scanne den Spieleordner erneut.", error=True)
            return
        if not game.get("console"):
            if not self.assign_game_console(identifier):
                return
            game = self._game(identifier)
        from core.launch import compatible_entries
        entries = compatible_entries(self.catalog, game["console"])
        if not entries:
            self._notify("Für diese Konsole ist kein passender Emulator im Katalog hinterlegt. Wähle eine andere Zuordnung oder ergänze den Katalog.", error=True)
            return
        installed = [entry for entry in entries if self.service.is_installed(entry["id"])]
        choices = installed or entries
        chosen = next((entry for entry in choices if entry["id"] == game.get("emulator_id")), choices[0])
        if len(choices) > 1:
            names = [f"{entry['emulator']} · {entry['konsole']}" for entry in choices]
            name, accepted = QInputDialog.getItem(self, "Emulator wählen", f"{game['name']} mit welchem Emulator starten?", names, choices.index(chosen), False)
            if not accepted:
                return
            chosen = choices[names.index(name)]
        if not installed:
            box = QMessageBox(self)
            box.setWindowTitle("Passenden Emulator installieren")
            box.setText(f"{chosen['emulator']} ist noch nicht installiert.")
            box.setInformativeText("Installiere den Emulator und starte dein Spiel anschließend erneut aus der Bibliothek.")
            install = box.addButton("Installieren", QMessageBox.ButtonRole.AcceptRole)
            cancel = box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(install)
            box.exec()
            if box.clickedButton() == install:
                self.install(chosen)
            return
        try:
            self.service.launch_game(identifier, chosen["id"])
        except Exception as exc:
            self._append_log(f"Spielstart fehlgeschlagen: {exc}")
            self._message("Spiel konnte nicht gestartet werden", str(exc), error=True)
        else:
            self._append_log(f"{game['name']} mit {chosen['emulator']} gestartet.")
            self.statusBar().showMessage(f"{game['name']} wurde gestartet.", 6000)
            warning = getattr(self.service.library, "last_warning", "")
            launch_note = chosen.get("launch_note")
            if launch_note:
                self._append_log(str(launch_note))
                self._notify(f"{game['name']} wurde an {chosen['emulator']} übergeben. {launch_note}")
            if warning:
                self._append_log(warning)
                self._notify(warning, error=True)
            self.refresh()

    def _load_log(self) -> None:
        try:
            path = Path(self.service.log_path)
            if path.exists():
                with path.open("rb") as source:
                    source.seek(max(0, path.stat().st_size - 150_000))
                    self._log_lines.extend(source.read().decode("utf-8", errors="replace").splitlines()[-700:])
        except OSError:
            pass

    @Slot(str)
    def _append_log(self, text: str) -> None:
        text = str(text)
        line = f"[{datetime.now():%H:%M:%S}] {text}"
        self._log_lines.append(line)
        if self._log_dialog is not None:
            self._log_dialog.append(line)

    @Slot()
    def show_logs(self) -> None:
        if self._log_dialog is None:
            self._log_dialog = LogDialog(list(self._log_lines), Path(self.service.log_path), self)
        self._log_dialog.show()
        self._log_dialog.raise_()
        self._log_dialog.activateWindow()

    def _notify(self, text: str, error: bool = False) -> None:
        self.notice_label.setText(text)
        self.notice.setStyleSheet("QFrame { background: #3d2833; border-radius: 8px; }" if error else "QFrame { background: #20392f; border-radius: 8px; }")
        self.notice.show()

    def _message(self, title: str, text: str, error: bool = False) -> None:
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setIcon(QMessageBox.Icon.Warning if error else QMessageBox.Icon.Information)
        close = box.addButton("Schließen", QMessageBox.ButtonRole.AcceptRole)
        box.setDefaultButton(close)
        box.exec()

    def _run_job(self, title: str, operation, completion, entry: dict | None = None) -> None:
        if self.worker is not None:
            self._notify("Bitte warte, bis der laufende Vorgang abgeschlossen ist.")
            return
        self._completion = completion
        self._job_entry = entry
        self.worker = Worker(operation, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self._append_log)
        self.worker.success.connect(self._on_success)
        self.worker.failure.connect(self._on_failure)
        self.worker.finished.connect(self._on_finished)
        self.notice.hide()
        self.operation_label.setText(title)
        self.progress_bar.setRange(0, 0)
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText("Abbrechen")
        self.operation_frame.show()
        self._append_log(title)
        self.refresh()
        self.statusBar().showMessage(title)
        self.worker.start()

    @Slot(int, str)
    def _on_progress(self, percent: int, phase: str) -> None:
        if percent < 0:
            self.progress_bar.setRange(0, 0)
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(max(0, min(100, percent)))
        self.operation_label.setText(phase or "Vorgang läuft …")
        if self._profile_dialog is not None:
            self._profile_dialog.set_progress(percent, phase)

    @Slot(object)
    def _on_success(self, result) -> None:
        if self._completion is not None:
            self._completion(result)

    @Slot(str)
    def _on_failure(self, message: str) -> None:
        self._append_log(f"Fehler: {message}")
        cancelled = bool(self.worker is not None and self.worker.cancel_event.is_set())
        self._notify(message, error=not cancelled)
        if self._profile_dialog is not None:
            self._profile_dialog.result_label.setText(message)
        if self._close_pending or cancelled:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Vorgang nicht abgeschlossen")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(message)
        box.setTextFormat(Qt.TextFormat.PlainText)
        guide = None
        failed_entry = self._job_entry
        if failed_entry is not None:
            box.setInformativeText("Du kannst den Emulator auch anhand der offiziellen Anleitung selbst einrichten.")
            guide = box.addButton("Anleitung öffnen", QMessageBox.ButtonRole.ActionRole)
        box.addButton("Schließen", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if guide is not None and box.clickedButton() == guide:
            # finished wird danach zugestellt; der Registrierungsauftrag darf erst
            # starten, wenn der alte Thread zuverlässig beendet ist.
            QTimer.singleShot(0, lambda: self.show_manual(failed_entry))

    @Slot()
    def _on_finished(self) -> None:
        worker = self.worker
        self.worker = None
        self._completion = None
        self._job_entry = None
        if worker is not None:
            worker.deleteLater()
        self.operation_frame.hide()
        self.refresh()
        self.statusBar().showMessage("Bereit · Downloads ausschließlich aus offiziellen Quellen")
        after_job, self._after_job = self._after_job, None
        if self._close_pending:
            QTimer.singleShot(0, self.close)
        elif after_job is not None:
            QTimer.singleShot(0, after_job)

    @Slot()
    def cancel_job(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.cancel_button.setText("Wird beendet …")
            self.operation_label.setText("Abbruch angefordert. Der laufende Schritt wird sicher beendet …")
            self._append_log("Abbruch angefordert.")

    @Slot(object)
    def install(self, entry: dict) -> None:
        if entry.get("install_methode", "manuell") == "manuell":
            self.show_manual(entry)
            return
        dialog = ShortcutDialog(entry, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        shortcuts = dialog.shortcuts
        self._run_job(
            f"{entry['emulator']} · Installation wird vorbereitet …",
            lambda progress, log, event: self.service.install(entry, progress, log, event, shortcuts=shortcuts),
            lambda _: self._notify(f"{entry['emulator']} ist installiert und bereit zum Starten."),
            entry=entry,
        )

    @Slot(object)
    def show_manual(self, entry: dict) -> None:
        dialog = ManualDialog(
            entry,
            lambda: self.open_official(entry),
            lambda folder: self.register_manual(entry, folder),
            self,
            allow_register=self.worker is None,
        )
        dialog.exec()

    def register_manual(self, entry: dict, folder: Path) -> None:
        self._run_job(
            f"{entry['emulator']} · Installationsordner wird geprüft …",
            lambda progress, log, event: self.service.register_manual(entry, folder),
            lambda _: self._notify(f"{entry['emulator']} wurde mit deinem Installationsordner verknüpft."),
        )

    @Slot(object)
    def start_emulator(self, entry: dict) -> None:
        try:
            self.service.start(entry)
        except Exception as exc:
            self._append_log(f"Start fehlgeschlagen: {exc}")
            self._message("Emulator konnte nicht gestartet werden", str(exc), error=True)
        else:
            self._append_log(f"{entry['emulator']} gestartet.")
            self.statusBar().showMessage(f"{entry['emulator']} wurde gestartet.", 6000)
            self.refresh()

    @Slot(object)
    def toggle_emulator_favorite(self, entry: dict) -> None:
        try:
            self.service.settings.toggle_favorite(entry["id"])
        except Exception as exc:
            self._message("Favorit konnte nicht gespeichert werden", str(exc), error=True)
        else:
            self.refresh()

    @Slot()
    def systemcheck(self) -> None:
        if not hasattr(self.service, "systemcheck"):
            return

        def complete(report):
            self._notify("Systemcheck abgeschlossen. Die Markierung an jedem Emulator ist eine grobe Einschätzung, keine Garantie. Details im Aktivitätsprotokoll.")
            self._update_system_summary(report)

        self._run_job(
            "Systemcheck · CPU, Grafikkarte und Arbeitsspeicher werden geprüft …",
            lambda progress, log, event: self.service.systemcheck(progress, log, event),
            complete,
        )

    def _update_system_summary(self, report) -> None:
        if not isinstance(report, dict):
            return
        cpu = str(report.get("cpu_name", report.get("cpu", "CPU unbekannt")))
        gpus = report.get("gpus")
        if not isinstance(gpus, list):
            gpus = []
        gpu = " / ".join(str(item.get("name", "Unbekannte GPU")) for item in gpus if isinstance(item, dict)) or str(report.get("gpu_name", report.get("gpu", "GPU unbekannt")))
        ram = report.get("ram_gb")
        detail = f"{cpu} · {gpu}" + (f" · {ram:g} GiB RAM" if isinstance(ram, (int, float)) else "")
        self.system_summary.setText(f"{detail}\nGrobe Einschätzung, keine Garantie. Die Leistung hängt auch vom Spiel und den Einstellungen ab.")
        warnings = report.get("warnings")
        if not isinstance(warnings, list):
            warnings = []
        self.system_summary.setToolTip("\n".join(str(warning) for warning in warnings))

    @Slot()
    def update_all(self) -> None:
        if not hasattr(self.service, "update_all"):
            return
        if not self.service.installed:
            self._notify("Installiere zuerst einen Emulator, um alle Installationen aktualisieren zu können.")
            return

        def complete(result):
            updated = len(result.get("updated", []))
            failed = result.get("failed", {})
            skipped = len(result.get("skipped", []))
            state = "abgebrochen" if result.get("cancelled") else "abgeschlossen"
            text = f"Aktualisierung {state}: {updated} aktualisiert, {skipped} unverändert oder manuell, {len(failed)} fehlgeschlagen."
            if failed:
                text += " Andere Emulatoren wurden weiter bearbeitet. Details im Aktivitätsprotokoll."
            self._notify(text, error=bool(failed))

        self._run_job(
            "Alle aktualisieren · Installierte Emulatoren werden nacheinander geprüft …",
            lambda progress, log, event: self.service.update_all(progress, log, event),
            complete,
        )

    @Slot(object)
    def open_official(self, entry: dict) -> None:
        try:
            self.service.open_official(entry)
        except Exception as exc:
            self._message("Offizielle Seite nicht geöffnet", str(exc), error=True)

    @Slot(object)
    def uninstall(self, entry: dict) -> None:
        record = self.service.installed.get(entry["id"], {})
        managed = record.get("managed", False)
        winget = record.get("method") == "winget"
        explanation = (
            "Der von Emulator Hub verwaltete Installationsordner einschließlich aller darin gespeicherten Dateien wird gelöscht. Zugehörige Verknüpfungen werden ebenfalls entfernt."
            if managed else
            "Die Registrierung in Emulator Hub und zugehörige Verknüpfungen werden entfernt. Dein manuell gewählter Installationsordner bleibt erhalten."
        )
        if winget:
            explanation = "WinGet deinstalliert das Paket für den aktuellen Benutzer. Die Hub-Zuordnung und zugehörige Verknüpfungen werden anschließend entfernt."
        box = QMessageBox(self)
        box.setWindowTitle("Emulator entfernen")
        box.setText(f"{entry['emulator']} deinstallieren?")
        box.setInformativeText(f"{explanation}\n\nOrdner: {record.get('path', 'Unbekannt')}")
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setIcon(QMessageBox.Icon.Warning)
        remove = box.addButton("Deinstallieren" if managed or winget else "Registrierung entfernen", QMessageBox.ButtonRole.DestructiveRole)
        cancel = box.addButton("Abbrechen", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel)
        box.exec()
        if box.clickedButton() != remove:
            return
        self._run_job(
            f"{entry['emulator']} · Installation wird entfernt …",
            lambda progress, log, event: self.service.uninstall(entry, log, event),
            lambda _: self._notify(f"{entry['emulator']} wurde aus deiner Bibliothek entfernt."),
        )

    @Slot()
    def check_updates(self) -> None:
        total = sum(entry["id"] in self.service.installed for entry in self.catalog.items)
        if not total:
            self._notify("Installiere zuerst einen Emulator, um anschließend auf Updates zu prüfen.")
            return

        def complete(result):
            update_count = sum("update" in self.service.status(entry["id"]).casefold() for entry in self.catalog.items)
            checked = len(result) if isinstance(result, dict) else total
            detail = f" {checked} von {total} Installationen geprüft. Details im Aktivitätsprotokoll." if checked < total else ""
            if update_count:
                self._notify(f"Updateprüfung abgeschlossen: {update_count} {'Update verfügbar' if update_count == 1 else 'Updates verfügbar'}.{detail}")
            else:
                self._notify(f"Updateprüfung abgeschlossen. Keine neueren Versionen festgestellt.{detail}")

        self._run_job(
            "Installierte Emulatoren · Auf Updates prüfen …",
            lambda progress, log, event: self.service.check_updates(progress, log, event),
            complete,
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.worker is not None and self.worker.isRunning():
            event.ignore()
            if self._close_pending:
                return
            box = QMessageBox(self)
            box.setWindowTitle("Vorgang läuft noch")
            box.setText("Es läuft noch ein Hintergrundvorgang.")
            box.setInformativeText("Du kannst den Vorgang abbrechen. Emulator Hub schließt sich, sobald der laufende Schritt sicher beendet ist.")
            stop = box.addButton("Abbrechen und schließen", QMessageBox.ButtonRole.DestructiveRole)
            stay = box.addButton("Weiterlaufen lassen", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(stay)
            box.exec()
            if box.clickedButton() == stop:
                self._close_pending = True
                self.cancel_job()
            return
        if self._couch_dialog is not None:
            self._close_pending = True
            self._couch_dialog.reject()
        event.accept()
