"""Große Bibliothekskacheln mit Tastatur- und XInput-Bedienung."""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import time

from PySide6.QtCore import (
    QEasingCurve, QEvent, QObject, QPoint, QPointF, Property, QPropertyAnimation,
    QRect, QRectF, QRunnable, QSize, Qt, QThreadPool, QTimer, Signal, Slot,
)
from PySide6.QtGui import QColor, QFont, QImage, QImageReader, QKeyEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QAbstractSpinBox, QApplication, QComboBox,
    QDialog, QGridLayout, QHBoxLayout, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from core.library import PS4_PACKAGE_STATUS, is_ps4_package, game_status, WINUAE_CONFIG_STATUS

from .dialogs import label
from .theme import STYLESHEET


def _cover_image(path):
    """Nur lokale, begrenzte Cover laden; defekte Bilder bleiben Platzhalter."""
    if not isinstance(path, (str, Path)) or not str(path):
        return QImage()
    try:
        file = Path(path)
        if not file.is_file() or file.stat().st_size > 10 * 1024 * 1024:
            return QImage()
        reader = QImageReader(str(file))
        size = reader.size()
        if not size.isValid() or max(size.width(), size.height()) > 4096:
            return QImage()
        reader.setAutoTransform(True)
        reader.setScaledSize(size.scaled(QSize(800, 1100), Qt.AspectRatioMode.KeepAspectRatio))
        return reader.read()
    except (OSError, ValueError, TypeError):
        return QImage()


def _cover_pixmap(path):
    return QPixmap.fromImage(_cover_image(path))


class _CoverSignals(QObject):
    ready = Signal(int, int, str, QImage)


class _CoverWorker(QRunnable):
    def __init__(self, generation, index, key, path):
        super().__init__()
        self.generation, self.index, self.key, self.path = generation, index, key, path
        self.signals = _CoverSignals()

    def run(self):
        # QImage darf im Thread entstehen; QPixmap erst im GUI-Slot erzeugen.
        image = _cover_image(self.path)
        self.signals.ready.emit(self.generation, self.index, self.key, image)


class CouchTile(QAbstractButton):
    """Fokus ohne Geometrieänderung animieren: auch viele Kacheln bleiben ruhig."""

    focused = Signal()

    def __init__(self, title, subtitle="", cover=None, *, kind="game", parent=None):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.cover = cover or QPixmap()
        self.kind = kind
        self._focus_amount = 0.0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(f"{title}, {subtitle}" if subtitle else title)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(210 if kind == "game" else 250)
        self.setFixedHeight(340 if kind == "game" else 180)
        self.animation = QPropertyAnimation(self, b"focusAmount", self)
        self.animation.setDuration(120)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _get_focus_amount(self):
        return self._focus_amount

    def _set_focus_amount(self, value):
        self._focus_amount = float(value)
        self.update()

    focusAmount = Property(float, _get_focus_amount, _set_focus_amount)

    def set_selected(self, selected):
        target = 1.0 if selected else 0.0
        self.animation.stop()
        self.animation.setStartValue(self._focus_amount)
        self.animation.setEndValue(target)
        self.animation.start()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.focused.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        amount = self._focus_amount
        base, selected = QColor("#192432"), QColor("#23433f")
        color = QColor(*[round(base.getRgb()[i] * (1 - amount) + selected.getRgb()[i] * amount) for i in range(3)])
        border_base, border_selected = QColor("#34465c"), QColor("#62dfb6")
        border = QColor(*[round(border_base.getRgb()[i] * (1 - amount) + border_selected.getRgb()[i] * amount) for i in range(3)])
        painter.setBrush(color)
        painter.setPen(QPen(border, 1.5 + 2.5 * amount))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(3, 3, -3, -3), 16, 16)
        if self.kind == "game":
            package = self.subtitle == PS4_PACKAGE_STATUS
            art = QRectF(17, 17, self.width() - 34, self.height() - (144 if package else 106))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#111b29"))
            painter.drawRoundedRect(art, 10, 10)
            if not self.cover.isNull():
                dimensions = self.cover.size().scaled(art.size().toSize(), Qt.AspectRatioMode.KeepAspectRatio)
                target = QRectF(art.center().x() - dimensions.width() / 2,
                                art.center().y() - dimensions.height() / 2,
                                dimensions.width(), dimensions.height())
                painter.drawPixmap(target, self.cover, QRectF(self.cover.rect()))
            else:
                self._placeholder(painter, art)
            heading = QRectF(19, self.height() - (116 if package else 78), self.width() - 38, 48)
            subtitle = QRectF(19, self.height() - (66 if package else 30), self.width() - 38, 58 if package else 22)
            font_size = 16
        else:
            heading = QRectF(23, 30, self.width() - 46, 88)
            subtitle = QRectF(23, 133, self.width() - 46, 27)
            font_size = 22
        painter.setPen(QColor("#edf3fa"))
        painter.setFont(QFont("Segoe UI", font_size, QFont.Weight.DemiBold))
        painter.drawText(heading, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, self.title)
        painter.setFont(QFont("Segoe UI", 12))
        painter.setPen(QColor("#a4b6ce"))
        if self.kind == "game" and self.subtitle == PS4_PACKAGE_STATUS:
            painter.drawText(subtitle, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap, self.subtitle)
        else:
            painter.drawText(subtitle, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             painter.fontMetrics().elidedText(self.subtitle, Qt.TextElideMode.ElideRight, int(subtitle.width())))

    @staticmethod
    def _placeholder(painter, rect):
        center = rect.center()
        painter.setBrush(QColor("#33465b"))
        painter.setPen(QPen(QColor("#7f93ad"), 3))
        painter.drawRoundedRect(QRectF(center.x() - 42, center.y() - 23, 84, 46), 15, 15)
        painter.drawLine(QPointF(center.x() - 29, center.y()), QPointF(center.x() - 11, center.y()))
        painter.drawLine(QPointF(center.x() - 20, center.y() - 9), QPointF(center.x() - 20, center.y() + 9))
        painter.setBrush(QColor("#7f93ad"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(center.x() + 13, center.y() - 12, 8, 8))
        painter.drawEllipse(QRectF(center.x() + 24, center.y() + 3, 8, 8))


class CouchDialog(QDialog):
    """Eigene Vollbildansicht; Spielstarts übernimmt weiterhin das Hauptfenster."""

    launchRequested = Signal(str)
    packageInstallRequested = Signal(str)

    def __init__(self, service, parent=None, *, backend=None):
        super().__init__(parent)
        self.service = service
        if backend is None:
            try:
                from core.controllers import XInputBackend
                backend = XInputBackend()
            except (ImportError, OSError):
                backend = None
        self.backend = backend
        self._page = "consoles"
        self._console = None
        self._console_index = 0
        self._selected = 0
        self._columns = 1
        self._tiles = []
        self._menu_return = None
        self._active_slot = None
        self._input_receiver = None
        self._armed = False
        self._previous_buttons = set()
        self._direction = None
        self._next_repeat = 0.0
        self._exit_started = None
        self._inactive_slot = None
        self._inactive_armed = False
        self._inactive_exit_started = None
        self._cover_generation = 0
        self._cover_files = {}
        self._cover_workers = {}
        self._cover_cache = OrderedDict()
        self.cover_pool = QThreadPool(self)
        self.cover_pool.setMaxThreadCount(2)
        self.cover_timer = QTimer(self)
        self.cover_timer.setSingleShot(True)
        self.cover_timer.timeout.connect(self._queue_visible_covers)
        self.setWindowTitle("Emulator Hub · Vollbild-Modus")
        self.setStyleSheet(STYLESHEET)
        self.resize(1280, 800)
        self.setMinimumSize(740, 580)
        self.setModal(False)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 28, 36, 24)
        layout.setSpacing(18)
        self.heading = label("Konsolen", "title")
        self.heading.setStyleSheet("font-size: 30pt; font-weight: 700;")
        layout.addWidget(self.heading)
        self.summary = label("", "muted")
        self.summary.setStyleSheet("font-size: 14pt; color: #a4b6ce;")
        layout.addWidget(self.summary)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.content = QWidget()
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(3, 3, 12, 12)
        self.grid.setSpacing(20)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.content)
        self.scroll.verticalScrollBar().valueChanged.connect(self._schedule_covers)
        layout.addWidget(self.scroll, 1)
        self.empty_label = label("Noch keine Spiele. Wähle Spieleordner in den Einstellungen und scanne die Bibliothek.", "muted")
        self.empty_label.setStyleSheet("font-size: 18pt;")
        layout.addWidget(self.empty_label)
        controls = QHBoxLayout()
        self.back_button = QPushButton("Zurück · B / Rücktaste")
        self.back_button.clicked.connect(self._back)
        controls.addWidget(self.back_button)
        self.menu_button = QPushButton("Menü · Start / M")
        self.menu_button.clicked.connect(self._open_menu)
        controls.addWidget(self.menu_button)
        controls.addStretch()
        self.exit_button = QPushButton("Vollbild verlassen · Esc")
        self.exit_button.clicked.connect(self.reject)
        controls.addWidget(self.exit_button)
        for button in (self.back_button, self.menu_button, self.exit_button):
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setStyleSheet("font-size: 14pt; padding: 14px 20px;")
        layout.addLayout(controls)
        self.controller_label = label("Kein XInput-Controller erkannt · Tastatur und Maus funktionieren ebenfalls.", "muted")
        self.controller_label.setStyleSheet("font-size: 12pt; color: #a4b6ce;")
        layout.addWidget(self.controller_label)
        help_text = label("Steuerkreuz/Stick: bewegen · A / Enter: wählen · B / Rücktaste: zurück · Start / M: Menü\nDialoge: oben/unten wählen, links/rechts oder LB/RB Fokus wechseln · Esc oder Start + Zurück (Select) 1,2 Sekunden: Vollbild verlassen", "footnote")
        help_text.setStyleSheet("font-size: 12pt; color: #91a3bb;")
        layout.addWidget(help_text)
        self._show_consoles()
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        # Ein Spielstart kann exec() öffnen. Außerhalb des laufenden Timer-Events
        # abfragen, damit der Timer auch im modalen Qt-Eventloop weiterläuft.
        self.timer.timeout.connect(self._poll_controllers, Qt.ConnectionType.QueuedConnection)

    def _metadata(self, game):
        metadata = getattr(self.service, "metadata", None)
        if metadata is None:
            return {}
        value = metadata.get(game["id"])
        return value if isinstance(value, dict) else {}

    def _clear_tiles(self):
        self._cover_generation += 1
        self.cover_pool.clear()
        self._cover_files = {}
        self._cover_workers = {}
        for tile in self._tiles:
            tile.animation.stop()
            self.grid.removeWidget(tile)
            tile.hide()
            tile.deleteLater()
        self._tiles = []
        self._selected = 0

    def _append_tile(self, tile, callback):
        index = len(self._tiles)
        tile.installEventFilter(self)
        tile.focused.connect(lambda i=index: self._select(i, focus=False))
        tile.clicked.connect(callback)
        self._tiles.append(tile)

    def _show_consoles(self, selected=None):
        self._page = "consoles"
        self._console = None
        self._clear_tiles()
        groups = {}
        for game in getattr(self.service.library, "visible_games", self.service.library.games):
            groups.setdefault(game.get("console") or "Noch zuordnen", []).append(game)
        self.heading.setText("Konsolen")
        self.summary.setText("Wähle eine Konsole und anschließend dein Spiel.")
        for console, games in sorted(groups.items(), key=lambda item: item[0].casefold()):
            tile = CouchTile(console, f"{len(games)} Spiele", kind="console")
            self._append_tile(tile, lambda _=False, name=console: self._show_games(name))
        self.empty_label.setVisible(not self._tiles)
        self.back_button.setText("Zur normalen Ansicht · B / Rücktaste")
        self._layout_tiles()
        self._select(self._console_index if selected is None else selected)

    def _show_games(self, console, selected=0):
        if self._page == "consoles":
            self._console_index = self._selected
        self._page = "games"
        self._console = console
        self._clear_tiles()
        self.heading.setText(console)
        games = [game for game in getattr(self.service.library, "visible_games", self.service.library.games)
                 if (game.get("console") or "Noch zuordnen") == console]
        display_games = [(game, self._metadata(game)) for game in games]
        display_games.sort(key=lambda pair: str(pair[1].get("title") or pair[0].get("name", "")).casefold())
        package_count = sum(is_ps4_package(game) for game in games)
        self.summary.setText(
            f"{len(games)} eigene Einträge · A / Enter: Spiel starten oder Paketinstallation öffnen."
            if package_count else f"{len(games)} eigene Spiele · A / Enter startet das gewählte Spiel."
        )
        for game, metadata in display_games:
            title = metadata.get("title") or game.get("name", "Unbenanntes Spiel")
            package = is_ps4_package(game)
            subtitle = PS4_PACKAGE_STATUS if package else "Datei fehlt" if game.get("missing") else str(metadata.get("year") or game.get("console") or "Konsole noch zuordnen")
            if game_status(game) == WINUAE_CONFIG_STATUS:
                subtitle = WINUAE_CONFIG_STATUS
            tile = CouchTile(str(title), subtitle)
            tile.setToolTip(f"{subtitle}\n{game.get('path', '')}")
            cover_path = metadata.get("cover_path")
            if isinstance(cover_path, (str, Path)) and str(cover_path):
                self._cover_files[len(self._tiles)] = str(cover_path)
            signal = self.packageInstallRequested if package else self.launchRequested
            self._append_tile(tile, lambda _=False, identifier=game["id"], target=signal: target.emit(identifier))
        self.empty_label.setVisible(not self._tiles)
        self.back_button.setText("Konsolen · B / Rücktaste")
        self._layout_tiles()
        self._select(selected)

    def _open_menu(self):
        if self._page == "menu":
            self._back()
            return
        self._menu_return = (self._page, self._console, self._selected)
        self._page = "menu"
        self._clear_tiles()
        self.heading.setText("Menü")
        self.summary.setText("A / Enter bestätigt · B / Rücktaste kehrt zur Bibliothek zurück.")
        self.empty_label.hide()
        self.back_button.setText("Bibliothek · B / Rücktaste")
        self._append_tile(CouchTile("Zur Bibliothek zurück", "Deine Auswahl bleibt erhalten.", kind="menu"), self._back)
        self._append_tile(CouchTile("Vollbild verlassen", "Zur normalen Emulator-Hub-Ansicht.", kind="menu"), self.reject)
        self._layout_tiles()
        self._select(0)

    def _back(self):
        if self._page == "menu":
            page, console, selected = self._menu_return or ("consoles", None, 0)
            self._menu_return = None
            if page == "games":
                self._show_games(console, selected)
            else:
                self._show_consoles(selected)
        elif self._page == "games":
            self._show_consoles()
        else:
            self.reject()

    def _layout_tiles(self):
        available = max(1, self.scroll.viewport().width() - 20)
        width = 265 if self._page == "games" else 310
        self._columns = 1 if self._page == "menu" else max(1, min(6, available // width))
        while self.grid.count():
            self.grid.takeAt(0)
        for column in range(6):
            self.grid.setColumnStretch(column, 1 if column < self._columns else 0)
        for index, tile in enumerate(self._tiles):
            self.grid.addWidget(tile, index // self._columns, index % self._columns)
        self.grid.activate()
        self._schedule_covers()

    def _select(self, index, *, focus=True):
        if not self._tiles:
            self._selected = 0
            return
        index = max(0, min(len(self._tiles) - 1, index))
        if self._selected != index or not self._tiles[index]._focus_amount:
            for i in {self._selected, index}:
                if i < len(self._tiles):
                    self._tiles[i].set_selected(i == index)
        self._selected = index
        if focus and not self._tiles[index].hasFocus():
            self._tiles[index].setFocus(Qt.FocusReason.OtherFocusReason)
        self.scroll.ensureWidgetVisible(self._tiles[index], 20, 20)
        self._schedule_covers()

    def _schedule_covers(self, *_):
        self.cover_timer.start(0)

    def _cover_visible(self, tile):
        position = tile.mapTo(self.scroll.viewport(), QPoint())
        # Eine zusätzliche Reihe vorbereiten, ohne alle Cover gleichzeitig zu lesen.
        viewport = self.scroll.viewport().rect().adjusted(0, -tile.height(), 0, tile.height())
        return QRect(position, tile.size()).intersects(viewport)

    def _queue_visible_covers(self):
        if self._page != "games" or not self.isVisible():
            return
        for index, tile in enumerate(self._tiles):
            if not self._cover_visible(tile):
                tile.cover = QPixmap()
                continue
            path = self._cover_files.get(index)
            if not path or not tile.cover.isNull():
                continue
            try:
                details = Path(path).stat()
                key = f"{path}|{details.st_mtime_ns}|{details.st_size}"
            except OSError:
                continue
            if key in self._cover_cache:
                tile.cover = self._cover_cache[key]
                self._cover_cache.move_to_end(key)
                tile.update()
                continue
            task = (self._cover_generation, index)
            if task in self._cover_workers:
                continue
            worker = _CoverWorker(self._cover_generation, index, key, path)
            worker.signals.ready.connect(self._cover_ready)
            self._cover_workers[task] = worker
            self.cover_pool.start(worker)

    @Slot(int, int, str, QImage)
    def _cover_ready(self, generation, index, key, image):
        self._cover_workers.pop((generation, index), None)
        if generation != self._cover_generation or index >= len(self._tiles):
            return
        pixmap = QPixmap.fromImage(image)
        self._cover_cache[key] = pixmap
        self._cover_cache.move_to_end(key)
        while len(self._cover_cache) > 16:
            self._cover_cache.popitem(last=False)
        tile = self._tiles[index]
        if self.isVisible() and self._cover_visible(tile):
            tile.cover = pixmap
            tile.update()

    def _navigate(self, direction):
        count = len(self._tiles)
        if not count:
            return
        index = self._selected
        if direction == "LEFT" and index % self._columns:
            index -= 1
        elif direction == "RIGHT" and index % self._columns < self._columns - 1 and index + 1 < count:
            index += 1
        elif direction == "UP" and index >= self._columns:
            index -= self._columns
        elif direction == "DOWN" and index + self._columns < count:
            index += self._columns
        elif direction == "DOWN" and index // self._columns < (count - 1) // self._columns:
            index = count - 1
        self._select(index)

    def _activate(self):
        if self._tiles:
            self._tiles[self._selected].click()
        else:
            self._open_menu()

    def _handle_key(self, event):
        key = event.key()
        directions = {Qt.Key.Key_Left: "LEFT", Qt.Key.Key_Right: "RIGHT", Qt.Key.Key_Up: "UP", Qt.Key.Key_Down: "DOWN"}
        if key in directions:
            self._navigate(directions[key])
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_A):
            if not event.isAutoRepeat():
                self._activate()
        elif key in (Qt.Key.Key_Backspace, Qt.Key.Key_B):
            if not event.isAutoRepeat():
                self._back()
        elif key == Qt.Key.Key_Escape:
            self.reject()
        elif key in (Qt.Key.Key_M, Qt.Key.Key_Menu, Qt.Key.Key_F10):
            if not event.isAutoRepeat():
                self._open_menu()
        elif key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self._select((self._selected + (-1 if key == Qt.Key.Key_Backtab or event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1)) % max(1, len(self._tiles)))
        else:
            return False
        event.accept()
        return True

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and self._handle_key(event):
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if not self._handle_key(event):
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "scroll"):
            self._layout_tiles()

    def showEvent(self, event):
        super().showEvent(event)
        self._armed = False
        self._layout_tiles()
        self._select(self._selected)
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        self.cover_timer.stop()
        self.cover_pool.clear()
        self._cover_generation += 1
        self._cover_workers = {}
        self._reset_input()
        self._reset_inactive_input()
        super().hideEvent(event)

    def _reset_input(self):
        self._input_receiver = None
        self._armed = False
        self._previous_buttons = set()
        self._direction = None
        self._exit_started = None

    @staticmethod
    def _input_direction(state):
        buttons = state.get("buttons", set())
        for direction in ("UP", "DOWN", "LEFT", "RIGHT"):
            if direction in buttons:
                return direction
        axes = state.get("axes", {})
        x, y = axes.get("lx", 0), axes.get("ly", 0)
        if abs(x) >= abs(y) and abs(x) >= 0.55:
            return "RIGHT" if x > 0 else "LEFT"
        if abs(y) >= 0.55:
            return "UP" if y > 0 else "DOWN"
        return None

    def _hub_modal(self):
        """Modale Qt-Fenster des Hubs über ihre Elternkette erkennen."""
        modal = QApplication.activeModalWidget()
        if isinstance(modal, QDialog):
            root = self.parentWidget().window() if self.parentWidget() is not None else self
            owner = modal.parentWidget()
            while owner is not None:
                if owner in (self, root):
                    return modal
                owner = owner.parentWidget()
        return None

    def _controller_target(self):
        """Nur die aktive Couch-Ansicht oder einen modalen Dialog dieses Hubs bedienen."""
        if not self.isVisible():
            return None
        if QApplication.activeModalWidget() is not None:
            modal = self._hub_modal()
            return modal if modal is not None and modal.isActiveWindow() else None
        return self if self.isActiveWindow() else None

    def _reset_inactive_input(self):
        self._inactive_slot = None
        self._inactive_armed = False
        self._inactive_exit_started = None

    def _handle_inactive_controller(self, state, now=None):
        """Während eines Spiels ausschließlich die eigene Rückkehr-Kombination prüfen."""
        slot = state.get("slot")
        if slot != self._inactive_slot:
            self._reset_inactive_input()
            self._inactive_slot = slot
        buttons = set(state.get("buttons", set()))
        if not self._inactive_armed:
            if not buttons and self._input_direction(state) is None:
                self._inactive_armed = True
            return
        if {"START", "BACK"}.issubset(buttons):
            now = time.monotonic() if now is None else now
            if self._inactive_exit_started is None:
                self._inactive_exit_started = now
            elif now - self._inactive_exit_started >= 1.2:
                self._exit_couch(self._hub_modal() or self)
                self._reset_inactive_input()
        else:
            self._inactive_exit_started = None

    @staticmethod
    def _modal_focus(dialog):
        focus = dialog.focusWidget()
        if focus is not None and focus.isEnabled() and focus.isVisible():
            return focus
        buttons = dialog.findChildren(QPushButton)
        button = next((item for item in buttons if item.isEnabled() and item.isVisible() and item.isDefault()), None)
        if button is not None:
            button.setFocus(Qt.FocusReason.OtherFocusReason)
            return button
        return dialog

    def _modal_key(self, dialog, key, modifiers=Qt.KeyboardModifier.NoModifier):
        """Qt-Ereignisse direkt zustellen; niemals globale Windows-Tastendrücke senden."""
        receiver = self._modal_focus(dialog)
        for kind in (QEvent.Type.KeyPress, QEvent.Type.KeyRelease):
            QApplication.sendEvent(receiver, QKeyEvent(kind, key, modifiers))

    def _modal_navigate(self, dialog, direction):
        focus = self._modal_focus(dialog)
        if direction in ("UP", "DOWN") and isinstance(focus, (QComboBox, QAbstractItemView, QAbstractSpinBox)):
            self._modal_key(dialog, Qt.Key.Key_Up if direction == "UP" else Qt.Key.Key_Down)
        else:
            backwards = direction in ("LEFT", "UP")
            self._modal_key(dialog, Qt.Key.Key_Backtab if backwards else Qt.Key.Key_Tab,
                            Qt.KeyboardModifier.ShiftModifier if backwards else Qt.KeyboardModifier.NoModifier)

    def _modal_activate(self, dialog):
        focus = self._modal_focus(dialog)
        if isinstance(focus, QAbstractButton):
            focus.click()
        else:
            self._modal_key(dialog, Qt.Key.Key_Return)

    def _exit_couch(self, target):
        # Reject beendet nur die Hub-Abfrage. Bereits gestartete Emulatoren bleiben unberührt.
        if target is not self:
            target.reject()
        self.reject()

    def _handle_controller(self, state, now=None, *, target=None):
        target = self if target is None else target
        if target is not self._input_receiver:
            self._reset_input()
            self._input_receiver = target
        now = time.monotonic() if now is None else now
        buttons = set(state.get("buttons", set()))
        direction = self._input_direction(state)
        if not self._armed:
            if not buttons and direction is None:
                self._armed = True
            self._previous_buttons = buttons
            return
        if {"START", "BACK"}.issubset(buttons):
            if self._exit_started is None:
                self._exit_started = now
            elif now - self._exit_started >= 1.2:
                self._exit_couch(target)
            self._previous_buttons = buttons
            self._direction = None
            return
        self._exit_started = None
        pressed = buttons - self._previous_buttons
        self._previous_buttons = buttons
        if "B" in pressed or (target is not self and "BACK" in pressed):
            self._direction = None
            target.reject() if target is not self else self._back()
            return
        if "A" in pressed:
            self._direction = None
            self._modal_activate(target) if target is not self else self._activate()
            return
        if "START" in pressed or (target is not self and {"LB", "RB"} & pressed):
            self._direction = None
            if target is self:
                self._open_menu()
            else:
                self._modal_navigate(target, "LEFT" if "LB" in pressed else "RIGHT")
            return
        if direction is not None:
            if direction != self._direction:
                self._modal_navigate(target, direction) if target is not self else self._navigate(direction)
                self._next_repeat = now + 0.35
            elif now >= self._next_repeat:
                self._modal_navigate(target, direction) if target is not self else self._navigate(direction)
                self._next_repeat = now + 0.11
        self._direction = direction

    def _poll_controllers(self):
        if not self.isVisible():
            self._reset_input()
            self._reset_inactive_input()
            return
        target = self._controller_target()
        if target is None:
            self._reset_input()
        else:
            self._reset_inactive_input()
        if self.backend is None:
            return
        try:
            states = self.backend.poll()
        except (OSError, RuntimeError, ValueError):
            self.controller_label.setText("Controller konnte nicht abgefragt werden · Tastatur und Maus sind weiterhin nutzbar.")
            self._reset_input()
            self._reset_inactive_input()
            return
        if not states:
            self.controller_label.setText("Kein XInput-Controller erkannt · Tastatur und Maus funktionieren ebenfalls.")
            self._active_slot = None
            self._reset_input()
            self._reset_inactive_input()
            return
        state = next((item for item in states if item.get("slot") == self._active_slot), states[0])
        if self._active_slot != state.get("slot"):
            self._active_slot = state.get("slot")
            self._reset_input()
        self.controller_label.setText(f"{state.get('name', 'XInput-Controller')} · {state.get('type', 'XInput-Gamepad')}")
        if target is None:
            self._handle_inactive_controller(state)
        else:
            self._handle_controller(state, target=target)
