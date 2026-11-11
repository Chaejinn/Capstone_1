"""Standalone homography editor, for when the main pipeline is not running.

    venv\\Scripts\\python.exe scripts/homography/calibration_editor.py homography [--homography-file F] [--video V]

Opens the camera itself through the same CaptureWorker/LatestFrames as the pipeline, so the
pipeline must be stopped first (one camera owner). Sends nothing to the web. While the pipeline
runs, use its --display window instead: e = homography.
Key lists: h inside the editor. Boat control commands are never produced.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aruco"))
import heading_tools as ht  # noqa: E402


def _start_source(args, config):
    import cv2
    from src.capture.frames import CaptureWorker, LatestFrames

    frames = LatestFrames()
    if args.video:
        source = cv2.VideoCapture(str(args.video))
        if not source.isOpened():
            raise ht.SetupError(f"영상을 열 수 없음: {args.video}")
        capture = CaptureWorker(source, frames, video_fps=source.get(cv2.CAP_PROP_FPS) or 30)
    else:
        camera, _size, _expected = ht.open_camera(config, args.camera_index)
        capture = CaptureWorker(camera, frames)
    capture.start()
    return frames, capture


def cmd_homography(args, config, path):
    from src.homography.editor import run_homography_editor
    from src.common.files import homography_path

    frames, capture = _start_source(args, config)
    try:
        result = run_homography_editor(homography_path(path.parent, config), lambda: frames.latest)
    finally:
        capture.close()
    if result is None:
        print("저장하지 않고 종료")
        return 1
    print(f"저장: {result['path']} (hash={result['homography_hash'][:12]}, {result['saved_at']})")
    for backup in result["backups"]:
        print(f"백업: {backup}")
    return 0


def main():
    import yaml
    from dotenv import load_dotenv
    from src.common.files import HOMOGRAPHY_FILE_ENV
    from src.homography.loader import HomographyConfigError

    load_dotenv(ht.ROOT / ".env")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", choices=("homography",))
    parser.add_argument("--config", type=Path, default=ht.ROOT / "configs/vision.yaml")
    parser.add_argument("--homography-file", type=Path)
    parser.add_argument("--camera-index", type=int)
    parser.add_argument("--video", type=Path, help="video file instead of the camera")
    args = parser.parse_args()
    if args.homography_file is not None:
        os.environ[HOMOGRAPHY_FILE_ENV] = str(args.homography_file)
    path = args.config.resolve()
    if not path.is_file():
        sys.exit(f"오류: {path}: vision config file not found")
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        sys.exit(cmd_homography(args, config, path))
    except (ht.SetupError, HomographyConfigError) as exc:
        sys.exit(f"오류: {exc}")


if __name__ == "__main__":
    main()
