"""ArUco-only check: detection rate, raw / corrected heading, heading-offset measurement.

    venv\\Scripts\\python.exe scripts/aruco/aruco_check.py [--expected-deg 90] [--write]
    venv\\Scripts\\python.exe scripts/aruco/aruco_check.py --world      # measure in the water plane

Default: NO homography (reads configs/aruco.yaml only). Heading is the pixel heading
(image up = +Y), which equals the world heading only for a top-down camera aligned with the
pool. --world uses calibration/homography.yaml as the runtime does (heading_mode=world).

Live window: board-marker detection rate (last ~1 s), raw heading, offset-applied heading.
1. Point the bow at a known direction (default +Y = 90 deg) and hold still.
2. SPACE: 2 s of samples -> circular (sin/cos) mean of the raw heading, std, and the
   recommended heading_offset_deg = normalize(expected - raw) in [-180, 180).
configs/aruco.yaml is changed only with --write, after showing old/new and a "y".
Measurement only: no boat commands.
"""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heading_tools as ht  # noqa: E402


def report(summary, expected, current_offset, right_angle_tolerance):
    raw = summary["mean_deg"]
    print()
    print(ht.format_table(
        ["항목", "값"],
        [["샘플 수 / 시도 프레임", f"{summary['samples']} / {summary['attempts']}"],
         ["마커 검출률", f"{summary['detection_rate']:.0%}"],
         ["평균 raw 헤딩(원형 평균)", ht.fmt(raw, "{:.2f}°")],
         ["표준편차(흔들림)", ht.fmt(summary["std_deg"], "{:.2f}°")],
         ["현재 heading_offset_deg", f"{current_offset:g}°"],
         ["기대 각도", f"{expected:g}°"]]))
    if raw is None:
        print("\n권장 오프셋을 계산할 수 없음: 유효한 마커 측정이 없음")
        return None
    offset = ht.recommend_offset(expected, raw)
    print(f"\n권장 heading_offset_deg = {offset:+.1f}°   (= 기대 {expected:g}° - 측정 raw {raw:.1f}°, "
          "-180~180 정규화)")
    for warning in summary["warnings"]:
        print(f"경고: {warning} -> 이 값은 신뢰할 수 없음")
    gap = ht.right_angle_gap(offset)
    if gap > right_angle_tolerance:
        print(f"경고: 오프셋이 0/90/180/270°에서 {gap:.1f}° 벗어남 -> 마커가 비스듬히 붙었거나 보트 정렬이 "
              "틀렸을 가능성. 마커 위쪽 변이 선수를 향하도록 다시 붙이는 것을 권장")
    return offset


class RateReader:
    """LiveReader wrapper that keeps a rolling detection rate for the overlay."""

    def __init__(self, reader, window=30):
        self.reader, self.locator = reader, reader.locator
        self.hits = deque(maxlen=window)

    def read(self):
        image, pose = self.reader.read()
        if pose is not None:
            self.hits.append(pose["tracking_valid"])
        return image, pose

    def rate(self):
        return sum(self.hits) / len(self.hits) if self.hits else 0.0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=ht.ROOT / "configs/vision.yaml",
                   help="vision config naming aruco_config (and homography_config for --world)")
    p.add_argument("--world", action="store_true", help="use the homography (heading_mode=world)")
    p.add_argument("--profile", help="ArUco profile (default: active profile in configs/aruco.yaml)")
    p.add_argument("--expected-deg", type=float, default=90.0)
    p.add_argument("--seconds", type=float, default=2.0)
    p.add_argument("--camera-index", type=int)
    p.add_argument("--max-std", type=float, default=ht.MAX_STD_DEG)
    p.add_argument("--min-samples", type=int, default=ht.MIN_SAMPLES)
    p.add_argument("--min-rate", type=float, default=ht.MIN_DETECTION_RATE)
    p.add_argument("--right-angle-tolerance", type=float, default=ht.RIGHT_ANGLE_TOLERANCE_DEG)
    p.add_argument("--write", action="store_true", help="offer to save to configs/aruco.yaml (asks first)")
    p.add_argument("--no-display", action="store_true", help="terminal only (Enter to start)")
    args = p.parse_args()
    expected = args.expected_deg % 360

    camera = None
    try:
        config, calibration, locator = ht.load_setup(args.config, use_homography=args.world,
                                                     heading_mode="world" if args.world else None,
                                                     profile=args.profile, measuring=True)
        camera, size, _ = ht.open_camera(config, args.camera_index)
        ht.check_image_size(calibration, size)
    except ht.SetupError as exc:
        if camera:
            camera.release()
        sys.exit(f"오류: {exc}")
    mode = "world(호모그래피)" if args.world else "pixel(호모그래피 없음)"
    print(f"모드 {mode}, board_marker_id={locator.marker_id}, heading_offset_deg={locator.offset:g}°")
    offset, reliable = None, False
    try:
        reader = RateReader(ht.LiveReader(camera, locator))
        session = ht.Interactive(reader, locator.offset, "aruco check", display=not args.no_display)
        hint = ht.DIRECTION_HINTS.get(round(expected) % 360, f"{expected:g}°")
        base = [f"[{mode}] 보트 선수를 {hint}, 기대 {expected:g}° 방향으로 정렬하고 고정"]
        original_show = session.show
        session.show = lambda image, pose, lines: original_show(
            image, pose, lines + [f"최근 검출률 {reader.rate():.0%}"])
        while session.wait_for_space(base):
            data = session.sample(args.seconds, base)
            summary = ht.summarize_samples(data["raw"], data["attempts"], min_samples=args.min_samples,
                                           min_rate=args.min_rate, max_std=args.max_std)
            offset = report(summary, expected, locator.offset, args.right_angle_tolerance)
            reliable = summary["reliable"]
            print("\n다시 측정하려면 스페이스바, 끝내려면 q")
        session.close()
    except ht.SetupError as exc:
        sys.exit(f"오류: {exc}")
    finally:
        camera.release()
    if offset is not None and args.write:
        if not reliable:
            print("\n주의: 마지막 측정이 신뢰 기준을 통과하지 못함(위 경고). 재측정을 권장")
        session = ht.make_session(f"aruco_check {'world' if args.world else 'pixel'} live", size, "live")
        ht.write_offset(ht.aruco_config_path(args.config), offset, session, profile=args.profile)
    elif offset is not None:
        print("\n설정은 바꾸지 않음. 반영하려면 --write (확인 후 configs/aruco.yaml의 해당 프로파일만 수정)")


if __name__ == "__main__":
    main()
