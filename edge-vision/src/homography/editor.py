"""OpenCV front end for the homography editor.

All calculation lives in src/homography/edit.py. These classes only map keys and mouse events to that logic and draw; they read frames from a shared provider
and never open the camera. Windows are created only inside run_*_editor, so importing this
module needs no display.
"""

from __future__ import annotations

import math
import time

import cv2
import numpy as np

from src.app.display import draw_text
from src.homography.edit import (GRID_UNIT_STEP, GRID_UNITS, MEASURE_KINDS, measure_rows,
                                 read_edit_state, save_homography, unit_grid_lines)

HOMOGRAPHY_WINDOW = "Drown Guardian - homography"
SAVED, CANCELLED, CONTINUE = "saved", "cancelled", "continue"
_ARROWS = {2424832: "left", 2490368: "up", 2555904: "right", 2621440: "down",  # Windows
           65361: "left", 65362: "up", 65363: "right", 65364: "down"}  # X11/GTK
_ARROW_STEP = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}
CORNER_NAMES = ("왼쪽 위", "오른쪽 위", "오른쪽 아래", "왼쪽 아래")
_YELLOW, _GREEN, _RED, _CYAN, _WHITE = (0, 255, 255), (0, 220, 0), (0, 0, 255), (255, 255, 0), (255, 255, 255)
_BLUE, _MAGENTA, _GRID = (255, 128, 0), (255, 0, 255), (190, 190, 190)
_AXIS_X, _AXIS_Y = (0, 0, 255), (0, 200, 0)  # BGR: X axis red, Y axis green
_MEASURE_COLORS = {"board": _BLUE, "victim": _MAGENTA}
_MEASURE_KEYS = {"b": "board", "d": "victim"}


def shift_pressed() -> bool:
    """OpenCV reports no modifiers with keys, so ask Windows directly."""
    try:
        import ctypes

        return bool(ctypes.windll.user32.GetKeyState(0x10) & 0x8000)
    except (AttributeError, OSError):
        return False


def parse_numbers(text: str, count: int):
    """`count` positive-or-zero numbers separated by a comma, or None."""
    parts = [p.strip() for p in text.split(",")]
    if len(parts) != count:
        return None
    try:
        values = [float(p) for p in parts]
    except ValueError:
        return None
    return values if all(math.isfinite(v) and v >= 0 for v in values) else None


class TextPrompt:
    """Numeric entry drawn on the video (OpenCV has no text box)."""

    def __init__(self):
        self.label, self.text, self.submit = None, "", None

    @property
    def active(self) -> bool:
        return self.label is not None

    def open(self, label, submit, initial=""):
        self.label, self.text, self.submit = label, initial, submit

    def close(self):
        self.label, self.text, self.submit = None, "", None

    def key(self, code) -> None:
        if code == 27:
            self.close()
        elif code in (10, 13):
            submit, text = self.submit, self.text
            self.close()
            submit(text)
        elif code in (8, 127):
            self.text = self.text[:-1]
        elif 0 <= code < 128 and chr(code) in "0123456789.,-":
            self.text += chr(code)

    def line(self) -> str:
        return f"{self.label}: {self.text}_  (Enter 확인, Esc 취소)"


HOMOGRAPHY_HELP = [
    "1~4 점 선택 | 마우스 드래그 이동 | 방향키 1px (Shift 5px)",
    "s 저장 | r 저장본으로 | z 되돌리기 | g 격자 | Esc 취소",
    "t 수조 크기 입력 | v 검증점 추가 | c 검증점 지우기 | h 도움말",
    "b 보드 위치 찍기 | d 익수자 위치 찍기 | x 측정점 지우기 (측정점은 저장·전송 안 함)",
]


class HomographyEditorUI:
    def __init__(self, state, path, *, store=None):
        self.state, self.path, self.store = state, path, store
        self.prompt = TextPrompt()
        self.show_grid, self.show_help = True, False
        self.cursor, self.pending_check, self.message = None, None, ""
        # Hand-placed measurement points (pixels). Not part of the saved calibration or undo.
        self.measure = {kind: None for kind in MEASURE_KINDS}
        self.pending_measure = None
        self.result = None

    def on_mouse(self, event, x, y, *extra):
        self.cursor = (x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            if self.pending_measure is not None:
                kind, self.pending_measure = self.pending_measure, None
                self.measure[kind] = (x, y)
                self.message = f"{MEASURE_KINDS[kind]} 위치 찍음"
            elif self.pending_check is not None:
                self.state.add_check((x, y), self.pending_check)
                self.pending_check, self.message = None, "검증점 추가됨"
            else:
                self.state.begin_drag((x, y))
        elif event == cv2.EVENT_MOUSEMOVE and flags_left(extra):
            self.state.drag((x, y))
        elif event == cv2.EVENT_LBUTTONUP:
            self.state.end_drag()

    def _set_size(self, text):
        values = parse_numbers(text, 2)
        error = "형식: 가로,세로 (m)" if values is None else self.state.set_size(*values)
        self.message = error or "수조 크기 변경됨"

    def _set_check(self, text):
        values = parse_numbers(text, 2)
        if values is None:
            self.message = "형식: x,y (m)"
            return
        self.pending_check, self.message = values, f"이제 영상에서 ({values[0]:g}, {values[1]:g}) m 위치를 클릭"

    def _save(self):
        issues = self.state.issues()
        if issues:
            self.message = "저장 불가: " + "; ".join(issues)
            return CONTINUE
        try:
            meta = save_homography(self.path, self.state)
        except (ValueError, OSError) as exc:
            self.message = f"저장 실패: {exc}"
            return CONTINUE
        if self.store is not None and not self.store.reload(end_editing=True):
            self.message = f"적용 실패, 이전 행렬 유지: {self.store.last_error}"
            return CONTINUE
        self.result = meta
        return SAVED

    def handle_key(self, code, shift=False) -> str:
        if code < 0 or code == 255:
            return CONTINUE
        if self.prompt.active:
            self.prompt.key(code)
            return CONTINUE
        if code in _ARROWS:
            dx, dy = _ARROW_STEP[_ARROWS[code]]
            step = 5 if shift else 1
            self.state.nudge(dx * step, dy * step)
            return CONTINUE
        if code == 27:
            return CANCELLED
        char = chr(code & 0xFF).lower()
        if char in "1234":
            self.state.select(int(char) - 1)
        elif char == "s":
            return self._save()
        elif char == "r":
            self.state.revert()
            self.message = "마지막 저장본으로 되돌림"
        elif char == "z":
            self.state.undo()
        elif char == "g":
            self.show_grid = not self.show_grid
        elif char == "h":
            self.show_help = not self.show_help
        elif char == "t":
            self.prompt.open("수조 가로,세로 (m)", self._set_size,
                             f"{self.state.width_m:g},{self.state.height_m:g}")
        elif char == "v":
            self.prompt.open("검증점 x,y (m)", self._set_check)
        elif char == "c":
            self.state.clear_checks()
        elif char in _MEASURE_KEYS:
            self.pending_measure = _MEASURE_KEYS[char]
            self.message = f"영상에서 {MEASURE_KINDS[self.pending_measure]} 위치를 클릭"
        elif char == "x":
            self.measure = {kind: None for kind in MEASURE_KINDS}
            self.pending_measure, self.message = None, "측정점 지움"
        return CONTINUE

    def _draw_unit_grid(self, view, draft):
        state = self.state
        for line in unit_grid_lines(draft.matrix, state.width_m, state.height_m):
            a, b = tuple(map(int, line["a"])), tuple(map(int, line["b"]))
            if line["value"] != 0:  # value 0 = the axes, drawn on top later by _draw_axes
                cv2.line(view, a, b, _GRID, 1, cv2.LINE_AA)
            # Tick numbers: X values along the bottom edge (line start), Y values along the left edge.
            u, v = a
            offset = (-14, 18) if line["axis"] == "x" else (-44, 5)
            cv2.putText(view, str(line["value"]), (u + offset[0], v + offset[1]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, _WHITE, 1, cv2.LINE_AA)

    def _draw_axes(self, view, draft):
        """X axis (Y = 0, red) and Y axis (X = 0, green) through the origin, above the pool outline."""
        state = self.state
        axes = {(line["axis"], line["value"]): line for line in
                unit_grid_lines(draft.matrix, state.width_m, state.height_m, step=GRID_UNITS)}
        origin = tuple(map(int, axes[("y", 0)]["a"]))
        x_end = tuple(map(int, axes[("y", 0)]["b"]))  # Y = 0 line ends at X = 1000
        y_end = tuple(map(int, axes[("x", 0)]["b"]))  # X = 0 line ends at Y = 1000
        cv2.arrowedLine(view, origin, x_end, _AXIS_X, 3, cv2.LINE_AA, tipLength=0.04)
        cv2.arrowedLine(view, origin, y_end, _AXIS_Y, 3, cv2.LINE_AA, tipLength=0.04)
        cv2.putText(view, "X", (x_end[0] + 22, x_end[1] + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.9, _AXIS_X, 2)
        cv2.putText(view, "Y", (y_end[0] + 14, y_end[1] + 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, _AXIS_Y, 2)

    def _measure_lines(self, view, draft) -> list[str]:
        state = self.state
        result = measure_rows(draft, self.measure, state.image_size, state.width_m, state.height_m)
        lines = []
        for kind, row in result["rows"].items():
            color = _MEASURE_COLORS[kind]
            cv2.circle(view, tuple(row["pixel"]), 9, color, 2, cv2.LINE_AA)
            cv2.drawMarker(view, tuple(row["pixel"]), color, cv2.MARKER_CROSS, 14, 2)
            name = MEASURE_KINDS[kind]
            if row["world"] is None:
                lines.append(f"{name}: 픽셀 {tuple(row['pixel'])} -> 수조 밖 ({row['reason']})")
            else:
                (x, y), (gx, gy) = row["world"], row["units"]
                lines.append(f"{name}: 격자 ({gx:.0f}, {gy:.0f}) = x {x:.3f} m, y {y:.3f} m")
        board, victim = result["rows"].get("board"), result["rows"].get("victim")
        if board and victim:
            cv2.line(view, tuple(board["pixel"]), tuple(victim["pixel"]), _WHITE, 1, cv2.LINE_AA)
        if result["distance_m"] is not None:
            lines.append(f"보드-익수자 거리: {result['distance_m']:.3f} m ({result['distance_m'] * 100:.1f} cm)")
        return lines

    def render(self, image):
        state, view = self.state, image
        draft = state.draft()
        if draft is not None and self.show_grid:
            self._draw_unit_grid(view, draft)
        polygon = np.asarray(state.points, np.int32)
        cv2.polylines(view, [polygon], True, _YELLOW, 2, cv2.LINE_AA)
        if draft is not None and self.show_grid:
            self._draw_axes(view, draft)
        for i, (u, v) in enumerate(state.points):
            color = _RED if i == state.selected else _YELLOW
            cv2.circle(view, (u, v), 7, color, -1, cv2.LINE_AA)
            cv2.putText(view, str(i + 1), (u + 9, v - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        for check in state.check_points:
            cv2.drawMarker(view, tuple(check["pixel"]), _CYAN, cv2.MARKER_CROSS, 16, 2)
        lines = ["수조 위쪽 테두리가 아니라 보트와 마커가 놓이는 바닥면 모서리를 맞추세요",
                 f"편집 중: 웹 좌표 전송 중단 | {state.selected + 1}번 점 = 수조 {CORNER_NAMES[state.selected]} | "
                 f"수조 {state.width_m:g} x {state.height_m:g} m | h 도움말",
                 f"격자 0~{GRID_UNITS} ({GRID_UNIT_STEP} 간격, 원점 = 수조 왼쪽 아래): "
                 f"X {GRID_UNITS} = {state.width_m:g} m, Y {GRID_UNITS} = {state.height_m:g} m"]
        if self.cursor is not None and draft is not None:
            world, reason = draft.point(self.cursor, state.image_size)
            if world:
                gx, gy = world["x"] / state.width_m * GRID_UNITS, world["y"] / state.height_m * GRID_UNITS
                lines.append(f"커서 ({self.cursor[0]}, {self.cursor[1]}) -> 격자 ({gx:.0f}, {gy:.0f}) = "
                             f"x={world['x']:.3f} m, y={world['y']:.3f} m")
            else:
                lines.append(f"커서 ({self.cursor[0]}, {self.cursor[1]}) -> 수조 밖 ({reason})")
        if draft is not None:
            lines += self._measure_lines(view, draft)
        saved_size = getattr(state, "saved_image_size", None)
        if saved_size and list(saved_size) != list(state.image_size):
            lines.append(f"경고: 현재 해상도 {state.image_size[0]}x{state.image_size[1]} != 저장본 "
                         f"{saved_size[0]}x{saved_size[1]}")
        if self.store is not None and self.store.last_error:
            lines.append(f"리로드 오류: {self.store.last_error}")
        rows = state.check_rows(draft)
        for i, row in enumerate(rows):
            if row["error_cm"] is None:
                lines.append(f"검증 {i + 1}: 기대 ({row['expected'][0]:.3f}, {row['expected'][1]:.3f}) 측정 불가 "
                             f"({row['reason']})")
            else:
                lines.append(f"검증 {i + 1}: 기대 ({row['expected'][0]:.3f}, {row['expected'][1]:.3f}) 계산 "
                             f"({row['measured'][0]:.3f}, {row['measured'][1]:.3f}) 오차 {row['error_cm']:.2f} cm")
        lines += [f"저장 불가: {issue}" for issue in state.issues()]
        if self.show_help:
            lines += HOMOGRAPHY_HELP
        if self.message:
            lines.append(self.message)
        if self.prompt.active:
            lines.append(self.prompt.line())
        return draw_text(view, lines)


def flags_left(extra) -> bool:
    return bool(extra and extra[0] & cv2.EVENT_FLAG_LBUTTON)


def _wait_frame(latest_frame, should_stop):
    while not should_stop():
        frame = latest_frame()
        if frame is not None:
            return frame
        time.sleep(0.02)
    return None


def _loop(window, ui, latest_frame, should_stop) -> str:
    """Show frames at camera rate until the operator closes the editor."""
    from src.app.display import ensure_highgui

    ensure_highgui()
    cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(window, ui.on_mouse)
    try:
        while not should_stop():
            frame = latest_frame()
            cv2.imshow(window, ui.render(frame.image.copy()))
            outcome = ui.handle_key(cv2.waitKeyEx(20), shift_pressed())
            if outcome != CONTINUE:
                return outcome
            if cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                return CANCELLED
        return CANCELLED
    finally:
        try:
            cv2.destroyWindow(window)
        except cv2.error:
            pass


def run_homography_editor(path, latest_frame, *, store=None, should_stop=lambda: False):
    """Blocks until saved or cancelled. Coordinates stay off the web while this runs; on any
    exit without a save the previous matrix resumes. Returns saved metadata or None."""
    if store is not None:
        store.begin_editing()
    try:
        frame = _wait_frame(latest_frame, should_stop)
        if frame is None:
            return None
        state = read_edit_state(path, (frame.image.shape[1], frame.image.shape[0]))
        ui = HomographyEditorUI(state, path, store=store)
        outcome = _loop(HOMOGRAPHY_WINDOW, ui, latest_frame, should_stop)
        return ui.result if outcome == SAVED else None
    finally:
        if store is not None:
            store.end_editing()
