"""Drown Guardian - Object Detection System.

Main package initialization.
"""

from __future__ import annotations

from typing import Any

__version__ = "0.1.0"
__author__ = "Drown Guardian Team"
__project__ = "Drown Guardian"

__all__ = [
    "Camera",
    "Config",
    "__project__",
    "__version__",
]


def __getattr__(name: str) -> Any:
    """무거운 OpenCV/모델 모듈은 실제 사용 시점에 로드한다."""
    if name == "Config":
        from src.app.config import Config

        return Config
    if name == "Camera":
        from src.capture.camera import Camera

        return Camera
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
