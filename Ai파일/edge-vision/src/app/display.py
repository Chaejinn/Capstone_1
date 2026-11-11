"""Optional operator window: tracks with the latest raw VLM label and FR-JDG-003 assessment."""
from __future__ import annotations

import cv2

WINDOW = "Drown Guardian"
COLORS = {"NORMAL": (0, 200, 0), "ABNORMAL": (0, 200, 255), "DROWNING": (0, 0, 255)}


_FONT = None


def _font(size=22):
    global _FONT
    if _FONT is None:
        try:
            from PIL import ImageFont
        except ImportError:
            _FONT = False
            return _FONT
        for candidate in ("C:/Windows/Fonts/malgun.ttf", "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                          "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"):
            try:
                _FONT = ImageFont.truetype(candidate, size)
                break
            except OSError:
                continue
        else:
            _FONT = False
    return _FONT


def draw_text(image, lines, origin=(10, 10), color=(255, 255, 0)):
    """Korean-capable overlay (PIL font), falling back to ASCII cv2 text."""
    import cv2
    import numpy as np

    font = _font()
    if not font:
        for i, line in enumerate(lines):
            cv2.putText(image, line.encode("ascii", "replace").decode(), (origin[0], origin[1] + 24 * (i + 1)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color[::-1], 2)
        return image
    from PIL import Image, ImageDraw

    pil = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    y = origin[1]
    for line in lines:
        box = draw.textbbox((origin[0], y), line, font=font)
        draw.rectangle((box[0] - 4, box[1] - 2, box[2] + 4, box[3] + 2), fill=(0, 0, 0))
        draw.text((origin[0], y), line, font=font, fill=color)
        y = box[3] + 8
    image[:] = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
    return image


def ensure_highgui() -> None:
    gui_support = next(
        (
            line.partition(":")[2].strip()
            for line in cv2.getBuildInformation().splitlines()
            if line.strip().startswith("GUI:")
        ),
        "",
    )
    if not gui_support or gui_support.upper() == "NONE":
        raise RuntimeError(
            "OpenCV GUI support is missing. Uninstall opencv-python-headless and "
            "install opencv-python>=4.8,<5."
        )


def draw_tracks(image, tracks, judgements):
    """``judgements``: track_id -> (raw_state, decision, assessment) from StatePublisher.last."""
    height, width = image.shape[:2]
    for track in tracks:
        track_id = int(track["track_id"])
        x1, y1, x2, y2 = (int(value) for value in track["bbox"])
        x1, x2 = max(0, min(x1, width - 1)), max(0, min(x2, width - 1))
        y1, y2 = max(0, min(y1, height - 1)), max(0, min(y2, height - 1))
        judgement = judgements.get(track_id)
        if judgement is None:
            color, label = (255, 200, 0), f"#{track_id} CHECKING"
        else:
            raw, _decision, assessment = judgement
            color, label = COLORS.get(assessment, (255, 200, 0)), f"#{track_id} {assessment} ({raw})"
        cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)
        cv2.putText(image, label, (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    return image


def show(latest, judgements, live=None, overlay=None, on_key=None) -> bool:
    """Render a frame with the latest analysis; False when the operator pressed q/Esc.

    ``overlay(image)`` draws extra layers (route, boat). ``on_key(code)`` sees every key press.

    ``live``: the newest camera frame. When given, the video stays at camera rate and the
    boxes from the last finished analysis are drawn on it (they lag the object by the
    analysis age shown in the corner). Without it, only analysed frames are shown.
    """
    frame, tracks = latest if latest is not None else (None, [])
    base = live if live is not None else frame
    if base is not None:
        image = draw_tracks(base.image.copy(), tracks, dict(judgements))
        if live is not None:
            age = (live.monotonic - frame.monotonic) * 1000 if frame is not None else None
            text = "analysis: waiting" if age is None else f"analysis age {age:.0f} ms"
            cv2.putText(image, text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        if overlay is not None:
            overlay(image)
        cv2.imshow(WINDOW, image)
    key = cv2.waitKey(30) & 0xFF
    if on_key is not None and key != 255:
        on_key(key)
    return key not in (ord("q"), ord("Q"), 27)


def close_windows() -> None:
    try:
        cv2.destroyAllWindows()
    except cv2.error:
        pass
