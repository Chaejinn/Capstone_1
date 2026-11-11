"""Homography editing logic without a window: quad checks, point edits, grid, atomic save.

src/homography/editor.py is the OpenCV front end; everything testable lives here.
Never imports ArUco. Points are in image pixels; the order is the PHYSICAL pool corners
upper-left, upper-right, lower-right, lower-left, clockwise on screen.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
from uuid import uuid4

import cv2
import numpy as np

from src.common.files import atomic_write_text, backup_file, utc_now_iso
from src.homography.coordinates import Calibration
from src.homography.loader import (HomographyConfigError, calibration_config, check_point_errors,
                                         matrix_hash)

from src.homography.geometry import validate_quad
GRID_SPACING_M = 0.10
PICK_RADIUS_PX = 18
MAX_UNDO = 200
# Display-only grid: each pool side is split into GRID_UNITS (X: 0 = left .. 1000 = right,
# Y: 0 = bottom .. 1000 = top), with a line every GRID_UNIT_STEP. Calculations and the web
# keep metres; this is only an easier-to-read scale on the editor screen.
GRID_UNITS = 1000
GRID_UNIT_STEP = 100
# Measurement points the operator places by hand to read positions and their distance.
# They are never used for the homography and never saved or sent anywhere.
MEASURE_KINDS = {"board": "보드", "victim": "익수자"}

_LINE = r"^({key}:[ \t]*)([^#\r\n]*?)([ \t]*(?:#[^\r\n]*)?)(\r?\n)?$"


def set_yaml_keys(text: str, values: dict, *, append_missing: bool = False, drop_comments=()) -> str:
    """Replace complete YAML values, including block lists, preserving comments."""
    import yaml
    for key, value in values.items():
        lines = text.splitlines(keepends=True)
        document = yaml.compose(text)
        if not isinstance(document, yaml.MappingNode):
            raise ValueError('homography config must be a YAML mapping')
        pattern = re.compile(_LINE.format(key=re.escape(key)))
        rendered = json.dumps(value, ensure_ascii=False)
        for index, (key_node, _value_node) in enumerate(document.value):
            if key_node.value == key:
                begin = key_node.start_mark.line
                end = (document.value[index+1][0].start_mark.line
                       if index+1 < len(document.value) else len(lines))
                match = pattern.match(lines[begin])
                comment = '' if key in drop_comments or not match else match.group(3)
                if comment and not comment.startswith((' ','\t')):
                    comment = ' '+comment
                notes = [line for line in lines[begin+1:end]
                         if not line.strip() or line.lstrip().startswith('#')]
                lines[begin:end] = [f'{key}: {rendered}{comment}\n', *notes]
                break
        else:
            if not append_missing:
                raise ValueError(f"{key} not found in homography config")
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            lines.append(f"{key}: {rendered}\n")
        text = ''.join(lines)
    return text



def build_calibration(points, width_m, height_m, image_size, *, frame_id, calibration_id,
                      max_error_m=0.05, bbox_anchor=None, units="m") -> Calibration | None:
    """Calibration from candidate values (never touches a file); None when not computable."""
    data = dict(pool_width_m=width_m, pool_height_m=height_m, image_size=list(image_size),
                image_points=[list(p) for p in points], frame_id=frame_id,
                calibration_id=calibration_id, max_error_m=max_error_m)
    if bbox_anchor is not None:
        data["bbox_anchor"] = bbox_anchor
    if units == "normalized":
        data.update(units=units, aspect_ratio=float(width_m) / float(height_m), aspect_source="auto")
    try:
        calibration = Calibration(calibration_config(data, "<draft>"))
    except HomographyConfigError:
        return None
    return calibration if calibration.matrix is not None else None


def world_to_pixel(matrix, world_points) -> np.ndarray:
    """Project Nx2 metres back to image pixels with the inverse of a pixel->metre matrix."""
    points = np.asarray(world_points, dtype=float).reshape(-1, 1, 2)
    return cv2.perspectiveTransform(points, np.linalg.inv(matrix)).reshape(-1, 2)


def _ticks(limit: float, spacing: float) -> list[float]:
    count = int(math.floor(limit / spacing + 1e-9))
    ticks = [i * spacing for i in range(count + 1)]
    return ticks + [limit] if limit - ticks[-1] > 1e-6 else ticks


def grid_lines(matrix, width_m, height_m, spacing=GRID_SPACING_M) -> list[tuple]:
    """Floor grid as pixel segments ((u1, v1), (u2, v2)), including the pool edges."""
    segments = [((x, 0.0), (x, height_m)) for x in _ticks(width_m, spacing)]
    segments += [((0.0, y), (width_m, y)) for y in _ticks(height_m, spacing)]
    projected = world_to_pixel(matrix, np.asarray(segments).reshape(-1, 2)).reshape(-1, 2, 2)
    return [(tuple(a), tuple(b)) for a, b in projected.tolist()]


def to_grid_units(x_m: float, y_m: float, width_m: float, height_m: float) -> tuple[float, float]:
    """Metres -> the 0..GRID_UNITS display scale (each axis scaled by its own pool side)."""
    return x_m / width_m * GRID_UNITS, y_m / height_m * GRID_UNITS


def unit_grid_lines(matrix, width_m, height_m, step=GRID_UNIT_STEP) -> list[dict]:
    """0..GRID_UNITS grid as pixel segments: [{axis, value, a, b}, ...].

    axis "x" = a vertical line at X = value (runs bottom to top); axis "y" = a horizontal line
    at Y = value (runs left to right). value 0 lines are the X/Y axes through the origin
    (physical lower-left corner).
    """
    if not 0 < step <= GRID_UNITS:
        raise ValueError("grid step must be in (0, GRID_UNITS]")
    values = list(range(0, GRID_UNITS + 1, int(step)))
    if values[-1] != GRID_UNITS:
        values.append(GRID_UNITS)
    meta, segments = [], []
    for value in values:
        x = value / GRID_UNITS * width_m
        meta.append(("x", value))
        segments.append(((x, 0.0), (x, height_m)))
    for value in values:
        y = value / GRID_UNITS * height_m
        meta.append(("y", value))
        segments.append(((0.0, y), (width_m, y)))
    projected = world_to_pixel(matrix, np.asarray(segments).reshape(-1, 2)).reshape(-1, 2, 2)
    return [{"axis": axis, "value": value, "a": tuple(a), "b": tuple(b)}
            for (axis, value), (a, b) in zip(meta, projected.tolist())]


def measure_point(calibration, pixel, image_size, width_m, height_m) -> dict:
    """One hand-placed point: pixel -> metres and grid units through the draft homography."""
    row = {"pixel": [int(pixel[0]), int(pixel[1])], "world": None, "units": None, "reason": None}
    if calibration is None:
        row["reason"] = "homography_not_computable"
        return row
    world, reason = calibration.point(pixel, image_size)
    if world is None:
        row["reason"] = reason
        return row
    row["world"] = [world["x"], world["y"]]
    row["units"] = list(to_grid_units(world["x"], world["y"], width_m, height_m))
    return row


def measure_rows(calibration, points: dict, image_size, width_m, height_m) -> dict:
    """{kind: row} for every placed kind, plus "distance_m" between board and victim (or None)."""
    rows = {kind: measure_point(calibration, pixel, image_size, width_m, height_m)
            for kind, pixel in points.items() if pixel is not None}
    board, victim = rows.get("board"), rows.get("victim")
    distance = None
    if board and victim and board["world"] and victim["world"]:
        distance = math.dist(board["world"], victim["world"])
    return {"rows": rows, "distance_m": distance}


class HomographyEditState:
    """Everything the editor screen changes. No drawing and no file access."""

    def __init__(self, points, width_m, height_m, image_size, *, frame_id, calibration_id,
                 check_points=(), max_error_m=0.05, bbox_anchor=None):
        self.points = [[int(round(u)), int(round(v))] for u, v in points]
        self.width_m, self.height_m = float(width_m), float(height_m)
        self.image_size = tuple(image_size)
        self.frame_id, self.calibration_id = frame_id, calibration_id
        self.check_points = [dict(c) for c in check_points]
        self.max_error_m, self.bbox_anchor = max_error_m, bbox_anchor
        self.units, self.aspect_ratio, self.aspect_source = "m", None, None
        self.selected = 0
        self._undo = []
        self._dragging = None
        self._saved = self._memento()

    def _memento(self):
        return ([list(p) for p in self.points], self.width_m, self.height_m,
                [dict(c) for c in self.check_points])

    def _restore(self, memento):
        points, self.width_m, self.height_m, checks = memento
        self.points = [list(p) for p in points]
        self.check_points = [dict(c) for c in checks]

    def _remember(self):
        self._undo.append(self._memento())
        del self._undo[:-MAX_UNDO]

    @property
    def dirty(self) -> bool:
        return self._memento() != self._saved

    def select(self, index: int) -> None:
        if not 0 <= index < 4:
            raise ValueError("point index must be 0-3")
        self.selected = index

    def nudge(self, dx: int, dy: int) -> None:
        self._remember()
        self.points[self.selected][0] += dx
        self.points[self.selected][1] += dy

    def pick(self, pixel, radius: int = PICK_RADIUS_PX) -> int | None:
        distances = [math.hypot(p[0] - pixel[0], p[1] - pixel[1]) for p in self.points]
        best = int(np.argmin(distances))
        return best if distances[best] <= radius else None

    def begin_drag(self, pixel) -> bool:
        index = self.pick(pixel)
        if index is None:
            return False
        self.selected, self._dragging = index, index
        self._remember()
        return True

    def drag(self, pixel) -> None:
        if self._dragging is not None:
            self.points[self._dragging] = [int(pixel[0]), int(pixel[1])]

    def end_drag(self) -> None:
        self._dragging = None

    def undo(self) -> bool:
        if not self._undo:
            return False
        self._restore(self._undo.pop())
        return True

    def revert(self) -> None:
        """r: back to the last saved values."""
        self._remember()
        self._restore(self._saved)

    def set_size(self, width_m, height_m) -> str | None:
        if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in (width_m, height_m)):
            return "수조 크기는 0보다 큰 숫자여야 함"
        self._remember()
        self.width_m, self.height_m = float(width_m), float(height_m)
        return None

    def add_check(self, pixel, world) -> None:
        self._remember()
        self.check_points.append({"pixel": [int(pixel[0]), int(pixel[1])],
                                  "world": [float(world[0]), float(world[1])]})

    def clear_checks(self) -> None:
        self._remember()
        self.check_points = []

    def issues(self) -> list[str]:
        return validate_quad(self.points, self.image_size, self.width_m, self.height_m,
                             check_aspect=self.units == "m")

    def draft(self) -> Calibration | None:
        return build_calibration(self.points, self.width_m, self.height_m, self.image_size,
                                 frame_id=self.frame_id, calibration_id=self.calibration_id or "draft",
                                 max_error_m=self.max_error_m, bbox_anchor=self.bbox_anchor, units=self.units)

    def check_rows(self, calibration=None) -> list[dict]:
        calibration = calibration or self.draft()
        return [] if calibration is None else check_point_errors(calibration, self.check_points)


def read_edit_state(path, image_size) -> HomographyEditState:
    """Editor start values from the file. An uncalibrated file starts with a centred quad."""
    import yaml

    path = Path(path)
    if not path.is_file():
        raise HomographyConfigError(f"{path}: homography config file not found")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise HomographyConfigError(f"{path}: invalid YAML: {exc}") from None
    calibration_config(data, str(path))  # same key/value errors as the runtime
    points = data.get("image_points") or []
    if not points:
        w, h = image_size
        points = [[w // 4, h // 6], [3 * w // 4, h // 6], [3 * w // 4, 5 * h // 6], [w // 4, 5 * h // 6]]
    state = HomographyEditState(points, data["pool_width_m"], data["pool_height_m"], image_size,
                                frame_id=data.get("frame_id") or "pool-01",
                                calibration_id=data.get("calibration_id"),
                                check_points=data.get("check_points") or [],
                                max_error_m=data.get("max_error_m", 0.05),
                                bbox_anchor=data.get("bbox_anchor"))
    state.saved_image_size = data.get("image_size")
    state.units, state.aspect_ratio, state.aspect_source = (data.get("units", "m"), data.get("aspect_ratio"),
                                                            data.get("aspect_source"))
    return state


def save_homography(path, state: HomographyEditState, now: float | None = None) -> dict:
    """Validate, back up the old files, then replace the config atomically.

    Raises HomographyConfigError (nothing written) when the values are invalid; an I/O failure
    during the write leaves the previous file in place. Returns saved metadata.
    """
    import yaml

    path = Path(path)
    issues = state.issues()
    if issues:
        raise HomographyConfigError(f"{path}: not saved: " + "; ".join(issues))
    calibration_id = str(uuid4())
    calibration = build_calibration(state.points, state.width_m, state.height_m, state.image_size,
                                    frame_id=state.frame_id, calibration_id=calibration_id,
                                    max_error_m=state.max_error_m, bbox_anchor=state.bbox_anchor, units=state.units)
    if calibration is None:
        raise HomographyConfigError(f"{path}: not saved: homography could not be computed")
    meta = {"homography_hash": matrix_hash(calibration.matrix), "saved_at": utc_now_iso(now)}
    text = path.read_text(encoding="utf-8")
    new_text = set_yaml_keys(text, {
        "calibration_id": calibration_id, "pool_width_m": state.width_m, "pool_height_m": state.height_m,
        "image_size": list(state.image_size), "image_points": state.points,
        "check_points": state.check_points, **meta,
        **({"units": "normalized", "aspect_ratio": state.aspect_ratio, "aspect_source": state.aspect_source}
           if state.units == "normalized" else {}),
    }, append_missing=True,
        drop_comments=("pool_width_m", "pool_height_m") if state.units == "normalized" else ())
    data = yaml.safe_load(new_text)
    if calibration_config(data, str(path)) is None:
        raise HomographyConfigError(f"{path}: not saved: image_points empty")
    backups = [backup_file(path, now)]
    matrix_file = data.get("matrix_file")
    if matrix_file:  # the runtime regenerates this cache on load
        backups.append(backup_file(path.parent / matrix_file, now))
    atomic_write_text(path, new_text)
    state._saved = state._memento()
    state.calibration_id = calibration_id
    return {**meta, "calibration_id": calibration_id, "path": str(path),
            "backups": [str(b) for b in backups if b is not None]}
