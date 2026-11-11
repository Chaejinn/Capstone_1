"""Browser-owned camera ingestion; reuse Modal, tracking, homography and ArUco.

Run behind an authenticated web proxy. This process never opens VideoCapture.
All frames/results live in bounded memory, not image files or browser storage.
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import secrets
from threading import Event, Lock, Thread
import time
from uuid import uuid4

import cv2
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
import yaml

from src.drowning_gate import DrowningGate
from src.flow.settings import PipelineSettings
from src.flow.detection.tracking import PersonTracker
from src.modal_api import _decode_image, MAX_IMAGE_BYTES
from src.flow.detection.board import BoardLocator
from src.rescue.frames import Frame
from src.flow.sensing.coordinates import Calibration
from src.flow.judgement.accumulation import StateStabilizer, StabilizationSettings
from src.rescue.web import iso

LOGGER = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[1]


class ModalGateway:
    def __init__(self, url, key, timeout=30):
        from src.deployment import origin

        self.url, self.key, self.timeout = origin(url), key, timeout
        if not key:
            raise ValueError("Modal API key is required on the service, never in the browser")

    def predict(self, frame):
        from client_example import _multipart_body, _request_json

        ok, encoded = cv2.imencode(".jpg", frame.image)
        if not ok:
            raise ValueError("could not encode browser frame")
        content_type, body = _multipart_body(encoded.tobytes(), str(frame.frame_id))
        return _request_json(
            self.url + "/detect", self.key, "POST", body, content_type, timeout=self.timeout
        )


class BrowserStream:
    def __init__(
        self,
        owner,
        site_id,
        camera_id,
        predictor,
        calibration,
        locator,
        *,
        tracker_factory=None,
        stabilization=None,
        max_tracking_gap=15,
        max_frame_age=2,
        pose_max_age=0.25,
        analysis_max_age=30,
        clock_tolerance_seconds=0.5,
    ):
        self.owner, self.site_id, self.camera_id = owner, site_id, camera_id
        self.predictor, self.calibration, self.locator = predictor, calibration, locator
        self.tracker_factory = tracker_factory
        self.tracker = tracker_factory() if tracker_factory else None
        self.stabilization = stabilization or {}
        self.stabilizer = StateStabilizer(StabilizationSettings(**self.stabilization))
        self.max_tracking_gap, self.max_frame_age = max_tracking_gap, max_frame_age
        self.strict_gate = DrowningGate(max_gap_seconds=max_tracking_gap)
        self.pose_max_age, self.analysis_max_age = pose_max_age, analysis_max_age
        if not 0 <= clock_tolerance_seconds <= 1:
            raise ValueError("clock tolerance must be bounded to at most one second")
        self.clock_tolerance = clock_tolerance_seconds
        self.clock_warning = None
        self.lock = Lock()
        self.wake, self.stop = Event(), Event()
        self.latest = self.analysis = self.pose = None
        self.inference_frame_id = None
        self.last_analyzed_time = None
        self.last_seen = time.monotonic()
        self.track_generation = 0
        self.last_error = None
        self.last_error_code = None
        self.submitted = self.analyzed = 0
        self.thread = Thread(target=self._run, name="browser-modal-analysis", daemon=True)
        self.thread.start()

    def submit(self, image, frame_id, captured_at):
        now, monotonic = time.time(), time.monotonic()
        if not -self.clock_tolerance <= now - captured_at <= self.max_frame_age:
            LOGGER.warning(json.dumps({"event":"browser_frame_rejected", "frame_id":frame_id,
                "reason_code":"FRAME_TOO_OLD" if now >= captured_at else "CLIENT_CLOCK_AHEAD",
                "observed_age_seconds":round(now-captured_at,3), "limit_seconds":self.max_frame_age}))
            raise ValueError(
                f"stale/future browser frame; observed_age_seconds={now-captured_at:.3f}; limit={self.max_frame_age}; synchronize clocks"
            )
        owned = image.copy()
        owned.flags.writeable = False
        frame = Frame(frame_id, captured_at, monotonic - (now - captured_at), owned)
        with self.lock:
            if self.stop.is_set():
                raise ValueError("stream is closed")
            if self.latest and frame_id <= self.latest.frame_id:
                raise ValueError("frame_id must strictly increase within a stream")
            # ArUco is independent of the slow Modal request thread.
            self.pose = self.locator.locate(frame, now=monotonic)
            self.clock_warning = "client_clock_ahead" if captured_at > now else None
            if self.clock_warning:
                # Informational inference can tolerate bounded RTC skew, but a
                # future/uncertain pose must never become a valid measurement.
                self.pose.update(
                    x=None,
                    y=None,
                    heading=None,
                    tracking_valid=False,
                    status="clock_unsynchronized",
                )
            self.latest = frame
            self.last_seen = monotonic
            self.submitted += 1
            self.wake.set()
            return self._snapshot(now)

    def _decorate(self, frame, result, inferred_at):
        if str(result.get("frame_id")) != str(frame.frame_id):
            raise ValueError("Modal result belongs to another frame")
        size = [frame.image.shape[1], frame.image.shape[0]]
        if result.get("image_size") != size:
            raise ValueError("Modal resolution does not match the submitted browser frame")
        raw = result.get("detections")
        if not isinstance(raw, list):
            raise ValueError("invalid Modal detection list")
        detections = []
        for detection in raw:
            box = detection.get("bbox")
            if (
                not isinstance(box, (list, tuple))
                or len(box) != 4
                or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in box)
                or not (0 <= box[0] < box[2] <= size[0] and 0 <= box[1] < box[3] <= size[1])
            ):
                raise ValueError("invalid original-image bbox")
            if detection.get("water_state") not in ("SWIMMING", "DROWNING", "UNCLEAR"):
                raise ValueError("invalid raw VLM state")
            score = detection.get("confidence")
            if (
                not isinstance(score, (int, float))
                or not math.isfinite(score)
                or not 0 <= score <= 1
            ):
                raise ValueError(
                    "invalid detection score; never replace with a drowning probability"
                )
            if detection.get("class", detection.get("class_name")) != "human_dummy":
                continue
            detections.append({**detection, "class": "human_dummy"})
        if self.tracker is not None:
            if (
                self.last_analyzed_time is not None
                and frame.monotonic - self.last_analyzed_time > self.max_tracking_gap
            ):
                # Never merge people across a long unobserved interval.
                self.tracker = self.tracker_factory()
                self.stabilizer = StateStabilizer(StabilizationSettings(**self.stabilization))
                self.strict_gate = DrowningGate(max_gap_seconds=self.max_tracking_gap)
                self.track_generation += 1
            tracked = self.tracker.update(detections)
        else:
            tracked = [{**d, "track_id": None} for d in detections]
        self.last_analyzed_time = frame.monotonic
        self.strict_gate.retain({d.get("track_id") for d in tracked})
        decorated = []
        for detection in tracked:
            track = detection.get("track_id")
            decision = self.stabilizer.observe(
                track, detection["water_state"], frame.frame_id, frame.monotonic
            )
            if decision is None:
                continue
            pixel, world, reason = self.calibration.bbox(detection["bbox"], size)
            raw_state = detection["water_state"]
            strict = self.strict_gate.observe(track, frame.frame_id, frame.monotonic,
                                              raw_state, detection.get("drowning_score"), decided_at=inferred_at)
            if strict is None:
                continue
            confirmed = strict["confirmed"]
            demo = result.get("demo_mode") if isinstance(result.get("demo_mode"), bool) else None
            decorated.append(
                {
                    **detection,
                    "class_name": "human_dummy",
                    "track_id": track,
                    "track_generation": self.track_generation,
                    "raw_state": raw_state,
                    "stable_state": strict["decision"],
                    "consecutive_frames": strict["consecutive_frames"],
                    "required_frames": strict["required_frames"],
                    "score_threshold": strict["score_threshold"],
                    "confirmed": confirmed,
                    "event_id": str(uuid4()) if strict["new_confirmation"] else None,
                    "assessment": "DROWNING" if confirmed else ("NORMAL" if raw_state == "SWIMMING" else "ABNORMAL"),
                    "classification_confidence": detection.get("drowning_score"),
                    "confidence_source": (
                        None if detection.get("drowning_score") is None else "moondream2_label_softmax_uncalibrated"
                    ),
                    "detection_confidence": detection.get("confidence"),
                    "pixel_coordinates": pixel,
                    "target_x_m": None if world is None else world["x"],
                    "target_y_m": None if world is None else world["y"],
                    "coordinate_valid": world is not None,
                    "coordinate_status": reason,
                    "coordinate_frame": self.calibration.config.get("frame_id"),
                    "dispatch_eligible": False,
                    "dispatch_status": ("BLOCKED_NO_CALIBRATION" if world is None else "BLOCKED_NO_BRIDGE") if confirmed else "AWAITING_CONFIRMATION",
                    "confirmed_at": iso(strict["confirmed_at"]) if confirmed else None,
                    "dispatch_deadline_at": iso(strict["confirmed_at"] + 3) if confirmed else None,
                    "command_issued": False,
                    "captured_at": iso(frame.captured_at),
                    "inferred_at": iso(inferred_at),
                }
            )
        marker = self.locator.inspect(frame.image) if hasattr(self.locator, "inspect") else None
        if marker is not None:
            marker.update(frame_id=frame.frame_id, captured_at=iso(frame.captured_at))
        return {
            **result,
            "marker_observation": marker,
            "configuration_revision": getattr(self.locator, "revision", None),
            "camera_id": self.camera_id,
            "frame_id": frame.frame_id,
            "captured_at": iso(frame.captured_at),
            "inferred_at": iso(inferred_at),
            "image_width": size[0],
            "image_height": size[1],
            "image_size": size,
            "detections": decorated,
            "camera_owner": "browser",
            "tracking_method": "ByteTrack on inference frames" if self.tracker else "none",
            "control_commands_generated": False,
        }

    def _run(self):
        last = -1
        while not self.stop.is_set():
            self.wake.wait(0.1)
            self.wake.clear()
            if self.stop.is_set():
                break
            with self.lock:
                frame = self.latest
                if frame is None or frame.frame_id <= last:
                    continue
                last = frame.frame_id
                self.inference_frame_id = last
            request_id = str(uuid4())
            started = time.perf_counter()
            try:
                if time.time() - frame.captured_at > self.max_frame_age:
                    self.strict_gate = DrowningGate(max_gap_seconds=self.max_tracking_gap)
                    continue
                result = self.predictor.predict(frame)
                inferred_at = time.time()
                if self.stop.is_set():
                    break
                if inferred_at - frame.captured_at > self.analysis_max_age:
                    raise ValueError("inference result expired")
                decorated = self._decorate(frame, result, inferred_at)
                decorated["request_id"] = request_id
                LOGGER.info(json.dumps({
                    "event": "browser_inference_completed",
                    "request_id": request_id,
                    "frame_id": frame.frame_id,
                    "detection_count": len(decorated["detections"]),
                    "raw_states": sorted({d["raw_state"] for d in decorated["detections"]}),
                    "processing_ms": round((time.perf_counter() - started) * 1000, 3),
                }))
                with self.lock:
                    if not self.stop.is_set():
                        self.analysis = decorated
                        self.last_error = None
                        self.last_error_code = None
                        self.analyzed += 1
            except Exception as exc:
                self.strict_gate = DrowningGate(max_gap_seconds=self.max_tracking_gap)
                # Do not expose keys, request headers, or arbitrary remote error bodies.
                reason_code = {
                    "inference result expired":"MODEL_RESULT_EXPIRED",
                    "Modal result belongs to another frame":"FRAME_MISMATCH",
                    "Modal resolution does not match the submitted browser frame":"IMAGE_SIZE_MISMATCH",
                    "invalid original-image bbox":"INVALID_BBOX",
                    "invalid raw VLM state":"INVALID_CLASSIFICATION",
                }.get(str(exc), "INFERENCE_ERROR")
                with self.lock:
                    self.last_error = type(exc).__name__
                    self.last_error_code = reason_code
                LOGGER.warning(json.dumps({
                    "event": "browser_inference_failed",
                    "request_id": request_id,
                    "frame_id": frame.frame_id,
                    "error_type": type(exc).__name__,
                    "reason_code": reason_code,
                    "processing_ms": round((time.perf_counter() - started) * 1000, 3),
                }))

    def _snapshot(self, now):
        pose = (
            dict(self.pose)
            if self.pose
            else {
                "x": None,
                "y": None,
                "heading": None,
                "tracking_valid": False,
                "status": "no_frame",
                "timestamp": now,
            }
        )
        if pose.get("tracking_valid") and now - pose["timestamp"] > self.pose_max_age:
            pose.update(x=None, y=None, heading=None, tracking_valid=False, status="stale_frame")
        pose["timestamp"] = iso(pose["timestamp"])
        analysis = self.analysis
        if analysis is not None:
            age = (
                now
                - datetime.fromisoformat(analysis["captured_at"].replace("Z", "+00:00")).timestamp()
            )
            analysis = {**analysis, "age_seconds": age, "expired": age > self.analysis_max_age}
        return {
            "site_id": self.site_id,
            "camera_id": self.camera_id,
            "latest_frame_id": self.latest.frame_id if self.latest else None,
            "inference_frame_id": self.inference_frame_id,
            "analysis": analysis,
            "pose": pose,
            "frames_received": self.submitted,
            "frames_analyzed": self.analyzed,
            "last_error": self.last_error,
            "last_error_code": self.last_error_code,
            "clock_warning": self.clock_warning,
            "control_commands_generated": False,
        }

    def snapshot(self):
        with self.lock:
            self.last_seen = time.monotonic()
            return self._snapshot(time.time())

    def close(self):
        self.stop.set()
        self.wake.set()
        self.thread.join(timeout=1)
        with self.lock:
            self.latest = self.analysis = self.pose = None


class OpenStream(BaseModel):
    configuration: dict | None = None
    camera_id: str = Field(min_length=1, max_length=80)


def create_browser_app(
    predictor,
    calibration,
    aruco_config,
    *,
    api_key,
    camera_id="camera-01",
    tracker_factory=None,
    stabilization=None,
    max_streams=4,
    idle_seconds=120,
    site_id=None,
    configuration_factory=None,
):
    if not api_key or len(api_key) < 32:
        raise ValueError("VISION_INGEST_API_KEY must contain at least 32 characters")
    if calibration.matrix is not None and not site_id:
        raise ValueError("A measured calibration must be bound to an explicit site_id")
    if (
        not isinstance(max_streams, int)
        or not 1 <= max_streams <= 16
        or not 1 <= idle_seconds <= 3600
    ):
        raise ValueError("invalid browser stream limits")
    streams, streams_lock = {}, Lock()

    async def cleanup_once():
        stale = []
        with streams_lock:
            for key, stream in list(streams.items()):
                if time.monotonic() - stream.last_seen > idle_seconds:
                    stale.append(streams.pop(key))
        for stream in stale:
            await asyncio.to_thread(stream.close)

    @asynccontextmanager
    async def lifespan(app):
        async def janitor():
            while True:
                await asyncio.sleep(min(10, idle_seconds))
                await cleanup_once()

        task = asyncio.create_task(janitor())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            with streams_lock:
                remaining = list(streams.values())
                streams.clear()
            for stream in remaining:
                await asyncio.to_thread(stream.close)

    app = FastAPI(title="Drown Guardian browser frame adapter", lifespan=lifespan)

    def identity(
        authorization: str | None = Header(default=None),
        x_vision_owner: str | None = Header(default=None),
        x_vision_site: str | None = Header(default=None),
    ):
        if not secrets.compare_digest((authorization or "").encode(), f"Bearer {api_key}".encode()):
            raise HTTPException(401, "Service authentication required")
        if (
            not x_vision_owner
            or not x_vision_site
            or max(len(x_vision_owner), len(x_vision_site)) > 128
        ):
            raise HTTPException(400, "Authenticated owner and site scope required")
        if site_id is not None and x_vision_site != site_id:
            raise HTTPException(403, "Site has no matching measured calibration profile")
        return x_vision_owner, x_vision_site

    def get_stream(stream_id, scope):
        with streams_lock:
            stream = streams.get(stream_id)
        if not stream or (stream.owner, stream.site_id) != scope:
            raise HTTPException(404, "Stream not found")
        return stream

    from src.rescue.edge import create_edge_router
    app.include_router(create_edge_router(
        identity, camera_id=camera_id, max_entries=max_streams, idle_seconds=idle_seconds
    ))

    from src.camera_runtime import register_routes
    register_routes(app, identity)

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "camera_owner": "browser",
            "calibration_valid": calibration.matrix is not None,
        }

    @app.post("/v1/streams", status_code=201)
    async def open_stream(body: OpenStream, scope=Depends(identity)):
        if body.camera_id != camera_id:
            raise HTTPException(422, "Camera has no matching calibration profile")
        profile = None
        if configuration_factory is not None:
            try:
                profile = configuration_factory(body.configuration)
            except ValueError:
                raise HTTPException(422, "Invalid camera configuration") from None
        await cleanup_once()
        with streams_lock:
            if len(streams) >= max_streams:
                raise HTTPException(429, "Stream limit reached")
            stream_id = str(uuid4())
            streams[stream_id] = BrowserStream(
                *scope,
                body.camera_id,
                predictor,
                profile[0] if profile else calibration,
                profile[1] if profile else BoardLocator(calibration, aruco_config),
                tracker_factory=tracker_factory,
                stabilization=stabilization,
            )
        return {"stream_id": stream_id, "camera_id": body.camera_id, "camera_owner": "browser",
                "configuration_revision": profile[2] if profile else None}

    @app.post("/v1/streams/{stream_id}/frames")
    async def upload(
        stream_id: str,
        image: UploadFile = File(...),
        frame_id: int = Form(...),
        captured_at: str = Form(...),
        image_width: int = Form(...),
        image_height: int = Form(...),
        scope=Depends(identity),
    ):
        stream = get_stream(stream_id, scope)
        raw = await image.read(MAX_IMAGE_BYTES + 1)
        if len(raw) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "Image exceeds 5 MiB")
        frame = await asyncio.to_thread(_decode_image, raw)
        if frame_id < 1 or [image_width, image_height] != [frame.shape[1], frame.shape[0]]:
            raise HTTPException(422, "Frame ID or image dimensions are invalid")
        try:
            timestamp = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                raise ValueError("UTC timestamp required")
            result = await asyncio.to_thread(stream.submit, frame, frame_id, timestamp.timestamp())
            return {"accepted_frame_id": frame_id, **result}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.get("/v1/streams/{stream_id}/results")
    def results(stream_id: str, scope=Depends(identity)):
        return get_stream(stream_id, scope).snapshot()

    @app.delete("/v1/streams/{stream_id}")
    async def close_stream(stream_id: str, scope=Depends(identity)):
        stream = get_stream(stream_id, scope)
        with streams_lock:
            streams.pop(stream_id, None)
        await asyncio.to_thread(stream.close)
        return {"closed": True}

    return app


def app_from_environment():
    # Emit the allowlisted inference records in service deployments too.
    logging.basicConfig(level=logging.INFO)
    LOGGER.setLevel(logging.INFO)
    load_dotenv(ROOT / ".env")
    config_path = Path(
        os.getenv("BROWSER_VISION_CONFIG", str(ROOT / "configs/browser_vision.yaml"))
    )
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    rescue_path = config_path.parent / config["rescue_config"]
    rescue = yaml.safe_load(rescue_path.read_text(encoding="utf-8"))
    cal = Calibration(rescue["calibration"], rescue_path.parent / rescue["matrix_cache"])
    predictor = ModalGateway(
        os.getenv("MODAL_API_URL", ""),
        os.getenv("DROWN_GUARDIAN_API_KEY", ""),
        config.get("modal_timeout_seconds", 30),
    )
    pipeline = PipelineSettings.from_mapping(
        yaml.safe_load((config_path.parent / config["pipeline_config"]).read_text(encoding="utf-8"))
    )
    tracker_factory = (
        (lambda: PersonTracker(**asdict(pipeline.bytetrack)))
        if config.get("enable_tracking")
        else None
    )
    return create_browser_app(
        predictor,
        cal,
        config["aruco"],
        api_key=os.getenv("VISION_INGEST_API_KEY", ""),
        camera_id=rescue["camera_id"],
        tracker_factory=tracker_factory,
        stabilization=config["stabilization"],
        max_streams=config.get("max_streams", 4),
        idle_seconds=config.get("idle_seconds", 120),
        site_id=os.getenv(config.get("site_id_env", "WEB_SITE_ID")) or None,
    )
