"""One capture worker per process; viewers share the latest JPEG (no frame queue)."""
import asyncio
import logging
import threading
import time

from . import config

logger = logging.getLogger(__name__)


class CameraUnavailable(RuntimeError):
    pass


class Camera:
    def __init__(self):
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._jpeg = None
        self._sequence = 0
        self._updated = 0.0
        self._error = None

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._jpeg = None
            self._error = None
            self._thread = threading.Thread(target=self._capture, daemon=True)
            self._thread.start()

    def _capture(self):
        capture = None
        try:
            import cv2

            source = config.CAMERA_SOURCE
            capture = cv2.VideoCapture(int(source) if source.isdecimal() else source)
            if not capture.isOpened():
                raise CameraUnavailable('웹캠을 열 수 없습니다. 장치 연결과 카메라 권한을 확인하세요.')
            capture.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAMERA_WIDTH)
            capture.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAMERA_HEIGHT)
            capture.set(cv2.CAP_PROP_FPS, config.CAMERA_FPS)
            while not self._stop.is_set():
                started = time.monotonic()
                ok, frame = capture.read()
                if not ok:
                    raise CameraUnavailable('웹캠 영상 수신이 끊겼습니다. 다시 연결하세요.')
                ok, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, config.CAMERA_JPEG_QUALITY])
                if not ok:
                    raise CameraUnavailable('카메라 프레임을 JPEG로 변환하지 못했습니다.')
                with self._lock:
                    self._jpeg = jpeg.tobytes()
                    self._sequence += 1
                    self._updated = time.monotonic()
                self._stop.wait(max(0, 1 / config.CAMERA_FPS - (time.monotonic() - started)))
        except ImportError:
            with self._lock:
                self._error = '영상 모듈이 없습니다. backend/requirements.txt를 설치하세요.'
        except Exception as exc:
            logger.exception('Camera capture stopped')
            with self._lock:
                self._error = str(exc) if isinstance(exc, CameraUnavailable) else '웹캠 처리 중 오류가 발생했습니다.'
        finally:
            if capture is not None:
                capture.release()

    async def next_frame(self, after=-1):
        deadline = time.monotonic() + config.CAMERA_TIMEOUT
        while time.monotonic() < deadline:
            with self._lock:
                if self._error:
                    raise CameraUnavailable(self._error)
                if self._stop.is_set():
                    raise CameraUnavailable('카메라 서버가 종료되었습니다.')
                if self._jpeg is not None and self._sequence != after and time.monotonic() - self._updated < config.CAMERA_TIMEOUT:
                    return self._sequence, self._jpeg
            await asyncio.sleep(0.02)
        raise CameraUnavailable('카메라 응답 시간이 초과되었습니다. 장치 연결을 확인하세요.')

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)


def mjpeg_part(jpeg):
    return (b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: '
            + str(len(jpeg)).encode('ascii') + b'\r\n\r\n' + jpeg + b'\r\n')


camera = Camera()
