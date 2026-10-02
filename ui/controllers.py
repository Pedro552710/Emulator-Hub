"""Modaler Controller-Assistent mit nativem Livetest und sicheren Vorschauen."""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout,
)

from core.controllers import ControllerService, XInputBackend
from core.errors import HubError
from .dialogs import label
from .worker import Worker


BUTTON_LABELS = {"UP": "Oben", "DOWN": "Unten", "LEFT": "Links", "RIGHT": "Rechts",
                 "START": "Start", "BACK": "Zurück", "LS": "Linker Stick", "RS": "Rechter Stick"}


class ControllerDialog(QDialog):
    def __init__(self, service, parent=None, backend=None):
        super().__init__(parent)
        self.service = service
        self.controllers = ControllerService(service)
        self.backend = backend or XInputBackend()
        self.worker = None
        self._preview = None
        self._states = []
        self._close_after_work = False
        self.setWindowTitle("Controller einrichten")
        self.resize(850, 790)
        self.setMinimumSize(700, 650)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(label("Controller einrichten", "sectionTitle"))
        layout.addWidget(label("XInput-kompatible Controller werden unter Windows erkannt. Der Treiber liefert Typ und Anschlussnummer, keinen Produktnamen. Andere USB-/Bluetooth-Controller ohne XInput können im jeweiligen Emulator manuell eingerichtet werden.", "muted"))
        device_row = QHBoxLayout()
        device_row.addWidget(label("Controller", "footnote"))
        self.device_combo = QComboBox()
        self.device_combo.setAccessibleName("Angeschlossener XInput-Controller")
        self.device_combo.currentIndexChanged.connect(self._selection_changed)
        device_row.addWidget(self.device_combo, 1)
        layout.addLayout(device_row)
        self.device_status = label("", "footnote")
        layout.addWidget(self.device_status)
        self.buttons_status = label("Gedrückte Tasten: keine", "cardTitle")
        layout.addWidget(self.buttons_status)
        self.axes_status = label("Sticks und Trigger: keine Eingabe", "footnote")
        layout.addWidget(self.axes_status)
        layout.addWidget(label("Tastenbelegung im Emulator", "cardTitle"))
        self.emulator_combo = QComboBox()
        self.emulator_combo.setAccessibleName("Emulator für die Controller-Einrichtung")
        for entry in service.catalog.items:
            suffix = " · Automatik für GameCube-Port 1" if self.controllers.can_auto(entry["id"]) else " · manuell"
            self.emulator_combo.addItem(entry["emulator"] + suffix, entry["id"])
        self.emulator_combo.currentIndexChanged.connect(self._emulator_changed)
        layout.addWidget(self.emulator_combo)
        self.guide = label("", "muted")
        layout.addWidget(self.guide)
        self.path_label = label("", "footnote")
        layout.addWidget(self.path_label)
        actions = QHBoxLayout()
        self.path_button = QPushButton("Konfigdatei wählen …")
        self.path_button.clicked.connect(self._choose_path)
        actions.addWidget(self.path_button)
        self.preview_button = QPushButton("Belegung prüfen / Vorschau")
        self.preview_button.clicked.connect(self._load_preview)
        actions.addWidget(self.preview_button)
        actions.addStretch()
        layout.addLayout(actions)
        self.preview_text = QPlainTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMinimumHeight(150)
        self.preview_text.setMaximumHeight(260)
        self.preview_text.setPlaceholderText("Die Vorschau ändert keine Datei. Nur der Abschnitt [GCPad1] einer vorhandenen GCPadNew.ini wird automatisch zugeordnet; andere Ports und Wii bleiben unverändert.")
        layout.addWidget(self.preview_text, 1)
        write_row = QHBoxLayout()
        self.apply_button = QPushButton("Belegung übernehmen …")
        self.apply_button.setObjectName("primary")
        self.apply_button.clicked.connect(self._apply)
        write_row.addWidget(self.apply_button)
        self.undo_button = QPushButton("Rückgängig machen …")
        self.undo_button.clicked.connect(self._undo)
        write_row.addWidget(self.undo_button)
        write_row.addStretch()
        layout.addLayout(write_row)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        self.status = label("Vor jeder Änderung und Rücknahme wird die aktuelle Konfiguration gesichert. Änderungen benötigen deine Bestätigung. Bitte den Emulator vorher vollständig schließen.", "footnote")
        layout.addWidget(self.status)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(90)
        self.log.hide()
        layout.addWidget(self.log)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.close_button = buttons.button(QDialogButtonBox.StandardButton.Close)
        self.close_button.setText("Schließen")
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(50)
        self.poll_timer.timeout.connect(self._poll)
        self._poll()
        self._emulator_changed()
        preferred = next((index for index, entry in enumerate(service.catalog.items)
                          if self.controllers.can_auto(entry["id"]) and service.is_installed(entry["id"])), 0)
        self.emulator_combo.setCurrentIndex(preferred)
        self.poll_timer.start()

    def _identifier(self):
        return self.emulator_combo.currentData()

    def _selected_state(self):
        slot = self.device_combo.currentData()
        return next((state for state in self._states if state["slot"] == slot), None)

    def _selection_changed(self):
        self._preview = None
        self.preview_text.clear()
        self._update_buttons()

    def _emulator_changed(self):
        self._preview = None
        self.preview_text.clear()
        identifier = self._identifier()
        if identifier:
            self.guide.setText(self.controllers.manual_guide(identifier))
            if self.controllers.can_auto(identifier):
                try:
                    self.path_label.setText("Aktive Konfigdatei prüfen: " + str(self.controllers.config_path(identifier)))
                except HubError as exc:
                    self.path_label.setText(str(exc))
            else:
                self.path_label.setText("Keine automatische Änderung: Eingabebackends, Profile und Formate unterscheiden sich je nach Version und Oberfläche.")
        self._update_buttons()

    def _poll(self):
        try:
            self._states = self.backend.poll()
        except (OSError, RuntimeError):
            self._states = []
            self.device_status.setText("Der Controller konnte nicht abgefragt werden. Bitte Verbindung und Treiber prüfen.")
        identity = [(state["slot"], state["name"], state["type"]) for state in self._states]
        previous = [(self.device_combo.itemData(i), self.device_combo.itemText(i)) for i in range(self.device_combo.count())]
        wanted = [(slot, f"{name} · {kind}") for slot, name, kind in identity] or [(None, "Kein XInput-Controller erkannt")]
        if previous != wanted:
            selected = self.device_combo.currentData()
            self.device_combo.blockSignals(True)
            self.device_combo.clear()
            for slot, text in wanted:
                self.device_combo.addItem(text, slot)
            index = self.device_combo.findData(selected)
            self.device_combo.setCurrentIndex(max(0, index))
            self.device_combo.blockSignals(False)
            self._selection_changed()
        state = self._selected_state()
        if state:
            self.device_status.setText("Livetest: Tasten, Sticks und Trigger bewegen. Anschlussnummern können sich nach erneutem Verbinden ändern.")
            self.buttons_status.setText("Gedrückte Tasten: " + (" · ".join(BUTTON_LABELS.get(button, button) for button in sorted(state["buttons"])) or "keine"))
            axes = state["axes"]
            self.axes_status.setText(f"Linker Stick: {axes['lx']:+.2f} / {axes['ly']:+.2f}    Rechter Stick: {axes['rx']:+.2f} / {axes['ry']:+.2f}    LT: {axes['lt']:.0%} · RT: {axes['rt']:.0%}")
        else:
            self.device_status.setText(getattr(self.backend, "unavailable_reason", "") or "Kein XInput-Gerät erkannt. Controller anschließen oder dessen XInput-Modus aktivieren. Nur durch XInput sichtbare Geräte werden angezeigt.")
            self.buttons_status.setText("Gedrückte Tasten: keine")
            self.axes_status.setText("Sticks und Trigger: keine Eingabe")
        self._update_buttons()

    def _update_buttons(self):
        if not hasattr(self, "apply_button"):
            return
        identifier = self._identifier()
        auto = bool(identifier and self.controllers.can_auto(identifier))
        state = self._selected_state()
        usable = bool(state and state.get("subtype") == 1)
        busy = self.worker is not None
        self.emulator_combo.setEnabled(not busy)
        self.device_combo.setEnabled(not busy)
        self.path_button.setEnabled(auto and not busy)
        self.preview_button.setEnabled(auto and usable and not busy)
        matching_preview = bool(self._preview and state and self._preview["slot"] == state["slot"]
                                and self._preview["emulator_id"] == identifier)
        self.apply_button.setEnabled(auto and usable and matching_preview and not busy)
        try:
            undo = bool(identifier and self.controllers.last_change(identifier))
        except HubError:
            undo = False
        self.undo_button.setEnabled(auto and undo and not busy)

    def _choose_path(self):
        selected, _ = QFileDialog.getOpenFileName(self, "Aktive Dolphin-Konfigdatei auswählen", "", "Dolphin-Konfiguration (GCPadNew.ini)")
        if not selected:
            return
        identifier = self._identifier()

        def choose(progress, log, cancel):
            if cancel.is_set():
                return None
            self.controllers.set_config_path(identifier, selected)
            return {"message": "Profil zugeordnet; noch keine Konfigdatei verändert."}

        def chosen(result):
            self._emulator_changed()
            if result:
                self.status.setText(result["message"])

        self._start(choose, chosen)

    def _load_preview(self):
        state = self._selected_state()
        if not state or state.get("subtype") != 1:
            return
        identifier, slot = self._identifier(), state["slot"]
        self._start(lambda progress, log, cancel: self.controllers.preview(identifier, slot, progress, log, cancel), self._show_preview)

    def _show_preview(self, result):
        self._preview = result
        self.preview_text.setPlainText(result["text"])
        self.path_label.setText("Geprüfte Konfigdatei: " + result["path"])
        self.status.setText("Vorschau: XInput A/B/X/Y → GameCube A/B/X/Y; RB → Z; LB/LT → L, RT → R. Nur Port 1 wird geändert. Vorhandene Belegung wird erst nach Bestätigung überschrieben und zuvor exakt gesichert.")

    def _apply(self):
        if self._preview is None:
            return
        preview = self._preview
        answer = QMessageBox.question(self, "Controller-Belegung bestätigen",
            "Ist Dolphin vollständig geschlossen und gehört diese Datei zum aktiven Profil?\n\n"
            + preview["path"] + "\n\nDie angezeigte Belegung für GameCube-Port 1 übernehmen? Die bisherige Datei wird vor der Änderung gesichert. Wii und andere Ports werden nicht geändert.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start(lambda progress, log, cancel: self.controllers.apply(preview, confirmed=True, progress=progress, log=log, cancel_event=cancel), self._written)

    def _undo(self):
        identifier = self._identifier()
        answer = QMessageBox.question(self, "Controller-Änderung rückgängig machen",
            "Ist Dolphin vollständig geschlossen?\n\nDie letzte Controller-Änderung rückgängig machen? Der aktuelle Stand wird vorher erneut gesichert. Hat sich die Datei inzwischen außerhalb des Hubs geändert, wird sie nicht überschrieben.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._start(lambda progress, log, cancel: self.controllers.undo(identifier, confirmed=True, progress=progress, log=log, cancel_event=cancel), self._written)

    def _written(self, result):
        self._preview = None
        self.preview_text.clear()
        self.status.setText(result["message"] + ("\nSicherung: " + result["backup"] if result.get("backup") else ""))

    def _start(self, operation, success):
        if self.worker is not None:
            return
        self.worker = Worker(operation, self)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.show()
        self.log.show()
        self.status.setText("Controller-Auftrag läuft im Hintergrund …")
        self.worker.progress.connect(self._progress)
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.success.connect(success)
        self.worker.failure.connect(lambda message: self.status.setText("Controller-Einrichtung: " + message))
        self.worker.finished.connect(self._finished)
        self._update_buttons()
        self.worker.start()

    def _progress(self, percent, phase):
        self.progress_bar.setRange(0, 0 if percent < 0 else 100)
        if percent >= 0:
            self.progress_bar.setValue(percent)
        self.status.setText(phase)

    def _finished(self):
        worker, self.worker = self.worker, None
        if worker:
            worker.deleteLater()
        self.progress_bar.hide()
        self._update_buttons()
        if self._close_after_work:
            self.reject()

    def reject(self):
        if self.worker is not None:
            self._close_after_work = True
            self.worker.cancel()
            self.status.setText("Der laufende Auftrag wird sicher beendet …")
            return
        self.poll_timer.stop()
        super().reject()

    def closeEvent(self, event):
        if self.worker is not None:
            self._close_after_work = True
            self.worker.cancel()
            event.ignore()
            return
        self.poll_timer.stop()
        super().closeEvent(event)

    def showEvent(self, event):
        self.poll_timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.poll_timer.stop()
        super().hideEvent(event)
