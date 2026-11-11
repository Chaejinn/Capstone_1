"""ArUco marker settings and pixel-space measurement (no homography here).

configs/aruco.yaml (profile form, 2026-11-05):
    dictionary: DICT_4X4_50
    profile: standin            active profile (standin = printed boat photo, boat = real boat)
    profiles:
      <name>:
        marker_length_m       printed black-square side (record; planar scale = homography)
        board_marker_id       marker ID used by this profile
        heading_offset_deg    float, or null = NOT MEASURED (never silently 0)
        missing_offset        reject | warn  (what the runtime does while the offset is null)
        session               null or {measured_at, camera_resolution, image_session, method}
Each profile keeps its own offset; writing one never touches another.
The legacy flat form (dictionary, marker_length_m, board_marker_id, heading_offset_deg,
heading_offset_source) is still accepted.

This module never imports or reads the homography (calibration) configuration. The only
place that combines marker pixels with the homography is src/aruco/board.py.

Pixel heading convention: image "up" (row 0 side) is +Y, image right is +X, angle 0 deg = +X,
counter-clockwise positive. With a top-down camera whose image axes match the pool
(origin lower-left, +X right, +Y far side = image up) this equals the world heading.
The marker's TOP edge (corners 0->1) is the bow.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import logging
import math
from pathlib import Path

import cv2
import numpy as np


class ArucoConfigError(ValueError):
    """Raised with the file and key that is wrong; never silently defaulted."""


@dataclass(frozen=True)
class ArucoSettings:
    dictionary: str
    marker_length_m: float
    board_marker_id: int
    heading_offset_deg: float | None
    heading_offset_source: str | None = None
    source: str = "<memory>"
    profile: str | None = None
    session: dict | None = None
    missing_offset: str = "reject"

    @property
    def offset_measured(self) -> bool:
        if self.heading_offset_deg is None:
            return False
        if self.profile is not None:
            return self.session is not None
        return self.heading_offset_source is not None


REQUIRED = ("dictionary", "marker_length_m", "board_marker_id", "heading_offset_deg")
PROFILE_KEYS = ("marker_length_m", "board_marker_id", "heading_offset_deg", "missing_offset", "session")
MISSING_OFFSET = ("reject", "warn")
SESSION_KEYS = ("measured_at", "camera_resolution", "image_session", "method")


def _dictionary(name, where):
    aruco = getattr(cv2, "aruco", None)
    if aruco is None:
        raise RuntimeError("This OpenCV build has no ArUco; install opencv-contrib-python")
    if not isinstance(name, str) or not name.startswith("DICT_") or not hasattr(aruco, name):
        raise ArucoConfigError(f"{where}: dictionary: unknown ArUco dictionary {name!r}")
    return aruco.getPredefinedDictionary(getattr(aruco, name))


def _common(data, where, source, dictionary_name):
    dictionary = _dictionary(dictionary_name, source)
    length = data["marker_length_m"]
    if isinstance(length, bool) or not isinstance(length, (int, float)) or not math.isfinite(length) \
            or not 0 < length <= 5:
        raise ArucoConfigError(f"{where}marker_length_m: must be a positive number of metres, got {length!r}")
    marker = data["board_marker_id"]
    if type(marker) is not int or not 0 <= marker < len(dictionary.bytesList):
        raise ArucoConfigError(
            f"{where}board_marker_id: must be an integer in [0, {len(dictionary.bytesList)}) "
            f"for {dictionary_name}, got {marker!r}")
    offset = data["heading_offset_deg"]
    if offset is not None and (isinstance(offset, bool) or not isinstance(offset, (int, float))
                               or not math.isfinite(offset) or not -360 < offset < 360):
        raise ArucoConfigError(
            f"{where}heading_offset_deg: must be null or a number in (-360, 360), got {offset!r}")
    return float(length), marker, None if offset is None else float(offset)


def settings_from_mapping(data, source="<memory>", profile=None) -> ArucoSettings:
    if not isinstance(data, dict):
        raise ArucoConfigError(f"{source}: must be a mapping")
    if "profiles" in data:
        return _profile_settings(data, source, profile)
    if profile is not None:
        raise ArucoConfigError(f"{source}: profile {profile!r} requested but the file has no profiles")
    missing = [k for k in REQUIRED if k not in data]
    if missing:
        raise ArucoConfigError(f"{source}: missing key(s): {', '.join(missing)}")
    unknown = set(data) - set(REQUIRED) - {"heading_offset_source"}
    if unknown:
        raise ArucoConfigError(f"{source}: unknown key(s): {', '.join(sorted(unknown))}")
    length, marker, offset = _common(data, f"{source}: ", source, data["dictionary"])
    if offset is None:
        raise ArucoConfigError(f"{source}: heading_offset_deg: must be a number "
                               "(use the profile form for an unmeasured null)")
    offset_source = data.get("heading_offset_source")
    if offset_source is not None and (not isinstance(offset_source, str) or not offset_source.strip()):
        raise ArucoConfigError(f"{source}: heading_offset_source: must be null or a non-empty string")
    return ArucoSettings(data["dictionary"], length, marker, offset, offset_source, source)


def _profile_settings(data, source, requested):
    unknown = set(data) - {"dictionary", "profile", "profiles"}
    if unknown:
        raise ArucoConfigError(f"{source}: unknown key(s): {', '.join(sorted(unknown))}")
    for key in ("dictionary", "profile"):
        if key not in data:
            raise ArucoConfigError(f"{source}: missing key: {key}")
    profiles = data["profiles"]
    if not isinstance(profiles, dict) or not profiles:
        raise ArucoConfigError(f"{source}: profiles: must be a non-empty mapping")
    parsed = {}
    for name, entry in profiles.items():  # validate every profile, not only the active one
        where = f"{source}: profiles.{name}."
        if not isinstance(entry, dict):
            raise ArucoConfigError(f"{where[:-1]}: must be a mapping")
        missing = [k for k in PROFILE_KEYS if k not in entry]
        if missing:
            raise ArucoConfigError(f"{where}{missing[0]}: missing")
        extra = set(entry) - set(PROFILE_KEYS)
        if extra:
            raise ArucoConfigError(f"{where[:-1]}: unknown key(s): {', '.join(sorted(extra))}")
        length, marker, offset = _common(entry, where, source, data["dictionary"])
        if entry["missing_offset"] not in MISSING_OFFSET:
            raise ArucoConfigError(f"{where}missing_offset: must be one of {MISSING_OFFSET}")
        session = entry["session"]
        if session is not None and (not isinstance(session, dict) or set(session) - set(SESSION_KEYS)):
            raise ArucoConfigError(f"{where}session: must be null or a mapping with {', '.join(SESSION_KEYS)}")
        if session is not None:
            from datetime import datetime
            try:
                stamp = datetime.fromisoformat(session['measured_at'].replace('Z','+00:00'))
                resolution = session['camera_resolution']
                valid_session = (stamp.utcoffset() is not None
                    and isinstance(resolution,list) and len(resolution)==2
                    and all(type(v) is int and v>0 for v in resolution)
                    and all(isinstance(session.get(k),str) and session[k].strip()
                            for k in ('image_session','method')))
            except (KeyError,TypeError,ValueError,AttributeError):
                valid_session = False
            if not valid_session:
                raise ArucoConfigError(f"{where}session: measured_at, camera_resolution, image_session and method are required")
        parsed[name] = ArucoSettings(data["dictionary"], length, marker, offset, None, source, name,
                                     session, entry["missing_offset"])
    name = requested or data["profile"]
    if name not in parsed:
        raise ArucoConfigError(f"{source}: profile: {name!r} is not one of {', '.join(parsed)}")
    return parsed[name]


def load_aruco_settings(path, profile=None) -> ArucoSettings:
    """Active profile (or `profile`) of configs/aruco.yaml."""
    import yaml

    path = Path(path)
    if not path.is_file():
        raise ArucoConfigError(f"{path}: ArUco config file not found")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ArucoConfigError(f"{path}: invalid YAML: {exc}") from None
    return settings_from_mapping(data, str(path), profile)


def require_measured_offset(settings: ArucoSettings, logger=None) -> ArucoSettings:
    """Runtime gate for an unmeasured heading offset (null).

    missing_offset=reject -> ArucoConfigError (start refused).
    missing_offset=warn   -> loud warning; heading is then reported with an explicit 0 offset.
    """
    if settings.heading_offset_deg is not None:
        return settings
    where = f"{settings.source}: profiles.{settings.profile}.heading_offset_deg"
    label = "실제 보트" if settings.profile == "boat" else f"{settings.profile} 프로파일"
    message = (f"{where}: {label} 헤딩 오프셋이 측정되지 않음(null). "
               "scripts/aruco/capture_heading_refs.py 촬영 후 calibrate_heading_from_images.py --write 로 측정")
    if settings.missing_offset == "reject":
        raise ArucoConfigError(message + " (missing_offset=reject: 시작 거부)")
    (logger or logging.getLogger(__name__)).warning(
        "%s (missing_offset=warn: 오프셋 0으로 계산 중, 헤딩을 신뢰하지 말 것)", message)
    return replace(settings, heading_offset_deg=0.0)


def legacy_settings(config: dict) -> ArucoSettings:
    """In-memory dict form used by tests/simulation: marker_id, forward_offset_deg, ..."""
    marker = config.get("marker_id")
    dictionary = config.get("dictionary", "DICT_4X4_50")
    size = len(_dictionary(dictionary, "aruco").bytesList)
    if not isinstance(marker, int) or isinstance(marker, bool) or not 0 <= marker < size:
        raise ValueError("configure a valid board marker_id")
    offset = float(config.get("forward_offset_deg", 0))
    length = float(config.get("marker_size_m", 0.10))
    if not all(math.isfinite(v) for v in (offset, length)) or length <= 0:
        raise ValueError("invalid marker settings")
    return ArucoSettings(dictionary, length, marker, offset, None, "<dict>")


def pixel_heading(corners) -> float:
    """Raw (no offset) bow heading in the pixel frame, [0, 360). corners: 4x2, ArUco order."""
    p = np.asarray(corners, dtype=float).reshape(4, 2)
    center, bow = p.mean(axis=0), (p[0] + p[1]) / 2
    dx, dy = bow - center
    return math.degrees(math.atan2(-dy, dx)) % 360  # image rows grow downward: flip y


class MarkerDetector:
    """Find the board marker; returns its 4 corners in ORIGINAL image pixels."""

    def __init__(self, settings: ArucoSettings, detect_max_width: int = 0):
        aruco = getattr(cv2, "aruco", None)
        if aruco is None:
            raise RuntimeError("This OpenCV build has no ArUco; install opencv-contrib-python")
        if type(detect_max_width) is not int or detect_max_width < 0:
            raise ValueError("detect_max_width must be a nonnegative integer")
        if not hasattr(aruco, "ArucoDetector"):
            # The pre-4.7 aruco.detectMarkers API is intentionally unsupported.
            raise RuntimeError(f"OpenCV >= 4.7 (cv2.aruco.ArucoDetector) required, found {cv2.__version__}")
        self.settings, self.detect_max_width = settings, detect_max_width
        dictionary = _dictionary(settings.dictionary, settings.source)
        self.detect = aruco.ArucoDetector(dictionary, aruco.DetectorParameters()).detectMarkers

    def find(self, image):
        """(corners 4x2 float | None, count of board-ID markers seen)."""
        scale_x = scale_y = 1
        small = image
        if self.detect_max_width and image.shape[1] > self.detect_max_width:
            width = self.detect_max_width
            height = max(1, round(image.shape[0] * width / image.shape[1]))
            small = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
            scale_x, scale_y = image.shape[1] / width, image.shape[0] / height
        corners, ids, _ = self.detect(small)
        selected = [] if ids is None else [
            corners[i] for i, value in enumerate(ids.ravel()) if int(value) == self.settings.board_marker_id]
        if len(selected) != 1:
            return None, len(selected)
        points = np.asarray(selected[0], dtype=float).reshape(4, 2).copy()
        points *= [scale_x, scale_y]
        return points, 1
