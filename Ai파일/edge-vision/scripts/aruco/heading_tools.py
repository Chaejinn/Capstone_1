"""Shared helpers for the ArUco / pose check scripts (measurement only, no boat control).

Heading itself is ALWAYS computed by ``BoardLocator.measure`` (src/aruco/board.py),
the same code the runtime uses. This module only averages, compares and displays it.

Convention (docs/WEB_INTERFACE.md): water-plane frame, origin = pool lower-left corner,
0 deg = +X (pool right), increasing counter-clockwise (90 deg = +Y, pool far side).
``BoardLocator`` returns ``heading = (raw + heading_offset_deg) % 360``, so
``raw = (heading - heading_offset_deg) % 360``. The offset lives in configs/aruco.yaml.

Pure functions (no camera) are unit-tested in tests/test_heading_tools.py.
"""

from __future__ import annotations

import math
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Acceptance defaults (overridable by CLI flags).
MIN_SAMPLES = 20  # ~2 s at the 27 fps measured on the 1280x720 webcam, allowing drops
MIN_DETECTION_RATE = 0.8
MAX_STD_DEG = 3.0
RIGHT_ANGLE_TOLERANCE_DEG = 10.0  # offset farther than this from 0/90/180/270 => marker skewed

DIRECTION_HINTS = {
    0: "수조 오른쪽(+X)",
    45: "오른쪽 위 대각선(+X와 +Y 사이)",
    90: "수조 위쪽/먼 쪽(+Y)",
    135: "왼쪽 위 대각선",
    180: "수조 왼쪽(-X)",
    225: "왼쪽 아래 대각선",
    270: "수조 아래쪽/가까운 쪽(-Y)",
    315: "오른쪽 아래 대각선",
}


# ---------------------------------------------------------------- angle math (pure)

def normalize_180(deg: float) -> float:
    """Wrap to [-180, 180)."""
    return (deg + 180.0) % 360.0 - 180.0


def circular_mean(degs) -> float | None:
    """Mean direction via sin/cos averaging, in [0, 360). Safe across the 0/360 seam."""
    degs = [d for d in degs if d is not None]
    if not degs:
        return None
    s = sum(math.sin(math.radians(d)) for d in degs) / len(degs)
    c = sum(math.cos(math.radians(d)) for d in degs) / len(degs)
    if math.hypot(s, c) < 1e-9:
        return None  # directions cancel out: no meaningful mean
    return math.degrees(math.atan2(s, c)) % 360.0


def circular_std(degs) -> float | None:
    """Circular standard deviation in degrees, sqrt(-2 ln R)."""
    degs = [d for d in degs if d is not None]
    if not degs:
        return None
    s = sum(math.sin(math.radians(d)) for d in degs) / len(degs)
    c = sum(math.cos(math.radians(d)) for d in degs) / len(degs)
    r = min(1.0, math.hypot(s, c))
    if r <= 1e-12:
        return 180.0
    return math.degrees(math.sqrt(max(0.0, -2.0 * math.log(r))))


def raw_heading(pose: dict, offset_deg: float) -> float | None:
    """Undo heading_offset_deg on a measured pose (None when not measured)."""
    if not pose or not pose.get("tracking_valid") or pose.get("heading") is None:
        return None
    return (pose["heading"] - offset_deg) % 360.0


def recommend_offset(expected_deg: float, measured_raw_deg: float) -> float:
    """heading_offset_deg that makes raw + offset == expected, in [-180, 180)."""
    return normalize_180(expected_deg - measured_raw_deg)


def right_angle_gap(offset_deg: float) -> float:
    """Distance (deg) from the offset to the nearest of 0/90/180/270."""
    return min(abs(normalize_180(offset_deg - k)) for k in (0, 90, 180, 270))


def summarize_samples(headings, attempts: int, *, min_samples=MIN_SAMPLES,
                      min_rate=MIN_DETECTION_RATE, max_std=MAX_STD_DEG) -> dict:
    """headings: per-frame values (None = marker not measured); attempts: frames tried."""
    valid = [h for h in headings if h is not None]
    rate = len(valid) / attempts if attempts else 0.0
    mean, std = circular_mean(valid), circular_std(valid)
    warnings = []
    if len(valid) < min_samples:
        warnings.append(f"샘플 부족: {len(valid)}개 < {min_samples}개")
    if attempts and rate < min_rate:
        warnings.append(f"마커 검출률 낮음: {rate:.0%} < {min_rate:.0%} (조명·반사·초점·마커 크기 확인)")
    if std is not None and std > max_std:
        warnings.append(f"흔들림 큼: 표준편차 {std:.1f}° > {max_std}° (보트 고정, 물결 정지 후 재측정)")
    if mean is None:
        warnings.append("유효한 헤딩 없음")
    return {"samples": len(valid), "attempts": attempts, "detection_rate": rate,
            "mean_deg": mean, "std_deg": std, "warnings": warnings,
            "reliable": not warnings}


def assess_directions(rows, tolerance_deg: float) -> dict:
    """rows: dicts with expected_deg and error_deg (None = not measured).

    Constant error across directions  -> offset problem (adjust heading_offset_deg).
    Error that varies with direction  -> camera not top-down, marker bent, or bad calibration.
    Measured ~= -expected (+ const)   -> rotation sense reversed (mirrored axes).
    """
    measured = [r for r in rows if r.get("error_deg") is not None]
    result = {"tolerance_deg": tolerance_deg, "all_measured": len(measured) == len(rows)}
    result["passed"] = bool(measured) and result["all_measured"] and all(
        abs(r["error_deg"]) <= tolerance_deg for r in measured)
    if len(measured) < 2:
        result["pattern"] = "insufficient"
        result["message"] = "측정된 방향이 2개 미만이라 오차 패턴을 판정할 수 없음"
        return result
    errors = [r["error_deg"] for r in measured]
    mean_error = normalize_180(circular_mean([e % 360 for e in errors]))
    spread = max(abs(normalize_180(e - mean_error)) for e in errors)
    # Mirror test: if measured = -expected + c, then measured + expected is constant.
    sums = [(r["expected_deg"] + r["expected_deg"] + r["error_deg"]) % 360 for r in measured]
    mirror_c = circular_mean(sums)
    mirror_spread = (max(abs(normalize_180(s - mirror_c)) for s in sums)
                     if mirror_c is not None else 180.0)
    result.update(mean_error_deg=mean_error, spread_deg=spread)
    if spread > tolerance_deg and mirror_spread <= tolerance_deg:
        result["pattern"] = "reversed"
        result["message"] = ("회전 방향이 반대로 보임(측정 ≈ -기대): 캘리브레이션 클릭 순서나 좌표축이 "
                             "뒤집혔을 가능성. --check-rotation으로 확인")
    elif spread <= tolerance_deg:
        if abs(mean_error) <= tolerance_deg:
            result["pattern"] = "consistent_ok"
            result["message"] = "방향별 오차가 일정하고 작음"
        else:
            result["pattern"] = "constant_offset"
            result["message"] = (f"방향별 오차가 일정({mean_error:+.1f}°): 오프셋 문제. "
                                 f"heading_offset_deg에 {-mean_error:+.1f}° 더하거나 "
                                 "aruco_check.py / tune_heading_offset.py로 다시 측정")
    else:
        result["pattern"] = "inconsistent"
        result["message"] = (f"방향별 오차가 들쭉날쭉(편차 ±{spread:.1f}°): 카메라가 비스듬함(탑뷰 아님), "
                             "마커 휘어짐/들뜸, 또는 호모그래피 클릭 오차 가능성")
    return result


def rotation_trend(headings, max_step_deg: float = 90.0) -> dict:
    """Unwrapped cumulative change of a heading sequence (None entries skipped).

    Steps larger than max_step_deg between consecutive samples are ambiguous and ignored.
    """
    total, last, ignored, used = 0.0, None, 0, 0
    for h in headings:
        if h is None:
            continue
        if last is not None:
            step = normalize_180(h - last)
            if abs(step) > max_step_deg:
                ignored += 1
            else:
                total += step
                used += 1
        last = h
    return {"total_deg": total, "steps": used, "ignored_steps": ignored}


def judge_rotation(trend: dict, min_turn_deg: float = 30.0) -> tuple[str, str]:
    total = trend["total_deg"]
    if trend["steps"] < 5 or abs(total) < min_turn_deg:
        return "insufficient", (f"회전량 부족({total:+.0f}°): 보트를 반시계로 {min_turn_deg:.0f}° 이상 "
                                "천천히 돌려 다시 시도")
    if total > 0:
        return "ok", f"반시계 회전 시 헤딩 증가({total:+.0f}°): 각도 규약 일치"
    return "reversed", (f"반시계 회전 시 헤딩 감소({total:+.0f}°): 각도 규약 불일치. "
                        "캘리브레이션 클릭 순서(UL, UR, LR, LL)와 +Y 방향 확인")


# ---------------------------------------------------------------- config / yaml

_LINE = r"^({key}:[ \t]*)([^#\r\n]*?)([ \t]*(?:#[^\r\n]*)?)(\r?\n)?$"


def update_offset_text(text: str, new_offset: float, source: str | None = None):
    """Replace top-level heading_offset_deg (and heading_offset_source) in configs/aruco.yaml
    text, keeping comments and every other line. Returns (text, old_offset)."""
    lines = text.splitlines(keepends=True)
    old = None
    updates = [("heading_offset_deg", f"{new_offset:g}")]
    if source is not None:
        updates.append(("heading_offset_source", _yaml_str(source)))
    for key, value in updates:
        pattern = re.compile(_LINE.format(key=key))
        for i, line in enumerate(lines):
            match = pattern.match(line)
            if match:
                if key == "heading_offset_deg":
                    old = float(match.group(2))
                lines[i] = f"{match.group(1)}{value}{match.group(3)}{match.group(4) or ''}"
                break
        else:
            raise ValueError(f"{key} not found in ArUco config")
    return "".join(lines), old


def _yaml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def update_profile_text(text: str, profile: str, offset: float, session: dict):
    """Set profiles.<profile>.heading_offset_deg and .session in profile-form aruco.yaml text.
    Only those two lines of that one profile change; comments and other profiles are kept.
    Returns (text, old_offset or None)."""
    import json

    lines = text.splitlines(keepends=True)
    start = next((i for i, l in enumerate(lines) if re.match(r"^profiles:[ \t]*(#.*)?\r?\n?$", l)), None)
    if start is None:
        raise ValueError("profiles: section not found in ArUco config")
    head = re.compile(rf"^  {re.escape(profile)}:[ \t]*(#[^\r\n]*)?(\r?\n)?$")
    begin = next((i for i in range(start + 1, len(lines)) if head.match(lines[i])), None)
    if begin is None:
        raise ValueError(f"profiles.{profile} not found in ArUco config")
    end = begin + 1
    while end < len(lines) and (not lines[end].strip() or lines[end].startswith("    ")):
        end += 1
    old, done = None, set()
    for key, value in (("heading_offset_deg", f"{offset:g}"),
                       ("session", json.dumps(session, ensure_ascii=False))):
        pattern = re.compile(_LINE.format(key="    " + key))
        for i in range(begin + 1, end):
            match = pattern.match(lines[i])
            if match:
                if key == "heading_offset_deg":
                    raw = match.group(2).strip()
                    old = None if raw in ("null", "~", "") else float(raw)
                lines[i] = f"{match.group(1)}{value}{match.group(3)}{match.group(4) or ''}"
                done.add(key)
                break
        else:
            raise ValueError(f"profiles.{profile}.{key} not found in ArUco config")
    return "".join(lines), old


def aruco_config_path(config_path: Path) -> Path:
    import yaml
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    return Path(config_path).resolve().parent / config["aruco_config"]


def make_session(method: str, resolution, image_session: str) -> dict:
    from datetime import datetime, timezone
    return {"measured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "camera_resolution": list(resolution) if resolution else None,
            "image_session": image_session, "method": method}


def write_offset(aruco_path: Path, offset: float, source, ask=input, profile=None) -> bool:
    """Show old -> new and write only after an explicit 'y'.

    Profile-form aruco.yaml: `source` is the session dict and `profile` the target
    (default: the active profile). Legacy flat form: `source` is a text label."""
    import yaml

    text = aruco_path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if "profiles" in data:
        profile = profile or data["profile"]
        session = source if isinstance(source, dict) else make_session(str(source), None, "unknown")
        new_text, old = update_profile_text(text, profile, round(offset, 1), session)
        where = f"profiles.{profile}.heading_offset_deg"
    else:
        new_text, old = update_offset_text(text, round(offset, 1), str(source))
        where = "heading_offset_deg"
    old_text = "null(미측정)" if old is None else f"{old:g}"
    print(f"\n{aruco_path}: {where}  {old_text}  ->  {round(offset, 1):g}  (기록: {source})")
    try:
        answer = ask("이 값으로 저장할까요? [y/N]: ").strip().lower()
    except EOFError:
        answer = ""
    if answer != "y":
        print("저장하지 않음")
        return False
    temporary = aruco_path.with_suffix(aruco_path.suffix + ".tmp")
    temporary.write_text(new_text, encoding="utf-8")
    temporary.replace(aruco_path)
    print("저장함")
    return True


class SetupError(RuntimeError):
    pass


CALIBRATE_HINT = (
    "  venv\\Scripts\\python.exe scripts\\scripts/homography/calib_server.py\n"
    "  (클릭 순서: 실제 수조 왼쪽 위 -> 오른쪽 위 -> 오른쪽 아래 -> 왼쪽 아래, Enter 저장)\n"
    "  보정 전 마커만 보려면: venv\\Scripts\\python.exe scripts/aruco/aruco_check.py")


def load_setup(config_path: Path, *, use_homography=True, heading_mode=None, profile=None,
               measuring=False):
    """Return (config, calibration, locator) using the same loaders as src.app.vision.run.

    profile: ArUco profile (default: the active one in configs/aruco.yaml).
    measuring=True: offset-measuring tools; an unmeasured (null) offset is allowed and
    reported as 0 so the raw heading can be read. Otherwise the profile's missing_offset
    policy applies (boat: refuse, standin: warn)."""
    import yaml
    from src.aruco.marker import load_aruco_settings
    from src.aruco.board import BoardLocator, load_pose_inputs

    path = Path(config_path).resolve()
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    try:
        if not use_homography:  # ArUco only: never touches the homography file
            aruco = load_aruco_settings(path.parent / config["aruco_config"], profile)
            options = {**config.get("pose", {}), "use_homography": False, "heading_mode": "pixel"}
            return config, None, BoardLocator(None, aruco, allow_unmeasured_offset=measuring, **options)
        calibration, aruco, options = load_pose_inputs(path, config, profile=profile)
        if calibration.matrix is None:
            raise SetupError(f"호모그래피 캘리브레이션이 없음/무효({calibration.reason}). "
                             f"수면 좌표에는 보정이 필요:\n{CALIBRATE_HINT}")
        if heading_mode:
            options["heading_mode"] = heading_mode
        return config, calibration, BoardLocator(calibration, aruco, allow_unmeasured_offset=measuring,
                                                 **options)
    except (ValueError, KeyError) as exc:
        raise SetupError(str(exc)) from None


def open_camera(config: dict, camera_index=None):
    """Open the configured webcam or exit with the cause and how to fix it."""
    from src.capture.camera import Camera

    options = dict(config.get("camera", {}))
    if camera_index is not None:
        options["camera_index"] = camera_index
    camera = Camera(**options)
    try:
        camera.open()
    except RuntimeError as exc:
        raise SetupError(
            f"카메라를 열 수 없음 (index={options.get('camera_index')}): {exc}\n"
            "  해결: 1) 다른 프로그램(Zoom/Teams/브라우저/다른 스크립트)이 카메라를 쓰고 있으면 종료\n"
            "        2) Windows 설정 > 개인정보 > 카메라 > '데스크톱 앱 접근 허용' 켜기\n"
            "        3) USB 재연결 후 다른 번호 시도: --camera-index 1\n"
            "        4) 사용 가능한 번호 확인: venv\\Scripts\\python.exe -c "
            "\"from src.capture.camera import scan_available_cameras as s; print(s())\"") from exc
    width, height = camera.get_width(), camera.get_height()
    expected = config["camera"].get("width"), config["camera"].get("height")
    return camera, (width, height), expected


def check_image_size(calibration, size):
    if calibration is None:
        return
    if list(size) != list(calibration.config.get("image_size") or []):
        raise SetupError(
            f"카메라 해상도 {size[0]}x{size[1]}가 캘리브레이션 해상도 {calibration.config.get('image_size')}와 "
            "다름. 같은 해상도로 다시 보정(scripts/homography/calib_server.py)하거나 camera.width/height를 맞출 것")


class LiveReader:
    """Single-threaded webcam -> Frame -> BoardLocator.measure (the production function)."""

    def __init__(self, camera, locator, max_silence_s=3.0):
        self.camera, self.locator = camera, locator
        self.frame_id = 0
        self.max_silence_s = max_silence_s
        self._last_ok = time.monotonic()

    def read(self):
        from src.capture.frames import Frame

        ok, image = self.camera.read()
        if not ok or image is None:
            if time.monotonic() - self._last_ok > self.max_silence_s:
                raise SetupError(
                    f"카메라에서 {self.max_silence_s:g}초 동안 프레임이 오지 않음. 다른 프로그램/이전 실행이 "
                    "카메라를 잡고 있는지 확인(작업 관리자에서 python.exe 종료), USB 재연결, --camera-index 변경")
            return None, None
        self._last_ok = time.monotonic()
        self.frame_id += 1
        frame = Frame(self.frame_id, time.time(), time.monotonic(), image)
        return image, view_pose(self.locator.measure(frame))


def view_pose(m: dict) -> dict:
    """BoardLocator.measure() -> the dict the scripts display (pixel_only counts as measured)."""
    return {**m, "tracking_valid": m["heading"] is not None}


# ---------------------------------------------------------------- drawing

def draw_text(image, lines, origin=(10, 10), color=(255, 255, 0)):
    from src.app.display import draw_text as draw

    return draw(image, lines, origin, color)


def draw_markers(image, locator):
    """Display only: outline detected markers and the top-edge (bow) arrow in pixels."""
    import cv2
    import numpy as np

    corners, ids, _ = locator.detect(image)
    if ids is None:
        return image
    cv2.aruco.drawDetectedMarkers(image, corners, ids)
    for c, marker_id in zip(corners, ids.ravel()):
        if int(marker_id) != locator.marker_id:
            continue
        p = np.asarray(c, dtype=float).reshape(4, 2)
        center, bow = p.mean(axis=0), (p[0] + p[1]) / 2
        tip = center + 2.0 * (bow - center)
        cv2.arrowedLine(image, tuple(map(int, center)), tuple(map(int, tip)), (0, 0, 255), 3,
                        tipLength=0.3)
    return image


def pose_lines(pose, offset):
    raw = raw_heading(pose, offset)
    if raw is None:
        status = pose.get("status") if pose else "no_frame"
        return [f"마커 없음/무효: {status}"]
    lines = [f"raw 헤딩 {raw:6.1f}°  | 오프셋 {offset:+.1f}° 적용 {pose['heading']:6.1f}°"]
    if pose.get("x") is not None:
        lines.append(f"위치 x={pose['x']:.3f} m, y={pose['y']:.3f} m")
    else:
        center = pose.get("center_px")
        lines.append("위치: 호모그래피 없음(m 좌표 null)" + (
            "" if center is None else f", 픽셀 ({center[0]:.0f}, {center[1]:.0f})"))
    return lines


def format_table(headers, rows) -> str:
    cells = [[str(h) for h in headers]] + [[str(c) for c in r] for r in rows]
    widths = [max(_width(row[i]) for row in cells) for i in range(len(headers))]
    out = []
    for n, row in enumerate(cells):
        out.append(" | ".join(c + " " * (w - _width(c)) for c, w in zip(row, widths)))
        if n == 0:
            out.append("-+-".join("-" * w for w in widths))
    return "\n".join(out)


def _width(text: str) -> int:
    import unicodedata
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def fmt(value, spec="{:.1f}", none="-"):
    return none if value is None else spec.format(value)


# ---------------------------------------------------------------- interactive sampling

def sample_for(read_pose, seconds: float, offset: float, clock=time.monotonic, on_frame=None):
    """Collect poses for `seconds`. read_pose() -> (image, pose); pose None = no frame."""
    raws, headings, poses, attempts = [], [], [], 0
    end = clock() + seconds
    while clock() < end:
        image, pose = read_pose()
        if pose is None:
            continue
        attempts += 1
        raws.append(raw_heading(pose, offset))
        headings.append(pose["heading"] if pose.get("tracking_valid") else None)
        poses.append(pose)
        if on_frame:
            on_frame(image, pose, end - clock())
    return {"raw": raws, "heading": headings, "poses": poses, "attempts": attempts}


class Interactive:
    """Live window (space = start, q/Esc = quit) or terminal Enter when --no-display."""

    def __init__(self, reader, offset, title, display=True):
        self.reader, self.offset, self.title, self.display = reader, offset, title, display
        if display:
            from src.app.display import ensure_highgui
            ensure_highgui()

    def show(self, image, pose, lines):
        import cv2
        if image is None:
            return 255
        view = draw_markers(image.copy(), self.reader.locator)
        draw_text(view, lines + pose_lines(pose, self.offset))
        cv2.imshow(self.title, view)
        return cv2.waitKey(1) & 255

    def wait_for_space(self, lines) -> bool:
        print("\n" + "\n".join(lines))
        if not self.display:
            try:
                return input("준비되면 Enter (q 입력 시 종료): ").strip().lower() != "q"
            except EOFError:
                return False
        while True:
            image, pose = self.reader.read()
            key = self.show(image, pose, lines + ["스페이스바 = 측정 시작, q/Esc = 종료"])
            if key == 32:
                return True
            if key in (27, ord("q"), ord("Q")):
                return False

    def sample(self, seconds, lines):
        def on_frame(image, pose, left):
            if self.display:
                self.show(image, pose, lines + [f"측정 중... {left:.1f}초 (움직이지 마세요)"])
        return sample_for(self.reader.read, seconds, self.offset, on_frame=on_frame)

    def close(self):
        if self.display:
            import cv2
            cv2.destroyAllWindows()


# ---------------------------------------------------------------- marker / person diagnostics

ALL_DICTIONARIES = tuple(f"DICT_{a}X{a}_{n}" for a in (4, 5, 6) for n in (50, 100, 250)) + ("DICT_ARUCO_ORIGINAL",)
MIN_SIDE_PX = 20  # below this the 4x4 cells are ~3 px: unreliable


def marker_side_px(corners) -> float:
    import numpy as np
    p = np.asarray(corners, dtype=float).reshape(4, 2)
    return float(np.mean([np.linalg.norm(p[i] - p[(i + 1) % 4]) for i in range(4)]))


def diagnose_no_marker(image, settings) -> list[str]:
    """Likely reasons the board marker was not measured (detection only, no heading)."""
    import cv2

    reasons = []
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, settings.dictionary))
    corners, ids, rejected = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters()).detectMarkers(image)
    if ids is not None:
        seen = sorted(set(int(i) for i in ids.ravel()))
        if settings.board_marker_id not in seen:
            reasons.append(f"다른 ID만 보임 {seen} (board_marker_id={settings.board_marker_id}): 인쇄한 ID 확인")
        elif list(ids.ravel()).count(settings.board_marker_id) > 1:
            reasons.append("같은 ID 마커가 여러 개 보임: 하나만 두기")
    for name in ALL_DICTIONARIES:
        if name == settings.dictionary:
            continue
        other = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco, name))
        _, other_ids, _ = cv2.aruco.ArucoDetector(other, cv2.aruco.DetectorParameters()).detectMarkers(image)
        if other_ids is not None:
            reasons.append(f"다른 사전 {name}의 ID {sorted(set(int(i) for i in other_ids.ravel()))} 감지: "
                           f"사전 불일치(설정 {settings.dictionary})")
            break
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
    if sharpness < 60:
        reasons.append(f"흐림(선명도 {sharpness:.0f} < 60): 초점·움직임 확인")
    glare = float((gray >= 250).mean())
    if glare > 0.02:
        reasons.append(f"반사/과노출(화소 {glare:.0%}가 포화): 조명 각도 바꾸기, 비닐·코팅 피하기")
    if rejected is not None and len(rejected) and ids is None:
        reasons.append(f"사각형 모양 {len(rejected)}개(격자·상자 모서리 등)가 있으나 어느 것도 ArUco 마커로 "
                       "판독되지 않음: 마커가 없거나, 있다면 흰 여백 부족·휘어짐·흐림")
    if not reasons:
        reasons.append("마커가 화면에 없거나 가려짐, 또는 너무 작음 "
                       f"(한 변 최소 {MIN_SIDE_PX} px 이상, 1280x720 기준 5 cm 마커가 수조 높이에서 보이는지 확인)")
    return reasons


_HOG = None


def detect_people(image) -> int:
    """Best-effort person check (OpenCV HOG body + Haar face). Top-down views of people are
    often missed, so this is a guard, not a guarantee."""
    import cv2

    global _HOG
    if _HOG is None:
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        face_path = getattr(getattr(cv2, "data", None), "haarcascades", "") + "haarcascade_frontalface_default.xml"
        face = cv2.CascadeClassifier(face_path)
        _HOG = (hog, None if face.empty() else face)
    hog, face = _HOG
    small = cv2.resize(image, (640, round(image.shape[0] * 640 / image.shape[1])))
    bodies, weights = hog.detectMultiScale(small, winStride=(8, 8))
    count = sum(1 for w in (weights.ravel() if len(weights) else []) if w > 0.6)
    if face is not None:
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        count += len(face.detectMultiScale(gray, 1.1, 6, minSize=(40, 40)))
    return count
