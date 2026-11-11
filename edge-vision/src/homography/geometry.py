"""Pure geometric checks shared by the editor and runtime loader."""
import math
import numpy as np

MIN_QUAD_AREA_FRACTION = 0.01
ASPECT_TOLERANCE = 1.35

def validate_quad(points, image_size, width_m, height_m, *, check_aspect=True) -> list[str]:
    """Reasons the four points cannot be saved (Korean, shown on screen). Empty = valid."""
    try:
        p = np.asarray(points, dtype=float)
    except (TypeError, ValueError):
        return ["점 형식이 잘못됨"]
    if p.shape != (4, 2) or not np.isfinite(p).all():
        return ["점 4개(왼쪽 위, 오른쪽 위, 오른쪽 아래, 왼쪽 아래)가 필요함"]
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in (width_m, height_m)):
        return ["수조 크기는 0보다 큰 값이어야 함"]
    if len({(float(u), float(v)) for u, v in p}) != 4:
        return ["같은 위치의 점이 있음(4점 중복)"]
    if (not isinstance(image_size, (list, tuple)) or len(image_size) != 2
            or any(type(v) is not int or v < 2 for v in image_size)):
        return ["이미지 크기는 2 이상의 정수 [width, height]여야 함"]
    reasons = []
    w, h = image_size
    outside = [i + 1 for i, (u, v) in enumerate(p) if not (0 <= u <= w - 1 and 0 <= v <= h - 1)]
    if outside:
        reasons.append(f"화면 밖 점: {outside}번")
    edges = np.roll(p, -1, axis=0) - p
    crosses = edges[:, 0] * np.roll(edges, -1, axis=0)[:, 1] - edges[:, 1] * np.roll(edges, -1, axis=0)[:, 0]
    if (crosses > 0).any() and (crosses < 0).any() or (crosses == 0).any():
        reasons.append("볼록 사각형이 아님(점이 꼬였거나 한 직선 위에 있음)")
        return reasons
    # Image rows grow downward, so a positive shoelace sum is clockwise on screen.
    area = 0.5 * float(np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1]))
    if area <= 0:
        reasons.append("점 순서가 화면 기준 시계 방향이 아님(좌우가 뒤집힌 매핑)")
    if abs(area) < MIN_QUAD_AREA_FRACTION * w * h:
        reasons.append(f"사각형이 너무 작음({abs(area):.0f} px², 최소 {MIN_QUAD_AREA_FRACTION * w * h:.0f} px²)")
    side = np.linalg.norm(edges, axis=1)
    ratio = ((side[0] + side[2]) / (side[1] + side[3])) / (width_m / height_m)
    if check_aspect and not 1 / ASPECT_TOLERANCE <= ratio <= ASPECT_TOLERANCE:
        reasons.append(f"가로세로 비율이 수조 크기와 맞지 않음(실제 대비 {ratio:.2f}배, 허용 "
                       f"{1 / ASPECT_TOLERANCE:.2f}~{ASPECT_TOLERANCE:.2f}배)")
    return reasons

