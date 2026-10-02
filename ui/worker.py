"""Ein einzelner Hintergrundauftrag mit Qt-Signalen und kooperativem Abbruch."""

from __future__ import annotations

import threading
from collections.abc import Callable

from PySide6.QtCore import QThread, Signal


class Worker(QThread):
    progress = Signal(int, str)
    log = Signal(str)
    success = Signal(object)
    failure = Signal(str)

    def __init__(self, operation: Callable, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.cancel_event = threading.Event()

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            result = self.operation(self.progress.emit, self.log.emit, self.cancel_event)
        except Exception as exc:
            self.failure.emit(str(exc) or "Der Vorgang konnte nicht abgeschlossen werden.")
        else:
            self.success.emit(result)
