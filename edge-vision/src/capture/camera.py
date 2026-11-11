"""OpenCV 카메라 입력과 자원 수명 관리."""

from __future__ import annotations

import logging
import os
import platform
from typing import Any, Literal

# MSMF with hardware transforms can block for tens of seconds (or indefinitely) when opening
# a webcam; with them off it opened in 0.3 s at 30 fps (Logi C270, 2026-11-05).
os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

import cv2  # noqa: E402

from src.app.config import Config

LOGGER = logging.getLogger(__name__)


class Camera:
    """OpenCV-based camera input manager for Drown Guardian.

    Handles video capture from webcam with frame reading, configuration,
    and safe resource management.

    Attributes:
        camera_index (int): Camera device index
        width (int): Requested frame width
        height (int): Requested frame height
        fps (int): Requested frames per second
        capture (Optional): OpenCV VideoCapture object
    """

    def __init__(
        self,
        camera_index: int | None = None,
        width: int | None = None,
        height: int | None = None,
        fps: int | None = None,
        fourcc: str | None = None,
    ) -> None:
        """Initialize camera with configuration.

        Args:
            camera_index (int): Camera index (default: Config.CAMERA_INDEX)
            width (int): Frame width (default: Config.CAMERA_WIDTH)
            height (int): Frame height (default: Config.CAMERA_HEIGHT)
            fps (int): Frames per second (default: Config.CAMERA_FPS)
        """
        self.camera_index = camera_index if camera_index is not None else Config.CAMERA_INDEX
        self.width = width if width is not None else Config.CAMERA_WIDTH
        self.height = height if height is not None else Config.CAMERA_HEIGHT
        self.fps = fps if fps is not None else Config.CAMERA_FPS
        if fourcc is not None and (len(fourcc) != 4 or not fourcc.isascii()):
            raise ValueError("fourcc must be a four-character ASCII codec")
        self.fourcc = fourcc

        self.capture: Any | None = None
        self._actual_width: int | None = None
        self._actual_height: int | None = None
        self._actual_fps: float | None = None

    def open(self) -> bool:
        """Open camera connection.

        Uses OpenCV VideoCapture with platform-specific optimizations.
        On Windows, attempts multiple backends for stability.

        Returns:
            bool: True if camera opened successfully, False otherwise

        Raises:
            RuntimeError: If camera connection fails after all attempts
        """
        try:
            if platform.system() == "Windows":
                # Try different backends on Windows for stability
                self.capture = self._try_open_windows()
            else:
                # Use default backend on other platforms
                self.capture = cv2.VideoCapture(self.camera_index)

            # Verify camera opened
            if self.capture is None or not self.capture.isOpened():
                raise RuntimeError(f"Failed to open camera at index {self.camera_index}")

            # Configure camera properties
            self.configure()
            return True

        except Exception as exc:
            self.release()
            self.capture = None
            raise RuntimeError(f"Camera open error: {exc}") from exc

    def _try_open_windows(self) -> Any | None:
        """Try opening camera with different Windows backends.

        Attempts multiple backends for stability on Windows.

        Returns:
            VideoCapture object if successful, None otherwise
        """
        # DSHOW first, with format/size/fps passed AT OPEN: set() after opening leaves the
        # C270 on uncompressed YUY2 (USB-limited to ~7.5 fps at 1280x720); MJPG at open gives
        # 30 fps. MSMF (hardware transforms off, see top of file) is the fallback.
        fourcc = cv2.VideoWriter_fourcc(*(self.fourcc or "MJPG"))
        open_params = [cv2.CAP_PROP_FOURCC, fourcc, cv2.CAP_PROP_FRAME_WIDTH, self.width,
                       cv2.CAP_PROP_FRAME_HEIGHT, self.height, cv2.CAP_PROP_FPS, self.fps]
        backends = [
            (cv2.CAP_DSHOW, "DSHOW"),
            (cv2.CAP_MSMF, "MSMF"),
            (None, "Default"),  # Default backend
        ]

        for backend, _name in backends:
            cap = None
            try:
                if backend == cv2.CAP_DSHOW:
                    cap = cv2.VideoCapture(self.camera_index, backend, open_params)
                    # configure() must not set() again: any later set() on DSHOW renegotiates
                    # the stream (seen: back to 640x480 / YUY2).
                    self._applied_at_open = cap.isOpened()
                elif backend is not None:
                    cap = cv2.VideoCapture(self.camera_index, backend)
                else:
                    cap = cv2.VideoCapture(self.camera_index)

                if cap.isOpened():
                    # Successfully opened
                    return cap
                cap.release()
            except Exception as exc:
                LOGGER.debug("카메라 백엔드 열기 실패", exc_info=exc)
                if cap is not None:
                    cap.release()

        return None

    def configure(self) -> None:
        """Configure camera properties.

        Sets requested resolution and FPS, then reads back actual values.
        Camera may not support requested values - actual values are stored.
        """
        if not self.is_opened():
            return
        capture = self.capture
        if capture is None:
            return

        try:
            # Set properties, unless they were already applied when opening (DSHOW): any
            # set() afterwards renegotiates that stream (back to 640x480 / YUY2 ~7.5 fps).
            if not getattr(self, "_applied_at_open", False):
                if self.fourcc:
                    capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.fourcc))
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                capture.set(cv2.CAP_PROP_FPS, self.fps)

            # Read back actual values (camera may not support requested values)
            self._actual_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            self._actual_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            self._actual_fps = capture.get(cv2.CAP_PROP_FPS)
            LOGGER.info(
                "camera requested=%sx%s@%s actual=%sx%s@%s",
                self.width,
                self.height,
                self.fps,
                self._actual_width,
                self._actual_height,
                self._actual_fps,
            )
            if (self._actual_width, self._actual_height) != (self.width, self.height):
                LOGGER.warning(
                    "Camera resolution requirement unmet; calibrate at actual resolution"
                )

        except Exception as exc:
            LOGGER.warning("카메라 속성을 설정하지 못했습니다: %s", exc)

    def read(self) -> tuple[bool, Any | None]:
        """Read frame from camera.

        Returns:
            Tuple[bool, Optional]: (success, frame)
                - success: True if frame read successfully
                - frame: numpy array if success, None otherwise

        Note:
            Returns (False, None) if camera is not opened or read fails.
            Does not raise exception on read failure.
        """
        if not self.is_opened():
            return False, None
        capture = self.capture
        if capture is None:
            return False, None

        try:
            success, frame = capture.read()
            return success, frame
        except Exception as exc:
            LOGGER.warning("카메라 프레임을 읽지 못했습니다: %s", exc)
            return False, None

    def is_opened(self) -> bool:
        """Check if camera is currently open and accessible.

        Returns:
            bool: True if camera is open, False otherwise
        """
        return self.capture is not None and self.capture.isOpened()

    def get_width(self) -> int:
        """Get actual camera frame width.

        Returns:
            int: Actual frame width, or requested width if not configured
        """
        return self._actual_width if self._actual_width is not None else self.width

    def get_height(self) -> int:
        """Get actual camera frame height.

        Returns:
            int: Actual frame height, or requested height if not configured
        """
        return self._actual_height if self._actual_height is not None else self.height

    def get_fps(self) -> float:
        """Get actual camera FPS.

        Returns:
            float: Actual FPS, or requested FPS if not configured.
                   Note: Some cameras return 0.0 for FPS (not an error).
        """
        return self._actual_fps if self._actual_fps is not None else self.fps

    def release(self) -> None:
        """Release camera resources safely.

        Closes VideoCapture and sets capture to None.
        Safe to call multiple times.
        """
        if self.capture is not None:
            try:
                self.capture.release()
            except Exception as exc:
                LOGGER.warning("카메라를 해제하지 못했습니다: %s", exc)
            finally:
                self.capture = None

    def get_info(self) -> dict[str, int | float]:
        """Get camera information as dictionary.

        Returns:
            dict: Camera information including index, resolution, and FPS

        Example:
            {
                "index": 0,
                "width": 1280,
                "height": 720,
                "fps": 30.0
            }
        """
        return {
            "index": self.camera_index,
            "width": self.get_width(),
            "height": self.get_height(),
            "fps": self.get_fps(),
        }

    def __enter__(self) -> Camera:
        """Context manager entry - opens camera."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> Literal[False]:
        """Context manager exit - releases camera."""
        self.release()
        return False

    def __repr__(self) -> str:
        """String representation."""
        status = "opened" if self.is_opened() else "closed"
        return (
            f"Camera(index={self.camera_index}, "
            f"resolution={self.get_width()}x{self.get_height()}, "
            f"fps={self.get_fps()}, status='{status}')"
        )


def scan_available_cameras(max_index: int | None = None) -> list[int]:
    """Scan and find available camera indices.

    Tests camera indices from 0 to max_index to find working cameras.

    Args:
        max_index (int): Maximum index to test
                        (default: Config.CAMERA_SCAN_MAX_INDEX)

    Returns:
        List[int]: List of available camera indices

    Example:
        >>> available = scan_available_cameras()
        >>> print(available)  # [0, 1]
    """
    if max_index is None:
        max_index = Config.CAMERA_SCAN_MAX_INDEX

    if max_index < 0:
        raise ValueError("max_index는 0 이상이어야 합니다.")
    available_cameras: list[int] = []

    for index in range(max_index + 1):
        cap = None
        try:
            cap = cv2.VideoCapture(index)
            if cap.isOpened():
                available_cameras.append(index)
        except Exception as exc:
            LOGGER.debug("카메라 인덱스 %s 확인 실패", index, exc_info=exc)
        finally:
            if cap is not None:
                cap.release()

    return available_cameras
