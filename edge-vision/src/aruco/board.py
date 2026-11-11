"""FR-DET-004 구조보드 위치 동시 검출 (ArUco).

Board marker corners -> water-plane metres (FR-SUR-004) and heading; no 3D camera-pose claim.
``PoseWorker`` runs at its own rate on the shared latest frame, independent of the VLM.
"""

import math
from threading import Lock, Thread, Event
import time
import logging

import cv2
import numpy as np


HEADING_MODES = ("pixel", "world")


class BoardLocator:
    """The ONE place that combines ArUco settings with the homography.

    aruco: ArucoSettings (configs/aruco.yaml) or the legacy in-memory dict
           {marker_id, forward_offset_deg, ...} used by tests/simulation.
    use_homography=False: pixel position and pixel heading only; x/y (metres) stay null and
           the pose is not a valid world pose (status "pixel_only").
    heading_mode="world" (default, unchanged behaviour): every marker corner is projected
           to the water plane, then the bow vector (corner-centroid -> top-edge midpoint) is
           taken between those projected end points. "pixel": heading from image pixels.
    heading_offset_deg is added exactly once, here, in either mode.
    """

    def __init__(self, calibration, aruco, *, use_homography=True, heading_mode="world",
                 max_frame_age_seconds=None, tracking_timeout_seconds=None, detect_max_width=None,
                 allow_unmeasured_offset=False):
        """allow_unmeasured_offset=True: measuring tools only (raw heading, explicit 0 offset).
        Otherwise a null heading_offset_deg follows the profile's missing_offset policy."""
        from dataclasses import replace

        from src.aruco.marker import (ArucoSettings, MarkerDetector, legacy_settings,
                                              require_measured_offset)

        if not hasattr(cv2, "aruco"):
            raise RuntimeError("This OpenCV build has no ArUco; install opencv-contrib-python")
        legacy = aruco if isinstance(aruco, dict) else {}
        settings = aruco if isinstance(aruco, ArucoSettings) else legacy_settings(aruco)
        self.offset_measured = settings.offset_measured
        if settings.heading_offset_deg is None:
            settings = (replace(settings, heading_offset_deg=0.0) if allow_unmeasured_offset
                        else require_measured_offset(settings))
        if heading_mode not in HEADING_MODES:
            raise ValueError(f"heading_mode must be one of {HEADING_MODES}, got {heading_mode!r}")
        if not isinstance(use_homography, bool):
            raise ValueError("use_homography must be true or false")
        if heading_mode == "world" and not use_homography:
            raise ValueError("heading_mode=world needs use_homography=true")
        self.calibration, self.settings = calibration, settings
        self.use_homography, self.heading_mode = use_homography, heading_mode
        self.marker_id = settings.board_marker_id
        self.offset = settings.heading_offset_deg
        pick = lambda value, key, default: value if value is not None else legacy.get(key, default)
        self.lost_seconds = float(pick(tracking_timeout_seconds, "tracking_timeout_seconds", 0.5))
        self.max_age = float(pick(max_frame_age_seconds, "max_frame_age_seconds", 0.2))
        self.detect_max_width = pick(detect_max_width, "detect_max_width", 0)
        if not all(math.isfinite(v) for v in (self.lost_seconds, self.max_age)) or min(
                self.max_age, self.lost_seconds) <= 0:
            raise ValueError("invalid marker settings")
        self.detector = MarkerDetector(settings, self.detect_max_width)
        self.last_seen = None

    @property
    def detect(self):
        """Raw cv2 detectMarkers (display overlays; replaceable in tests)."""
        return self.detector.detect

    @detect.setter
    def detect(self, function):
        self.detector.detect = function

    def measure(self, frame, now=None, calibration=None):
        """Full measurement: pixel and (if available) world heading, both raw and offset.

        Keys: status, corners_px, center_px, pixel_heading_raw, world_heading_raw,
        x, y, heading (selected mode + offset, or None).
        calibration: the frame's snapshot; default = the current one.
        """
        from src.aruco.marker import pixel_heading
        from src.homography.coordinates import calibration_view

        if calibration is None and self.use_homography:
            calibration = calibration_view(self.calibration)[0]

        now = time.monotonic() if now is None else now
        result = dict(status=None, corners_px=None, center_px=None, pixel_heading_raw=None,
                      world_heading_raw=None, x=None, y=None, heading=None)
        if not 0 <= now - frame.monotonic <= self.max_age:
            return {**result, "status": "stale_frame"}
        points, _count = self.detector.find(frame.image)
        if points is None:
            lost = self.last_seen is None or now - self.last_seen >= self.lost_seconds
            return {**result, "status": "tracking_lost" if lost else "not_detected"}
        result.update(corners_px=points, center_px=points.mean(axis=0),
                      pixel_heading_raw=pixel_heading(points))
        if self.use_homography:
            if calibration is None:
                return {**result, "status": "invalid_calibration_or_roi"}
            size = (frame.image.shape[1], frame.image.shape[0])
            # Transform all corners before averaging: image-space angles are not world headings.
            world = [calibration.point(p, size)[0] for p in points]
            if any(p is None for p in world):
                return {**result, "status": "invalid_calibration_or_roi"}
            xy = np.array([[p["x"], p["y"]] for p in world])
            center = xy.mean(axis=0)
            forward = (xy[0] + xy[1]) / 2 - center  # marker's top edge is its nominal front
            if np.linalg.norm(forward) < 1e-8:
                return {**result, "status": "degenerate_marker"}
            # Heading convention (agreed 2026-11-04, docs/WEB_INTERFACE.md): water-plane frame with
            # origin = pool lower-left corner, +X = pool right, +Y = pool up (far side in top view).
            # 0 deg = +X, increasing counter-clockwise (90 deg = +Y), range [0, 360).
            result.update(x=float(center[0]), y=float(center[1]),
                          world_heading_raw=math.degrees(math.atan2(forward[1], forward[0])) % 360)
        raw = result["world_heading_raw"] if self.heading_mode == "world" else result["pixel_heading_raw"]
        # heading_offset_deg (configs/aruco.yaml) corrects a marker whose top edge is not
        # exactly toward the bow. Applied here once; nothing downstream adds it again.
        result["heading"] = (raw + self.offset) % 360
        self.last_seen = now
        result["status"] = "tracked" if self.use_homography else "pixel_only"
        return result

    def locate(self, frame, now=None):
        from src.homography.coordinates import calibration_view

        # One snapshot for the whole frame: a hot reload can never mix two matrices here.
        calibration, editing, matrix_hash = calibration_view(self.calibration)
        m = (dict(status="calibration_editing", center_px=None) if editing
             else self.measure(frame, now, calibration=calibration))
        base = {
            "x": None,
            "y": None,
            "heading": None,
            "timestamp": frame.captured_at,
            "frame_id": frame.frame_id,
            "coordinate_frame": calibration.config.get("frame_id") if calibration else None,
            "unit": calibration.config.get("unit", "m") if calibration else "m",
            "heading_unit": "degree",
            "zero_axis_deg": 0,
            "clockwise": False,
            "marker_id": self.marker_id,
            "tracking_valid": False,
            "pixel_coordinates": None,
            "status": m["status"],
        }
        if hasattr(self.calibration, "snapshot"):  # hot-reload runtime only
            base.update(homography_hash=matrix_hash, calibration_editing=editing)
        if m["center_px"] is not None:
            base["pixel_coordinates"] = {"x": float(m["center_px"][0]), "y": float(m["center_px"][1]),
                                         "unit": "pixel"}
        if m["status"] != "tracked":
            # pixel_only (no homography) is not a world pose: coordinates and heading stay null.
            # Legacy payloads carried no pixel position for invalid poses.
            if m["status"] != "pixel_only":
                base["pixel_coordinates"] = None
            return base
        if not self.offset_measured:
            return {**base, "status": "unmeasured_heading"}
        return {**base, "x": m["x"], "y": m["y"], "heading": m["heading"], "tracking_valid": True}


class PoseWorker:
    def __init__(self, frames, locator, sender, hz=15):
        if not 10 <= hz <= 100:
            raise ValueError("pose target_hz must be between 10 and 100")
        self.frames, self.locator, self.sender, self.hz = frames, locator, sender, hz
        self.stop = Event()
        self.lock = Lock()
        self.latest = None
        self.processed = 0
        self.processing_seconds = 0
        self.error = None
        self.thread = Thread(target=self._run, name="aruco-pose", daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        try:
            self._process_frames()
        except Exception as exc:
            self.error = type(exc).__name__
            logging.getLogger(__name__).exception("ArUco pose worker failed")

    def _process_frames(self):
        last = -1
        while not self.stop.is_set():
            started = time.monotonic()
            frame = self.frames.get(last, timeout=1 / self.hz)
            if frame is None:
                if self.latest is not None and self.latest.get("tracking_valid"):
                    loss = {
                        **self.latest,
                        "x": None,
                        "y": None,
                        "heading": None,
                        "tracking_valid": False,
                        "status": "tracking_lost",
                        "timestamp": time.time(),
                    }
                    with self.lock:
                        self.latest = loss
                    self.sender.submit(loss, time.monotonic())
                if self.frames.closed:
                    break
                continue
            last = frame.frame_id
            try:
                pose = self.locator.locate(frame)
            except cv2.error:
                pose = {
                    "timestamp": frame.captured_at,
                    "marker_id": self.locator.marker_id,
                    "x": None,
                    "y": None,
                    "heading": None,
                    "tracking_valid": False,
                    "status": "detector_error",
                }
            with self.lock:
                self.latest = pose
            self.sender.submit(pose, frame.monotonic)
            self.processed += 1
            self.processing_seconds += time.monotonic() - started
            self.stop.wait(max(0, 1 / self.hz - (time.monotonic() - started)))

    def telemetry(self):
        with self.lock:
            pose = self.latest
            if not pose or not pose["tracking_valid"]:
                return None
            return dict(
                x=pose["x"],
                y=pose["y"],
                current_heading=pose["heading"],
                unit=pose.get("unit", "m"),
                frame_id=pose["coordinate_frame"],
                position_timestamp=pose["timestamp"],
                heading_timestamp=pose["timestamp"],
                zero_axis_deg=0,
                clockwise=False,
            )

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            logging.getLogger(__name__).error("pose worker did not stop within shutdown deadline")


POSE_OPTION_KEYS = ("use_homography", "heading_mode", "max_frame_age_seconds",
                    "tracking_timeout_seconds", "detect_max_width")


class PoseConfigError(ValueError):
    pass


def load_pose_inputs(config_path, config, *, require_calibrated=False, profile=None):
    """Read the two INDEPENDENT configs named by a vision config and its pose options.

    vision config keys:  homography_config (calibration/homography.yaml),
                         aruco_config (configs/aruco.yaml), pose: {POSE_OPTION_KEYS}
    Returns (calibration, aruco_settings, pose_options). Errors name the file and key.
    """
    from pathlib import Path

    from src.aruco.marker import load_aruco_settings
    from src.common.files import aruco_path, homography_path
    from src.homography.loader import load_homography

    where = str(config_path)
    if "aruco" in config:
        raise PoseConfigError(f"{where}: aruco: section moved to a separate file; "
                              "set aruco_config: aruco.yaml (see configs/aruco.yaml)")
    for key in ("homography_config", "aruco_config", "pose"):
        if key not in config:
            raise PoseConfigError(f"{where}: {key}: missing")
    options = config["pose"]
    if not isinstance(options, dict):
        raise PoseConfigError(f"{where}: pose: must be a mapping")
    unknown = set(options) - set(POSE_OPTION_KEYS)
    if unknown:
        raise PoseConfigError(f"{where}: pose: unknown key(s): {', '.join(sorted(unknown))}")
    for key in ("use_homography", "heading_mode"):
        if key not in options:
            raise PoseConfigError(f"{where}: pose.{key}: missing")
    if not isinstance(options["use_homography"], bool):
        raise PoseConfigError(f"{where}: pose.use_homography: must be true or false")
    if options["heading_mode"] not in HEADING_MODES:
        raise PoseConfigError(f"{where}: pose.heading_mode: must be one of {HEADING_MODES}")
    if options["heading_mode"] == "world" and not options["use_homography"]:
        raise PoseConfigError(f"{where}: pose.heading_mode=world requires pose.use_homography=true")
    base = Path(config_path).resolve().parent
    calibration = load_homography(homography_path(base, config), require_calibrated=require_calibrated)
    aruco = load_aruco_settings(aruco_path(base, config), profile)
    return calibration, aruco, dict(options)
