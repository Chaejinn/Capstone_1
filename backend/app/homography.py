"""
HomographyTransformer — 4점 대응으로 3x3 호모그래피 행렬을 DLT(Direct Linear Transform)로 계산.
class_srv.puml의 HomographyTransformer.calibrate(imgPts, worldPts) 대응.
실제 OpenCV 없이 numpy만으로 계산 (엣지 환경 의존성 최소화).
"""
from typing import List, Tuple

import numpy as np


def calibrate(img_points: List[List[float]], world_points: List[List[float]]) -> Tuple[np.ndarray, float]:
    """4쌍 이상의 대응점으로 H를 구하고, 재투영 오차(m)를 함께 반환한다."""
    if len(img_points) < 4 or len(world_points) < 4 or len(img_points) != len(world_points):
        raise ValueError("이미지 좌표와 실좌표는 각각 4점 이상, 같은 개수여야 합니다.")

    A = []
    for (x, y), (X, Y) in zip(img_points, world_points):
        A.append([-x, -y, -1, 0, 0, 0, x * X, y * X, X])
        A.append([0, 0, 0, -x, -y, -1, x * Y, y * Y, Y])
    A = np.array(A)

    _, _, vt = np.linalg.svd(A)
    h = vt[-1]
    H = h.reshape(3, 3)
    if abs(H[2, 2]) > 1e-12:
        H = H / H[2, 2]

    errors = []
    for (x, y), (X, Y) in zip(img_points, world_points):
        p = H @ np.array([x, y, 1.0])
        if abs(p[2]) < 1e-12:
            continue
        px, py = p[0] / p[2], p[1] / p[2]
        errors.append(((px - X) ** 2 + (py - Y) ** 2) ** 0.5)

    reproj_error_m = float(np.mean(errors)) if errors else float("inf")
    return H, reproj_error_m


def to_world(H: np.ndarray, img_x: float, img_y: float) -> Tuple[float, float]:
    p = H @ np.array([img_x, img_y, 1.0])
    if abs(p[2]) < 1e-12:
        return 0.0, 0.0
    return float(p[0] / p[2]), float(p[1] / p[2])
