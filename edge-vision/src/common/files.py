"""File helpers shared by the homography editors and route planner (no camera, no GUI).

Path overrides: CLI flags set these environment variables, so every loader (runtime, preflight,
deployment check, scripts) resolves the same file. An override that points at a missing or bad
file raises from the loader; it never falls back to the default.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import time

HOMOGRAPHY_FILE_ENV = "HOMOGRAPHY_FILE"
ARUCO_CONFIG_ENV = "ARUCO_CONFIG"
ROUTE_CONFIG_ENV = "ROUTE_CONFIG"
CALIB_CONFIG_ENV = "CALIB_CONFIG"


def path_override(env_name: str) -> Path | None:
    value = os.getenv(env_name, "").strip()
    return Path(value).resolve() if value else None


def homography_path(base: Path, config: dict) -> Path:
    return path_override(HOMOGRAPHY_FILE_ENV) or Path(base) / config["homography_config"]


def aruco_path(base: Path, config: dict) -> Path:
    return path_override(ARUCO_CONFIG_ENV) or Path(base) / config["aruco_config"]


def calib_config_path(base: Path, config: dict) -> Path:
    override = path_override(CALIB_CONFIG_ENV)
    if override:
        return override
    if "calibration_api_config" not in config:
        raise KeyError("calibration_api_config: missing in the vision config (or set CALIB_CONFIG / --calib-config)")
    return Path(base) / config["calibration_api_config"]


def utc_now_iso(now: float | None = None) -> str:
    moment = datetime.now(timezone.utc) if now is None else datetime.fromtimestamp(now, timezone.utc)
    return moment.isoformat().replace("+00:00", "Z")


def backup_file(path: Path, now: float | None = None, suffix: str = ".bak") -> Path | None:
    """Copy `path` to `<name>.<UTC stamp><suffix>` next to it; None when there is nothing to back up."""
    path = Path(path)
    if not path.is_file():
        return None
    moment = datetime.now(timezone.utc) if now is None else datetime.fromtimestamp(now, timezone.utc)
    stem = f"{path.name}.{moment.strftime('%Y%m%dT%H%M%SZ')}"
    target, counter = path.with_name(f"{stem}{suffix}"), 0
    while target.exists():
        counter += 1
        target = path.with_name(f"{stem}_{counter}{suffix}")
    shutil.copy2(path, target)
    return target


def _replace(source: Path, target: Path, attempts: int = 10) -> None:
    # On Windows a reader holding the target open makes os.replace fail briefly.
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.02)


def atomic_write_text(path: Path, text: str) -> None:
    """Write to a temp file in the same directory, fsync, then replace. On any failure the
    existing file is untouched and the temp file is removed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with open(temporary, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        _replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
