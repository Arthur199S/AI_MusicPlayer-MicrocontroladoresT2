"""Metricas de sistema do Raspberry Pi (CPU/RAM/disco/temp)."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def system_metrics() -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "cpu_percent": None,
        "ram_used_mb": None,
        "ram_total_mb": None,
        "ram_percent": None,
        "disk_used_gb": None,
        "disk_total_gb": None,
        "disk_percent": None,
        "temp_c": None,
    }
    try:
        import psutil
    except ImportError:
        return metrics

    metrics["cpu_percent"] = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    metrics["ram_used_mb"] = round(mem.used / (1024 ** 2), 1)
    metrics["ram_total_mb"] = round(mem.total / (1024 ** 2), 1)
    metrics["ram_percent"] = mem.percent
    disk = psutil.disk_usage("/")
    metrics["disk_used_gb"] = round(disk.used / (1024 ** 3), 2)
    metrics["disk_total_gb"] = round(disk.total / (1024 ** 3), 2)
    metrics["disk_percent"] = disk.percent

    thermal = Path("/sys/class/thermal/thermal_zone0/temp")
    if thermal.exists():
        try:
            raw = int(thermal.read_text().strip())
            metrics["temp_c"] = round(raw / 1000.0, 1)
        except (OSError, ValueError):
            pass
    return metrics
