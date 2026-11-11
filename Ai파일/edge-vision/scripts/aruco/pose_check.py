"""Pose check: ArUco + homography combined; pixel vs world heading per direction.

    venv\\Scripts\\python.exe scripts/aruco/pose_check.py [--angles 0 90 180 270 45] [--tolerance 5]

For each expected direction (SPACE = 2 s of samples) prints the offset-applied heading in
both modes from the SAME frames (BoardLocator.measure computes both):
    pixel  heading from image pixels (image up = +Y)
    world  bow vector end points projected by the homography (runtime default)
plus pixel - world and the world error against the expectation. A large pixel-world gap
means the camera is not top-down/aligned, so heading_mode=world is required.
Measurement only: no boat commands.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import heading_tools as ht  # noqa: E402


def direction_row(expected, poses, offset):
    pixel = ht.circular_mean([(p["pixel_heading_raw"] + offset) % 360 for p in poses
                              if p.get("pixel_heading_raw") is not None and p.get("world_heading_raw") is not None])
    world = ht.circular_mean([(p["world_heading_raw"] + offset) % 360 for p in poses
                              if p.get("world_heading_raw") is not None])
    world_std = ht.circular_std([(p["world_heading_raw"] + offset) % 360 for p in poses
                                 if p.get("world_heading_raw") is not None])
    return {"expected_deg": expected, "pixel_deg": pixel, "world_deg": world, "world_std": world_std,
            "pixel_minus_world": None if pixel is None or world is None else ht.normalize_180(pixel - world),
            "error_deg": None if world is None else ht.normalize_180(world - expected),
            "samples": sum(p.get("world_heading_raw") is not None for p in poses), "frames": len(poses)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, default=ht.ROOT / "configs/vision.yaml")
    p.add_argument("--angles", type=float, nargs="+", default=[0, 90, 180, 270, 45])
    p.add_argument("--tolerance", type=float, default=5.0)
    p.add_argument("--seconds", type=float, default=2.0)
    p.add_argument("--camera-index", type=int)
    p.add_argument("--no-display", action="store_true")
    args = p.parse_args()

    camera = None
    try:
        config, calibration, locator = ht.load_setup(args.config, heading_mode="world")
        camera, size, _ = ht.open_camera(config, args.camera_index)
        ht.check_image_size(calibration, size)
    except ht.SetupError as exc:
        if camera:
            camera.release()
        sys.exit(f"오류: {exc}")
    offset = locator.offset
    rows = []
    try:
        session = ht.Interactive(ht.LiveReader(camera, locator), offset, "pose check",
                                 display=not args.no_display)
        for expected in [a % 360 for a in args.angles]:
            hint = ht.DIRECTION_HINTS.get(round(expected) % 360, f"{expected:g}°")
            lines = [f"[{len(rows) + 1}/{len(args.angles)}] 선수를 {hint}({expected:g}°)으로 놓고 스페이스바"]
            if not session.wait_for_space(lines):
                break
            rows.append(direction_row(expected, session.sample(args.seconds, lines)["poses"], offset))
        session.close()
    except ht.SetupError as exc:
        sys.exit(f"오류: {exc}")
    finally:
        camera.release()
    if not rows:
        sys.exit(1)
    print(f"\nheading_offset_deg = {offset:g}° (두 모드 모두 한 번만 적용)")
    print(ht.format_table(
        ["기대", "pixel", "world", "pixel-world", "world 오차", "world 표준편차", "샘플"],
        [[f"{r['expected_deg']:g}°", ht.fmt(r["pixel_deg"], "{:.1f}°"), ht.fmt(r["world_deg"], "{:.1f}°"),
          ht.fmt(r["pixel_minus_world"], "{:+.1f}°"), ht.fmt(r["error_deg"], "{:+.1f}°"),
          ht.fmt(r["world_std"], "{:.1f}°"), f"{r['samples']}/{r['frames']}"] for r in rows]))
    gaps = [abs(r["pixel_minus_world"]) for r in rows if r["pixel_minus_world"] is not None]
    if gaps:
        worst = max(gaps)
        print(f"\npixel-world 최대 차이 {worst:.1f}°: " + (
            "카메라가 거의 탑뷰·정렬 상태 (두 모드가 일치)" if worst <= args.tolerance else
            "카메라가 비스듬하거나 수조 축과 어긋남 -> heading_mode=world 유지 필요"))
    verdict = ht.assess_directions(rows, args.tolerance)
    print(f"world 헤딩: {'합격' if verdict['passed'] else '불합격'} - {verdict['message']}")
    sys.exit(0 if verdict["passed"] else 1)


if __name__ == "__main__":
    main()
