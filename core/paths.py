"""Programmressourcen und bearbeitbare Konfigurationen zentral auflösen."""
from pathlib import Path
import shutil
import sys


def app_directory():
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent


def resource_path(relative):
    root = Path(getattr(sys, "_MEIPASS", app_directory()))
    return root / relative


def config_path(name, data_dir=None):
    if Path(name).name != name:
        raise ValueError("Konfigurationsname muss ein Dateiname sein.")
    candidates = ([Path(data_dir) / "configs" / name] if data_dir is not None else [])
    candidates += [app_directory() / "configs" / name, resource_path(Path("configs") / name)]
    return next((p for p in candidates if p.is_file()), candidates[-1])


def ensure_config(name, data_dir):
    """Eine editierbare lokale Kopie anlegen; bestehende Werte nicht ersetzen."""
    target = Path(data_dir) / "configs" / name
    if not target.exists():
        source = config_path(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return target
