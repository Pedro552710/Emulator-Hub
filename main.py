"""Natives Windows-Programm: python main.py (ohne Browser/Webserver)."""
import argparse
import ctypes
import os
from pathlib import Path
import sys

from PySide6.QtCore import QLockFile, QTimer, QLocale, QTranslator, QLibraryInfo
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QMessageBox

from core.catalog import Catalog, CatalogError
from core.errors import HubError
from core.installer import HubService, default_data_dir
from core.version import VERSION
from ui import MainWindow
from ui.branding import application_icon


def app_icon():
    """Gemeinsames Logo für Fenster und Windows-Taskleiste."""
    return application_icon()


def set_windows_app_id():
    """Eigenständige Taskleistengruppe vor dem ersten Qt-Fenster festlegen."""
    if os.name != "nt":
        return False
    try:
        function = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        function.argtypes = [ctypes.c_wchar_p]
        function.restype = ctypes.c_long
        return function("EmulatorHub.Desktop") >= 0
    except (OSError, AttributeError):
        return False


def main():
    parser = argparse.ArgumentParser(description="Emulator Hub für Windows")
    parser.add_argument("--catalog", type=Path, help="Abweichende Katalogdatei")
    parser.add_argument("--data-dir", type=Path, help="Abweichender lokaler Datenordner")
    parser.add_argument("--smoke-test", action="store_true", help="Fenster testweise öffnen und automatisch schließen")
    parser.add_argument("--check-integrations", action="store_true", help="Mit --smoke-test auch Windows-Zugangsdatenbackend und XInput prüfen")
    parser.add_argument("--screenshot", type=Path, help="Fenster als PNG speichern (mit --smoke-test)")
    args = parser.parse_args()
    if args.check_integrations and not args.smoke_test:
        parser.error("--check-integrations benötigt --smoke-test.")
    set_windows_app_id()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Emulator Hub")
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("EmulatorHub")
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(app_icon())
    QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Germany))
    translator = QTranslator(app)
    if translator.load("qtbase_de", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    data_dir = args.data_dir or default_data_dir()
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(data_dir / "hub.lock"))
        # Qt prüft Prozess-ID und Rechnername; echte verwaiste Sperren werden erkannt.
        lock.setStaleLockTime(0)
        if not lock.tryLock(100):
            raise HubError("Emulator Hub läuft bereits mit diesem Datenordner. Bitte das vorhandene Fenster verwenden.")
        catalog = Catalog(args.catalog)
        service = HubService(catalog, data_dir=data_dir)
        if args.check_integrations and os.name == "nt":
            from core.controllers import XInputBackend
            backend = XInputBackend()
            if not backend.available:
                raise HubError("Das Windows-XInput-Backend konnte nicht geladen werden.")
            backend.poll()
            try:
                # Nur eine unbenutzte Prüfkennung lesen; keine echten Zugangsdaten
                # lesen oder speichern und keine Dienstverbindung herstellen.
                service.metadata._vault().get_password("EmulatorHub.RuntimeCheck", "Backendtest")
            except Exception:
                raise HubError("Das Windows-Zugangsdatenbackend konnte nicht geprüft werden.") from None
        window = MainWindow(service, catalog)
        window.show()
    except (HubError, CatalogError, OSError) as exc:
        if args.smoke_test:
            print(str(exc), file=sys.stderr)
        else:
            QMessageBox.critical(None, "Emulator Hub – Start fehlgeschlagen", str(exc))
        return 1
    if args.smoke_test:
        def finish():
            # Beim Erststart darf der Systemcheck seinen Hintergrundschritt beenden.
            if window.worker is not None and window.worker.isRunning():
                QTimer.singleShot(200, finish)
                return
            if args.screenshot:
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                if not window.grab().save(str(args.screenshot), "PNG"):
                    app.exit(2)
                    return
            print(f"Start erfolgreich: {len(catalog.items)} Emulatoren, {len(catalog.categories)} Kategorien.", flush=True)
            window.close()
            app.quit()
        QTimer.singleShot(1200, finish)
    result = app.exec()
    lock.unlock()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
