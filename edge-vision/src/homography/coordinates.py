"""FR-SUR-004 호모그래피 기반 수면 실좌표 변환.

``Calibration``: >=4 measured image/water-plane point pairs -> validated homography;
bbox anchor -> metres. ``navigation``: target vs board pose -> heading error, the
input of FR-NAV-003 (guidance), which lives outside this module.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from pathlib import Path

import cv2
import numpy as np


def calibration_view(source):
    """(calibration, editing, homography_hash) from a Calibration or a HomographyStore.

    Call once per frame and use the returned calibration for the whole frame: a store may swap
    its matrix at any time, and one frame must never mix the old and the new one.
    """
    if hasattr(source, "snapshot"):
        snapshot = source.snapshot()
        return snapshot.calibration, snapshot.editing, snapshot.homography_hash
    return source, False, getattr(source, "homography_hash", None)


class Calibration:
    homography_hash = None
    saved_at = None

    def __init__(self, config: dict, cache: Path | None = None):
        self.config = config if isinstance(config, dict) else {}
        self.matrix = None
        self.reason = "UNCALIBRATED"
        self.pixels = np.empty((0, 2))
        if not self.config:
            return
        try:
            self._load(cache)
            self.reason = "VALID"
        except (ValueError, TypeError, KeyError, cv2.error, np.linalg.LinAlgError) as exc:
            self.matrix = None
            self.reason = f"INVALID_CALIBRATION: {exc}"

    def _load(self, cache):
        c = self.config
        self.pixels = np.asarray(c["image_points"], dtype=np.float64)
        world = np.asarray(c["world_points"], dtype=np.float64)
        if (
            self.pixels.shape != world.shape
            or self.pixels.ndim != 2
            or self.pixels.shape[1] != 2
            or len(world) < 4
        ):
            raise ValueError("at least four paired 2D points required")
        for points in (self.pixels, world):
            if not np.isfinite(points).all() or len(np.unique(points, axis=0)) != len(points):
                raise ValueError("nonfinite or duplicate points")
            if np.linalg.matrix_rank(points - points.mean(axis=0)) < 2:
                raise ValueError("collinear points")
        for name in ("frame_id", "origin", "x_axis", "y_axis", "calibration_id"):
            if not isinstance(c.get(name), str) or not c[name].strip():
                raise ValueError(f"missing {name}")
        if c.get("unit") not in ("m", "normalized"):
            raise ValueError("world unit must be m or normalized")
        size = np.asarray(c["image_size"], dtype=float)
        bounds = np.asarray(c["world_bounds"], dtype=float)
        if size.shape != (2,) or not np.isfinite(size).all() or (size <= 0).any():
            raise ValueError("invalid image size")
        if (
            bounds.shape != (4,)
            or not np.isfinite(bounds).all()
            or bounds[0] >= bounds[2]
            or bounds[1] >= bounds[3]
        ):
            raise ValueError("invalid world bounds [xmin,ymin,xmax,ymax]")
        if ((self.pixels < 0) | (self.pixels > size)).any():
            raise ValueError("image points outside image")
        if ((world < bounds[:2]) | (world > bounds[2:])).any():
            raise ValueError("world points outside bounds")
        anchor = np.asarray(c.get("bbox_anchor", [0.5, 1.0]), dtype=float)
        if (
            anchor.shape != (2,)
            or not np.isfinite(anchor).all()
            or ((anchor < 0) | (anchor > 1)).any()
        ):
            raise ValueError("bbox_anchor must be two fractions in [0,1]")
        tolerance = float(c.get("max_error_m", 0.05))
        if not math.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("max_error_m must be positive")
        if c.get("roi") is not None:
            roi = np.asarray(c["roi"], dtype=np.float32)
            if (
                roi.ndim != 2
                or roi.shape[1] != 2
                or len(roi) < 3
                or not np.isfinite(roi).all()
                or not cv2.isContourConvex(roi)
                or abs(cv2.contourArea(roi)) < 1
            ):
                raise ValueError("ROI must be an ordered, convex pixel polygon")
        fingerprint = hashlib.sha256(json.dumps(c, sort_keys=True).encode()).hexdigest()
        matrix = None
        if cache and cache.exists():
            try:
                saved = json.loads(cache.read_text(encoding="utf-8"))
                if saved["fingerprint"] == fingerprint:
                    matrix = np.asarray(saved["matrix"], dtype=float)
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if matrix is None:
            matrix, _ = cv2.findHomography(self.pixels, world, method=0)
        if (
            matrix is None
            or matrix.shape != (3, 3)
            or not np.isfinite(matrix).all()
            or np.linalg.matrix_rank(matrix) != 3
        ):
            raise ValueError("singular homography")
        # A projective horizon through the calibrated hull indicates crossed pairs.
        denominators = np.c_[self.pixels, np.ones(len(world))] @ matrix[2]
        if np.any(np.abs(denominators) < 1e-10) or not (
            np.all(denominators > 0) or np.all(denominators < 0)
        ):
            raise ValueError("inconsistent correspondence order / projective horizon")
        projected = cv2.perspectiveTransform(self.pixels[None], matrix)[0]
        self.errors = np.linalg.norm(projected - world, axis=1)
        if not np.isfinite(self.errors).all() or self.errors.max() > tolerance:
            raise ValueError("calibration residual exceeds max_error_m")
        self.matrix = matrix
        if cache:
            try:
                cache.parent.mkdir(parents=True, exist_ok=True)
                temporary = cache.with_suffix(cache.suffix + ".tmp")
                temporary.write_text(
                    json.dumps({"fingerprint": fingerprint, "matrix": matrix.tolist()}),
                    encoding="utf-8",
                )
                temporary.replace(cache)
            except OSError:
                logging.getLogger(__name__).warning(
                    "Calibration valid but matrix cache could not be saved"
                )

    def point(self, pixel, image_size):
        if self.matrix is None:
            return None, self.reason
        if list(image_size) != self.config["image_size"]:
            return None, "IMAGE_SIZE_MISMATCH"
        p = np.asarray(pixel, dtype=float)
        if p.shape != (2,) or not np.isfinite(p).all():
            return None, "INVALID_PIXEL"
        hull = cv2.convexHull(self.pixels.astype(np.float32))
        if cv2.pointPolygonTest(hull, tuple(map(float, p)), False) < 0:
            return None, "OUTSIDE_CALIBRATED_AREA"
        if self.config.get("roi") is not None and self.config.get("exclude_outside_roi", True):
            if (
                cv2.pointPolygonTest(
                    np.asarray(self.config["roi"], dtype=np.float32), tuple(map(float, p)), False
                )
                < 0
            ):
                return None, "OUTSIDE_ROI"
        denominator = float(self.matrix[2] @ np.r_[p, 1])
        if abs(denominator) < 1e-10:
            return None, "PROJECTIVE_HORIZON"
        x, y = cv2.perspectiveTransform(p.reshape(1, 1, 2), self.matrix)[0, 0]
        xmin, ymin, xmax, ymax = self.config["world_bounds"]
        if not np.isfinite([x, y]).all() or not (
            xmin - 1e-8 <= x <= xmax + 1e-8 and ymin - 1e-8 <= y <= ymax + 1e-8
        ):
            return None, "OUTSIDE_WORLD_BOUNDS"
        return {
            "x": float(x),
            "y": float(y),
            "unit": self.config["unit"],
            "frame_id": self.config["frame_id"],
        }, "VALID"

    def bbox(self, bbox, image_size):
        b = np.asarray(bbox, dtype=float)
        if b.shape != (4,) or not np.isfinite(b).all() or b[2] <= b[0] or b[3] <= b[1]:
            return None, None, "INVALID_BBOX"
        anchor = self.config.get("bbox_anchor", [0.5, 1.0])
        if (
            not isinstance(anchor, (list, tuple))
            or len(anchor) != 2
            or not all(
                isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 1 for v in anchor
            )
        ):
            return None, None, "INVALID_ANCHOR"
        p = b[:2] + (b[2:] - b[:2]) * anchor
        world, reason = self.point(p, image_size)
        return {"x": float(p[0]), "y": float(p[1]), "unit": "pixel"}, world, reason

    def annotate(self, image):
        result = image.copy()
        if self.pixels.ndim != 2 or self.pixels.shape[1] != 2:
            return result
        for index, point in enumerate(self.pixels):
            if np.isfinite(point).all():
                p = tuple(map(int, point))
                cv2.circle(result, p, 5, (0, 255, 255), -1)
                cv2.putText(result, str(index), p, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        return result


def navigation(target, board, now, *, max_age=5.0, arrival_radius=0.2):
    """Board headings require explicit zero axis/direction in the world frame.

    zero_axis_deg=90, clockwise=True represents north-zero clockwise only when
    world +Y is north. Output uses the same convention as the board input.
    """
    result = dict(
        x=None,
        y=None,
        current_heading=None,
        target_heading=None,
        heading_error=None,
        status="NO_BOARD_POSITION",
    )
    if target is None:
        result["status"] = "NO_TARGET_COORDINATES"
        return result
    if not all(
        isinstance(target.get(k), (int, float)) and math.isfinite(target[k]) for k in ("x", "y")
    ):
        result["status"] = "INVALID_TARGET_COORDINATES"
        return result
    if not board:
        return result
    if board.get("frame_id") != target.get("frame_id") or board.get("unit") != target.get("unit", "m"):
        result["status"] = "COORDINATE_FRAME_MISMATCH"
        return result

    def fresh(value):
        return (
            isinstance(value, (int, float)) and math.isfinite(value) and 0 <= now - value <= max_age
        )

    if not all(
        isinstance(board.get(k), (int, float)) and math.isfinite(board[k]) for k in ("x", "y")
    ):
        return result
    if not fresh(board.get("position_timestamp")):
        result["status"] = "STALE_BOARD_POSITION"
        return result
    result.update(
        x=board["x"],
        y=board["y"],
        frame_id=board["frame_id"],
        position_timestamp=board["position_timestamp"],
        position_unit=board["unit"],
    )
    dx, dy = target["x"] - board["x"], target["y"] - board["y"]
    if math.hypot(dx, dy) <= arrival_radius:
        result["status"] = "ARRIVAL_CANDIDATE"
        return result
    zero, clockwise = board.get("zero_axis_deg"), board.get("clockwise")
    if (
        not isinstance(zero, (float, int))
        or not math.isfinite(zero)
        or not isinstance(clockwise, bool)
    ):
        result["status"] = "UNKNOWN_HEADING_CONVENTION"
        return result
    sign = -1 if clockwise else 1
    result.update(
        target_heading=(sign * (math.degrees(math.atan2(dy, dx)) - zero)) % 360,
        zero_axis_deg=zero,
        clockwise=clockwise,
        heading_unit="degree",
        status="NO_CURRENT_HEADING",
    )
    current = board.get("current_heading")
    if isinstance(current, (int, float)) and math.isfinite(current):
        if fresh(board.get("heading_timestamp")):
            result.update(
                current_heading=current % 360,
                heading_timestamp=board["heading_timestamp"],
                heading_error=(result["target_heading"] - current + 180) % 360 - 180,
                status="VALID",
            )
        else:
            result["status"] = "STALE_CURRENT_HEADING"
    return result
