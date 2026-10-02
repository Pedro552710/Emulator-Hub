"""Optionaler echter Downloadtest; alle Daten bleiben im angegebenen Testordner."""
import argparse
import json
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.catalog import Catalog
from core.installer import HubService


def main():
    parser = argparse.ArgumentParser(description="Echte offizielle Downloads und lokale Installation prüfen")
    parser.add_argument("--id", action="append", dest="identifiers")
    parser.add_argument("--data-dir", type=Path, default=Path("test-artifacts/live-data"))
    parser.add_argument("--keep", action="store_true", help="Testinstallationen für die Oberflächenprüfung behalten")
    args = parser.parse_args()
    catalog = Catalog()
    service = HubService(catalog, args.data_dir)
    event = threading.Event()
    reports = []
    try:
        for identifier in args.identifiers or ["melonds", "flycast"]:
            entry = catalog.by_id(identifier)
            last_phase = ""
            def progress(percent, phase):
                nonlocal last_phase
                if percent in (-1, 86, 95, 100) and phase != last_phase:
                    print(phase, flush=True)
                    last_phase = phase
            record = service.install(entry, progress, print, event, shortcuts={})
            assert service.is_installed(identifier)
            assert Path(record["exe_path"]).is_file()
            assert HubService(catalog, args.data_dir).installed[identifier]["version"] == record["version"]
            reports.append({"id": identifier, "version": record["version"],
                            "sha256": record["sha256"], "status": service.status(identifier)})
        service.check_updates(lambda *_: None, print, event)
        for report in reports:
            assert service.status(report["id"]) == "installiert"
    finally:
        if not args.keep:
            for report in reports:
                service.uninstall(catalog.by_id(report["id"]), print, event)
                assert report["id"] not in service.installed
    output = args.data_dir.parent / "live-report.json"
    output.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Downloadtest erfolgreich: {len(reports)} Emulatoren. Bericht: {output}")


if __name__ == "__main__":
    main()
