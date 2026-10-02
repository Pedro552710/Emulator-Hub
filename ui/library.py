"""Spielebibliothek und lokale Spieleordner als native Qt-Seiten."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QListView,
    QMenu,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .dialogs import label
from .metadata import CoverSettingsPanel, GameDetailsDialog, cover_icon, game_metadata


def _date_text(value: str) -> str:
    if not value:
        return "Noch nicht gespielt"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone().strftime("%d.%m.%Y %H:%M")
    except (ValueError, TypeError):
        return value


class LibraryPage(QWidget):
    launchRequested = Signal(str)
    assignmentRequested = Signal(str)
    favoriteRequested = Signal(str)
    settingsRequested = Signal()
    scanRequested = Signal()
    metadataRequested = Signal(str)
    metadataAllRequested = Signal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        self._busy = False
        self.visible_games: list[dict] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        title = QHBoxLayout()
        title.addWidget(label("Bibliothek", "sectionTitle"), 1)
        self.settings_button = QPushButton("Spieleordner wählen")
        self.settings_button.clicked.connect(self.settingsRequested.emit)
        title.addWidget(self.settings_button)
        self.scan_button = QPushButton("Bibliothek scannen")
        self.scan_button.clicked.connect(self.scanRequested.emit)
        title.addWidget(self.scan_button)
        layout.addLayout(title)
        self.metadata_all_button = QPushButton("Cover && Infos für die Bibliothek laden")
        self.metadata_all_button.clicked.connect(self.metadataAllRequested.emit)
        layout.addWidget(self.metadata_all_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(label("Eigene Spiel-Dateien direkt starten. Die Bibliothek speichert nur Pfade und Metadaten; deine Dateien bleiben unverändert.", "muted"))

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Spiel oder Dateipfad suchen …")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Spiele suchen")
        self.search.textChanged.connect(self.refresh_games)
        filters.addWidget(self.search, 1)
        self.console_filter = QComboBox()
        self.console_filter.setAccessibleName("Nach Konsole filtern")
        self.console_filter.addItem("Alle Konsolen", "all")
        self.console_filter.addItem("Noch zuordnen", "unassigned")
        for console in self.service.library.supported_consoles:
            self.console_filter.addItem(console, console)
        self.console_filter.currentIndexChanged.connect(self.refresh_games)
        filters.addWidget(self.console_filter)
        self.sort_order = QComboBox()
        self.sort_order.setAccessibleName("Spiele sortieren")
        self.sort_order.addItem("Name A–Z", "name")
        self.sort_order.addItem("Zuletzt gespielt", "last_played")
        self.sort_order.currentIndexChanged.connect(self.refresh_games)
        filters.addWidget(self.sort_order)
        self.view_mode = QComboBox()
        self.view_mode.addItem("Listenansicht", "list")
        self.view_mode.addItem("Raster mit Covern", "grid")
        self.view_mode.setAccessibleName("Bibliotheksansicht")
        self.view_mode.currentIndexChanged.connect(self._change_view)
        filters.addWidget(self.view_mode)
        layout.addLayout(filters)
        self.favorites_only = QCheckBox("Nur Favoriten")
        self.favorites_only.toggled.connect(self.refresh_games)
        layout.addWidget(self.favorites_only)
        self.results_label = label("", "footnote")
        layout.addWidget(self.results_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Spiel / Konsole", "Datei", "Zuletzt gespielt", "★", "Status"])
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setAlternatingRowColors(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setAccessibleName("Spiele nach Konsole gruppiert")
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemSelectionChanged.connect(self._update_actions)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(lambda point: self._context_menu(self.tree, point))
        self.grid = QListWidget()
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setIconSize(QSize(132, 176))
        self.grid.setGridSize(QSize(186, 246))
        self.grid.setWordWrap(True)
        self.grid.setSpacing(8)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.grid.setAccessibleName("Spiele mit Covern")
        self.grid.itemSelectionChanged.connect(self._update_actions)
        self.grid.itemDoubleClicked.connect(lambda item: self.launchRequested.emit(item.data(Qt.ItemDataRole.UserRole)) if not self._busy else None)
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(lambda point: self._context_menu(self.grid, point))
        self.views = QStackedWidget()
        self.views.addWidget(self.tree)
        self.views.addWidget(self.grid)
        layout.addWidget(self.views, 1)
        self.empty_label = label("Wähle in den Einstellungen einen oder mehrere Ordner mit deinen eigenen Spiel-Dateien und starte einen Scan.", "muted")
        layout.addWidget(self.empty_label)
        actions = QHBoxLayout()
        self.launch_button = QPushButton("Spiel starten")
        self.launch_button.setObjectName("primary")
        self.launch_button.clicked.connect(lambda: self._request(self.launchRequested))
        actions.addWidget(self.launch_button)
        self.assign_button = QPushButton("Konsole zuordnen")
        self.assign_button.clicked.connect(lambda: self._request(self.assignmentRequested))
        actions.addWidget(self.assign_button)
        self.favorite_button = QPushButton("Favorit umschalten")
        self.favorite_button.clicked.connect(lambda: self._request(self.favoriteRequested))
        actions.addWidget(self.favorite_button)
        self.metadata_button = QPushButton("Cover && Infos laden")
        self.metadata_button.clicked.connect(lambda: self._request(self.metadataRequested))
        actions.addWidget(self.metadata_button)
        self.details_button = QPushButton("Details")
        self.details_button.clicked.connect(self.show_details)
        actions.addWidget(self.details_button)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addWidget(label("Doppelklick startet ein Spiel. Bei mehrdeutigen Endungen wählst du die Konsole selbst. Spiele, BIOS und Firmware werden hier weder heruntergeladen noch verlinkt.", "footnote"))
        self.refresh_games()

    def selected_game_id(self):
        if hasattr(self, "grid") and self.view_mode.currentData() == "grid":
            item = self.grid.currentItem()
            return item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        item = self.tree.currentItem()
        return item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None

    def _request(self, signal):
        identifier = self.selected_game_id()
        if identifier and not self._busy:
            signal.emit(identifier)

    def _double_clicked(self, item, column):
        identifier = item.data(0, Qt.ItemDataRole.UserRole)
        if identifier and column != 3 and not self._busy:
            self.launchRequested.emit(identifier)

    def _clicked(self, item, column):
        identifier = item.data(0, Qt.ItemDataRole.UserRole)
        if identifier and column == 3 and not self._busy:
            self.favoriteRequested.emit(identifier)

    def _update_actions(self):
        enabled = bool(self.selected_game_id()) and not self._busy
        self.launch_button.setEnabled(enabled)
        self.assign_button.setEnabled(enabled)
        self.favorite_button.setEnabled(enabled)
        if hasattr(self, "metadata_button"):
            self.metadata_button.setEnabled(enabled and hasattr(self.service, "metadata"))
            self.details_button.setEnabled(enabled)

    def _change_view(self, *_):
        if self.views.currentWidget() == self.grid:
            identifier = self.grid.currentItem().data(Qt.ItemDataRole.UserRole) if self.grid.currentItem() else None
        else:
            identifier = self.tree.currentItem().data(0, Qt.ItemDataRole.UserRole) if self.tree.currentItem() else None
        self.views.setCurrentWidget(self.grid if self.view_mode.currentData() == "grid" else self.tree)
        if identifier:
            for row in range(self.grid.count()):
                if self.grid.item(row).data(Qt.ItemDataRole.UserRole) == identifier:
                    self.grid.setCurrentRow(row)
                    break
            for row in range(self.tree.topLevelItemCount()):
                group = self.tree.topLevelItem(row)
                for index in range(group.childCount()):
                    item = group.child(index)
                    if item.data(0, Qt.ItemDataRole.UserRole) == identifier:
                        self.tree.setCurrentItem(item)
        self._update_actions()

    def _context_menu(self, widget, point):
        item = widget.itemAt(point)
        if item is None or self._busy:
            return
        widget.setCurrentItem(item)
        if not self.selected_game_id():
            return
        menu = QMenu(self)
        menu.addAction("Spiel starten", lambda: self._request(self.launchRequested))
        menu.addAction("Details", self.show_details)
        action = menu.addAction("Cover && Infos laden", lambda: self._request(self.metadataRequested))
        action.setEnabled(hasattr(self.service, "metadata"))
        menu.addAction("Favorit umschalten", lambda: self._request(self.favoriteRequested))
        menu.addAction("Konsole zuordnen", lambda: self._request(self.assignmentRequested))
        menu.exec(widget.viewport().mapToGlobal(point))

    def show_details(self):
        identifier = self.selected_game_id()
        if identifier and not self._busy:
            GameDetailsDialog(self.service, self.service.library.get_game(identifier), self).exec()

    def set_busy(self, busy):
        self._busy = busy
        self.scan_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.metadata_all_button.setEnabled(not busy and hasattr(self.service, "metadata"))
        self._update_actions()

    def refresh_games(self, *_):
        selected = self.selected_game_id() if hasattr(self, "tree") else None
        query = self.search.text().strip().casefold()
        console = self.console_filter.currentData()
        games = self.service.library.games
        for game in games:
            game["display_title"] = game_metadata(self.service, game["id"]).get("title") or game.get("name", "")
        games = [game for game in games if
                 (console == "all" or (console == "unassigned" and not game.get("console")) or game.get("console") == console)
                 and (not self.favorites_only.isChecked() or game.get("favorite"))
                 and (not query or query in f"{game.get('name', '')} {game['display_title']} {game.get('path', '')}".casefold())]
        if self.sort_order.currentData() == "last_played":
            games.sort(key=lambda game: (game.get("last_played", ""), game.get("name", "").casefold()), reverse=True)
        else:
            games.sort(key=lambda game: game["display_title"].casefold())
        self.visible_games = games
        self.tree.clear()
        self.grid.clear()
        grouped = {}
        for game in games:
            grouped.setdefault(game.get("console") or "Noch zuordnen", []).append(game)
        for console, items in sorted(grouped.items(), key=lambda item: item[0].casefold()):
            group = QTreeWidgetItem(self.tree, [f"{console} ({len(items)})"])
            group.setFirstColumnSpanned(True)
            for game in items:
                state = "Datei fehlt" if game.get("missing") else "Konsole wählen" if not game.get("console") else "Bereit"
                item = QTreeWidgetItem(group, [game["display_title"], game.get("path", ""), _date_text(game.get("last_played", "")), "★" if game.get("favorite") else "☆", state])
                item.setData(0, Qt.ItemDataRole.UserRole, game["id"])
                item.setToolTip(1, game.get("path", ""))
                item.setToolTip(3, "Klicken, um den Favoritenstatus zu ändern")
                if game["id"] == selected:
                    self.tree.setCurrentItem(item)
                tile = QListWidgetItem(cover_icon(self.service, game["id"]), f"{'★ ' if game.get('favorite') else ''}{game['display_title']}\n{console}")
                tile.setData(Qt.ItemDataRole.UserRole, game["id"])
                tile.setToolTip(f"{game['display_title']} · {state}\nRechtsklick: Start, Details, Cover & Infos")
                self.grid.addItem(tile)
                if game["id"] == selected:
                    self.grid.setCurrentItem(tile)
            group.setExpanded(True)
        self.results_label.setText(f"{len(games)} Spiele · nach Konsole gruppiert")
        self.empty_label.setVisible(not games)
        if self.service.library.games and not games:
            self.empty_label.setText("Keine Spiele für diese Suche gefunden. Passe die Suche oder Filter an.")
        else:
            self.empty_label.setText("Wähle in den Einstellungen einen oder mehrere Ordner mit deinen eigenen Spiel-Dateien und starte einen Scan.")
        self._update_actions()


class SettingsPage(QWidget):
    foldersChanged = Signal(list)
    scanRequested = Signal()

    def __init__(self, service, parent=None):
        super().__init__(parent)
        self.service = service
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(label("Einstellungen", "sectionTitle"))
        layout.addWidget(label("Ordner mit eigenen Spiel-Dateien", "cardTitle"))
        layout.addWidget(label("Der Scan durchsucht Unterordner und übernimmt nur Dateipfade und Metadaten. Spiele werden weder kopiert noch verändert. Mehrdeutige Dateiendungen ordnest du anschließend in der Bibliothek einer Konsole zu.", "muted"))
        self.folders = QListWidget()
        self.folders.setAccessibleName("Eigene Spieleordner")
        self.folders.addItems(service.settings.get("game_folders", []))
        self.folders.setMinimumHeight(150)
        layout.addWidget(self.folders, 1)
        actions = QHBoxLayout()
        self.add_button = QPushButton("Ordner hinzufügen")
        self.add_button.clicked.connect(self._add_folder)
        actions.addWidget(self.add_button)
        self.remove_button = QPushButton("Ordner entfernen")
        self.remove_button.clicked.connect(self._remove_folder)
        actions.addWidget(self.remove_button)
        actions.addStretch()
        self.scan_button = QPushButton("Speichern und scannen")
        self.scan_button.setObjectName("primary")
        self.scan_button.clicked.connect(self.scanRequested.emit)
        actions.addWidget(self.scan_button)
        layout.addLayout(actions)
        layout.addWidget(label("Entfernte oder verschobene Spiele bleiben als Metadaten sichtbar und werden beim nächsten Scan als fehlend markiert.", "footnote"))
        layout.addWidget(label(f"Datenordner: {service.data_dir}", "footnote"))
        layout.addWidget(label("Systemcheck-Schwellen und Dateiendungen kannst du in den Konfigdateien im Datenordner anpassen. Starte Emulator Hub nach Änderungen neu.", "footnote"))
        self.cover_panel = CoverSettingsPanel(service)
        layout.addWidget(self.cover_panel)

    def roots(self):
        return [self.folders.item(row).text() for row in range(self.folders.count())]

    def _add_folder(self):
        selected = QFileDialog.getExistingDirectory(self, "Ordner mit eigenen Spiel-Dateien hinzufügen")
        if selected and selected not in self.roots():
            self.folders.addItem(selected)
            self.foldersChanged.emit(self.roots())

    def _remove_folder(self):
        row = self.folders.currentRow()
        if row >= 0:
            self.folders.takeItem(row)
            self.foldersChanged.emit(self.roots())

    def set_busy(self, busy):
        for button in (self.add_button, self.remove_button, self.scan_button):
            button.setEnabled(not busy)
        self.cover_panel.set_busy(busy)
