"""Lokale Hardwaredaten und ausdrücklich grobe, konfigurierbare Einschätzung."""
from datetime import datetime, timezone
import json
import math
import os
import platform
import subprocess

import psutil

from .errors import HubError, Cancelled
from .paths import config_path
from .state import read_json


def load_thresholds(data_dir=None):
    config = read_json(config_path("system_requirements.json", data_dir), None, "Systemcheck-Konfiguration")
    if not isinstance(config, dict) or config.get("schema_version") != 1 or not isinstance(config.get("levels"), dict):
        raise HubError("Die Systemcheck-Konfiguration ist ungültig.")
    for level, values in config["levels"].items():
        if not isinstance(values, dict):
            raise HubError(f"Ungültige Systemcheck-Schwelle: {level}.")
        for kind in ("minimum", "recommended"):
            thresholds = values.get(kind)
            if not isinstance(thresholds, dict) or any(
                not isinstance(thresholds.get(k), (int, float)) or isinstance(thresholds[k], bool) or thresholds[k] < 0
                or not math.isfinite(thresholds[k]) for k in ("cpu_cores", "ram_gb", "gpu_score")
            ):
                raise HubError(f"Ungültige Systemcheck-Schwelle: {level}/{kind}.")
        if any(values["minimum"][k] > values["recommended"][k] for k in ("cpu_cores", "ram_gb", "gpu_score")):
            raise HubError(f"Die Mindestwerte für {level} dürfen nicht über den empfohlenen Werten liegen.")
    if not isinstance(config.get("gpu_classes"), dict) or not isinstance(config.get("gpu_keywords"), dict):
        raise HubError("GPU-Klassen fehlen in der Systemcheck-Konfiguration.")
    tolerance = config.get("ram_tolerance_gb", 0)
    if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool) or not math.isfinite(tolerance) or tolerance < 0:
        raise HubError("Die RAM-Toleranz muss eine nicht negative Zahl sein.")
    for kind in ("unknown", "high_end", "dedicated", "integrated"):
        score = config["gpu_classes"].get(kind)
        keywords = config["gpu_keywords"].get(kind)
        if (not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score) or score < 0
                or not isinstance(keywords, list) or any(not isinstance(word, str) or not word.strip() for word in keywords)):
            raise HubError(f"Ungültige GPU-Klasse oder Schlüsselwörter: {kind}.")
    return config


def classify_gpu(name, config):
    value = name.casefold()
    for kind in ("unknown", "high_end", "dedicated", "integrated"):
        if any(keyword.casefold() in value for keyword in config["gpu_keywords"].get(kind, [])):
            return kind, config["gpu_classes"].get(kind, 0)
    return "unknown", 0


def detect_hardware(progress, log, cancel_event, config):
    if cancel_event.is_set():
        raise Cancelled()
    progress(10, "CPU und Arbeitsspeicher auslesen …")
    frequency = psutil.cpu_freq()
    cores = psutil.cpu_count(logical=False)
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "cpu_name": platform.processor() or "CPU-Modell nicht erkannt",
        "cpu_cores": cores, "cpu_threads": psutil.cpu_count(logical=True),
        "cpu_mhz": (frequency.max or frequency.current) if frequency else None,
        "ram_gb": round(psutil.virtual_memory().total / 1024 ** 3, 2),
        "gpus": [], "gpu_score": None, "warnings": [],
        "disclaimer": config.get("disclaimer", "Grobe Einschätzung, keine Garantie."),
    }
    progress(40, "GPU über lokale Windows-Systeminformationen auslesen …")
    if os.name == "nt":
        script = (
            "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
            "$ErrorActionPreference='Stop'; "
            "$c=Get-CimInstance Win32_Processor | Select-Object Name; "
            "$g=Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM,DriverVersion; "
            "@{cpus=@($c);gpus=@($g)} | ConvertTo-Json -Depth 4 -Compress"
        )
        try:
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                    capture_output=True, timeout=20,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise ValueError("Die Windows-Abfrage wurde abgewiesen.")
            info = json.loads(result.stdout.decode("utf-8-sig"))
            if not isinstance(info, dict) or not isinstance(info.get("cpus"), list) or not isinstance(info.get("gpus"), list):
                raise ValueError("Ungültige lokale Windows-Systeminformationen.")
            if info.get("cpus"):
                report["cpu_name"] = " / ".join(str(c.get("Name", "")).strip() for c in info["cpus"])
            for gpu in info.get("gpus", []):
                name = str(gpu.get("Name", "Unbekannte GPU"))
                kind, score = classify_gpu(name, config)
                report["gpus"].append({"name": name, "class": kind, "score": score,
                                       "driver": str(gpu.get("DriverVersion", ""))})
            known = [g["score"] for g in report["gpus"] if g["class"] != "unknown"]
            report["gpu_score"] = max(known) if known else None
        except (OSError, ValueError, TypeError, subprocess.TimeoutExpired) as exc:
            report["warnings"].append(f"Die GPU konnte nicht zuverlässig ausgelesen werden: {exc}")
    else:
        report["warnings"].append("Die GPU-Abfrage ist für Windows vorgesehen.")
    if report["gpu_score"] is None:
        report["warnings"].append("GPU-Leistung unbekannt; eine Einstufung kann daher nur vorläufig erfolgen.")
    if cancel_event.is_set():
        raise Cancelled()
    progress(100, "Systemcheck abgeschlossen.")
    log(f"Systemcheck: {report['cpu_name']}, {cores if cores is not None else '?'} CPU-Kerne, {report['ram_gb']:.1f} GiB RAM.")
    for warning in report["warnings"]:
        log(warning)
    return report


def assess(entry, report, config):
    if not report:
        return {"status": "Unbekannt", "reason": "Bitte zunächst einen Systemcheck durchführen."}
    level = config["levels"].get(entry.get("pc_anforderung"))
    if not level:
        return {"status": "Unbekannt", "reason": "Für diese PC-Anforderung ist keine Schwelle konfiguriert."}
    measurements = {"cpu_cores": report.get("cpu_cores"), "ram_gb": report.get("ram_gb"), "gpu_score": report.get("gpu_score")}
    names = {"cpu_cores": "CPU-Kerne", "ram_gb": "GiB RAM", "gpu_score": "GPU-Klasse"}
    minimum_failures, recommended_failures, unknown = [], [], []
    for key, value in measurements.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value < 0:
            value = None
        if value is None and level["recommended"][key] > 0:
            unknown.append(names[key])
        elif value is not None:
            compared = value + (config.get("ram_tolerance_gb", 0) if key == "ram_gb" else 0)
            if compared < level["minimum"][key]:
                minimum_failures.append(f"{names[key]}: {value:g} vorhanden, mindestens {level['minimum'][key]:g} vorgesehen")
            elif compared < level["recommended"][key]:
                recommended_failures.append(f"{names[key]} unter der empfohlenen Schwelle ({value:g} / {level['recommended'][key]:g})")
    if minimum_failures:
        return {"status": "Zu schwach", "reason": "; ".join(minimum_failures) + ". Grobe Einschätzung."}
    if unknown or recommended_failures:
        return {"status": "Grenzwertig", "reason": "; ".join(recommended_failures + (["Nicht zuverlässig erkannt: " + ", ".join(unknown)] if unknown else [])) + ". Grobe Einschätzung."}
    return {"status": "Läuft gut", "reason": "Die konfigurierten empfohlenen Hardware-Schwellen werden erreicht. Grobe Einschätzung, keine Garantie."}
