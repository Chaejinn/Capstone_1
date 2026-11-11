"""Homography (water-plane) settings: calibration/homography.yaml. No ArUco here.

Keys:
    frame_id, calibration_id     coordinate-frame name / id of this calibration
    pool_width_m, pool_height_m  measured pool size (X = width, Y = height)
    image_size                   [width, height] of the calibration image (camera resolution)
    image_points                 4 clicked pixels: physical UL, UR, LR, LL
    matrix_file                  JSON cache of the matrix, relative to this file
    check_points                 independent verification points [{pixel: [u, v], world: [x, y]}]
    max_error_m                  pass limit for residual and check points (default 0.05)
    bbox_anchor                  [0.5, 1.0] = bottom centre of a person bbox
    homography_hash, saved_at    written by the editor; a stored hash must match the matrix
    units                        m (default) | normalized (written by /calib/commit)
    aspect_ratio, aspect_source  normalized only: width / height, auto | perspective | override.
                                 pool_width_m is then 1.0 and pool_height_m 1 / aspect_ratio; those
                                 two values are NOT metres although the key names stay.

Convention (docs/WEB_INTERFACE.md): origin = pool lower-left, +X right, +Y up, metres.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from src.homography.coordinates import Calibration
from src.homography.geometry import validate_quad

KEYS = ("frame_id", "calibration_id", "pool_width_m", "pool_height_m", "image_size", "image_points",
        "matrix_file", "check_points", "max_error_m", "bbox_anchor", "homography_hash", "saved_at",
        "units", "aspect_ratio", "aspect_source")
ASPECT_SOURCES = ("auto", "perspective", "override")
DEFAULT_MAX_ERROR_M = 0.05


class HomographyConfigError(ValueError):
    pass


def matrix_hash(matrix) -> str:
    """SHA-256 of the scale-normalised pixel->metre matrix (the web's homography_hash)."""
    h = np.asarray(matrix, dtype=float)
    return hashlib.sha256(json.dumps(np.round(h / h[2, 2], 12).tolist()).encode()).hexdigest()


def _number(data, key, where, positive=True):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) \
            or (positive and value <= 0):
        raise HomographyConfigError(f"{where}: {key}: must be a positive number, got {value!r}")
    return float(value)


def world_corners(width_m, height_m):
    """World points for image_points clicked as UL, UR, LR, LL."""
    return [[0, height_m], [width_m, height_m], [width_m, 0], [0, 0]]


def calibration_config(data: dict, where: str) -> dict | None:
    """Validated dict for coordinates.Calibration, or None when not calibrated yet."""
    if not isinstance(data, dict):
        raise HomographyConfigError(f"{where}: must be a mapping")
    unknown = set(data) - set(KEYS)
    if unknown:
        raise HomographyConfigError(f"{where}: unknown key(s): {', '.join(sorted(unknown))}")
    width = _number(data, "pool_width_m", where)
    height = _number(data, "pool_height_m", where)
    max_error = float(data.get("max_error_m", DEFAULT_MAX_ERROR_M))
    if not math.isfinite(max_error) or max_error <= 0:
        raise HomographyConfigError(f"{where}: max_error_m: must be positive")
    units = data.get("units", "m")
    if units not in ("m", "normalized"):
        raise HomographyConfigError(f"{where}: units: must be m or normalized, got {units!r}")
    extra = {}
    if units == "normalized":
        aspect = _number(data, "aspect_ratio", where)
        if data.get("aspect_source") not in ASPECT_SOURCES:
            raise HomographyConfigError(f"{where}: aspect_source: must be one of {ASPECT_SOURCES}")
        if abs(width - 1.0) > 1e-9 or abs(height - 1.0 / aspect) > 1e-6:
            raise HomographyConfigError(f"{where}: pool_width_m / pool_height_m: normalized needs 1.0 and 1 / aspect_ratio")
        extra = {"aspect_ratio": aspect, "aspect_source": data["aspect_source"]}
    points = data.get("image_points") or []
    if not points:
        return None
    if len(points) != 4:
        raise HomographyConfigError(f"{where}: image_points: need exactly 4 points (UL, UR, LR, LL), got {len(points)}")
    for key in ("frame_id", "calibration_id"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise HomographyConfigError(f"{where}: {key}: required once image_points are set")
    size = data.get("image_size")
    if not (isinstance(size, list) and len(size) == 2 and all(type(v) is int and v > 0 for v in size)):
        raise HomographyConfigError(f"{where}: image_size: must be [width, height] integers, got {size!r}")
    # Enforce the editor's topology checks at runtime too. Perspective can change
    # pixel aspect, so the aspect heuristic remains an editor-only warning/gate.
    issues = validate_quad(points, size, width, height, check_aspect=False)
    if issues:
        raise HomographyConfigError(f"{where}: image_points: {'; '.join(issues)}")
    for i, check in enumerate(data.get("check_points") or []):
        if not (isinstance(check, dict) and set(check) == {"pixel", "world"}
                and all(isinstance(check[k], list) and len(check[k]) == 2 for k in check)):
            raise HomographyConfigError(f"{where}: check_points[{i}]: must be {{pixel: [u, v], world: [x, y]}}")
    return dict(
        image_points=points, world_points=world_corners(width, height), image_size=size,
        pool_width_m=width, pool_height_m=height, world_bounds=[0, 0, width, height], unit=units, **extra,
        frame_id=data["frame_id"], calibration_id=data["calibration_id"],
        origin="physical lower-left corner", x_axis="physical right", y_axis="physical up",
        bbox_anchor=data.get("bbox_anchor", [0.5, 1.0]), max_error_m=max_error, roi=points,
        exclude_outside_roi=True,
    )


def load_homography(path, *, require_calibrated=False) -> Calibration:
    """Calibration from calibration/homography.yaml. Wrong values raise; an empty
    image_points list yields an UNCALIBRATED Calibration unless require_calibrated."""
    import yaml

    path = Path(path)
    if not path.is_file():
        raise HomographyConfigError(f"{path}: homography config file not found "
                                    "(create it with scripts/homography/calib_server.py)")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise HomographyConfigError(f"{path}: invalid YAML: {exc}") from None
    config = calibration_config(data, str(path))
    if config is None:
        if require_calibrated:
            raise HomographyConfigError(f"{path}: image_points: empty, not calibrated yet "
                                        "(run scripts/homography/calib_server.py)")
        calibration = Calibration({})
    else:
        matrix_file = data.get("matrix_file")
        cache = path.parent / matrix_file if matrix_file else None
        calibration = Calibration(config, cache)
        if calibration.matrix is None:
            raise HomographyConfigError(f"{path}: {calibration.reason}")
        calibration.homography_hash = matrix_hash(calibration.matrix)
        stored = data.get("homography_hash")
        if stored and stored != calibration.homography_hash:
            raise HomographyConfigError(f"{path}: homography_hash: does not match the matrix "
                                        "(file edited by hand or partially written)")
    calibration.saved_at = (data or {}).get("saved_at")
    calibration.check_points = (data or {}).get("check_points") or []
    calibration.source = str(path)
    return calibration


def check_point_errors(calibration: Calibration, check_points) -> list[dict]:
    """Per verification point: projected metres and error in cm (None if not projectable)."""
    rows = []
    size = calibration.config.get("image_size")
    for check in check_points:
        world, reason = calibration.point(check["pixel"], size)
        expected = np.asarray(check["world"], dtype=float)
        error = None if world is None else float(np.hypot(world["x"] - expected[0], world["y"] - expected[1]))
        rows.append({"pixel": check["pixel"], "expected": list(map(float, expected)),
                     "measured": None if world is None else [world["x"], world["y"]],
                     "error_cm": None if error is None else error * 100, "reason": reason})
    return rows
