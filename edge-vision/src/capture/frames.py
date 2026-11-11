"""Single-owner capture and immutable, bounded latest-frame fan-out."""

from dataclasses import dataclass
from threading import Condition, Event, Thread
import logging
import time

import numpy as np

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Frame:
    frame_id: int
    captured_at: float
    monotonic: float
    image: np.ndarray


class LatestFrames:
    def __init__(self):
        self.condition = Condition()
        self.latest = None
        self.closed = False

    def publish(self, image, captured_at=None, monotonic=None):
        with self.condition:
            if self.closed:
                return
            owned = image.copy()
            owned.flags.writeable = False
            self.latest = Frame(
                1 if self.latest is None else self.latest.frame_id + 1,
                time.time() if captured_at is None else captured_at,
                time.monotonic() if monotonic is None else monotonic,
                owned,
            )
            self.condition.notify_all()

    def get(self, after=-1, timeout=0.2):
        with self.condition:
            self.condition.wait_for(
                lambda: self.closed or (self.latest is not None and self.latest.frame_id > after),
                timeout,
            )
            if self.latest is not None and self.latest.frame_id > after:
                return self.latest
            return None

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()


class CaptureWorker:
    def __init__(self, source, frames, *, video_fps=None):
        self.source, self.frames, self.video_fps = source, frames, video_fps
        self.stop = Event()
        self.thread = Thread(target=self._run, name="camera-capture", daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        failures = 0
        try:
            while not self.stop.is_set():
                started = time.monotonic()
                ok, image = self.source.read()
                if not ok:
                    failures += 1
                    if self.video_fps or failures >= 10:
                        break
                    self.stop.wait(0.02)
                    continue
                failures = 0
                self.frames.publish(image)
                if self.video_fps:
                    self.stop.wait(max(0, 1 / self.video_fps - (time.monotonic() - started)))
        except Exception:
            LOGGER.exception("capture failed")
        finally:
            self.source.release()
            self.frames.close()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
        if self.thread.is_alive():
            self.source.release()
            self.thread.join(timeout=1)
        if self.thread.is_alive():
            LOGGER.error("capture driver did not stop within shutdown deadline")
