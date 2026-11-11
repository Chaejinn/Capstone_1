"""애플리케이션 설정과 프로젝트 경로 관리."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

try:
    import torch
except ImportError: # The ONNX + remote-classifier edge client does not require torch.
    torch = None


class Config:
    """Runtime defaults shared by the webcam and detector modules."""

    PROJECT_ROOT: ClassVar[Path] = Path(__file__).resolve().parents[2]
    WEIGHTS_DIR: ClassVar[Path] = PROJECT_ROOT / "weights"

    CAMERA_INDEX: ClassVar[int] = 0
    CAMERA_WIDTH: ClassVar[int] = 1280
    CAMERA_HEIGHT: ClassVar[int] = 720
    CAMERA_FPS: ClassVar[int] = 30
    CAMERA_SCAN_MAX_INDEX: ClassVar[int] = 5

    MODEL_TYPE: ClassVar[str] = "rfdetr-nano"
    CONFIDENCE_THRESHOLD: ClassVar[float] = 0.5
    RFDETR_WEIGHTS_PATH: ClassVar[Path] = WEIGHTS_DIR / "rfdetr" / "checkpoint_best_total.pth"
    DETECTION_CLASS_NAME: ClassVar[str] = "human_dummy"
    DEVICE: ClassVar[str] = "cuda" if torch is not None and torch.cuda.is_available() else "cpu"

    @classmethod
    def get_device(cls) -> str:
        return cls.DEVICE
