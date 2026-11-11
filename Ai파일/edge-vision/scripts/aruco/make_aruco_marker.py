"""Printable ArUco marker on an A4 page (PNG + PDF), exact physical size at 100 % print.

    venv\\Scripts\\python.exe scripts/aruco/make_aruco_marker.py                 # 5 cm (standin) + 10 cm (boat)
    venv\\Scripts\\python.exe scripts/aruco/make_aruco_marker.py --size-cm 7.5 --id 3

--size-cm is the side of the BLACK square (the marker itself, border included). The white
quiet zone of --margin-cells cells (cell = side / (bits + 2)) surrounds it; never trim it.
"UP" is printed OUTSIDE the marker and the quiet zone, above the top edge: the top edge is
the bow direction used by BoardLocator. Nothing is drawn on the marker.
A 5 cm ruler with 1 cm ticks is on the same page: print at 100 % ("actual size", no "fit to
page") and check the black square and the ruler with a real ruler.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

A4_M = (0.210, 0.297)
DEFAULT_SIZES = ((5.0, "standin"), (10.0, "boat"))


def render(dictionary_name, marker_id, size_cm, *, margin_cells=1, dpi=300, purpose=""):
    """A4 page image (PIL, grayscale) and the marker's pixel box (left, top, side)."""
    import cv2
    from PIL import Image, ImageDraw, ImageFont

    if margin_cells < 1:
        raise ValueError("--margin-cells must be >= 1 (ArUco needs a white quiet zone)")
    aruco = cv2.aruco
    if not hasattr(aruco, dictionary_name):
        raise ValueError(f"unknown dictionary {dictionary_name}")
    dictionary = aruco.getPredefinedDictionary(getattr(aruco, dictionary_name))
    if not 0 <= marker_id < len(dictionary.bytesList):
        raise ValueError(f"--id must be in [0, {len(dictionary.bytesList)}) for {dictionary_name}")
    px_per_m = dpi / 0.0254
    page_w, page_h = (round(v * px_per_m) for v in A4_M)
    side = round(size_cm / 100 * px_per_m)
    cell = side / (dictionary.markerSize + 2)
    quiet = round(margin_cells * cell)
    if side + 2 * quiet > page_w - round(0.02 * px_per_m):
        raise ValueError(f"{size_cm} cm marker + margin does not fit on A4")
    marker = aruco.generateImageMarker(dictionary, marker_id, side)

    page = Image.new("L", (page_w, page_h), 255)
    left = (page_w - side) // 2
    top = round(0.06 * px_per_m)
    page.paste(Image.fromarray(marker), (left, top))
    draw = ImageDraw.Draw(page)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/malgun.ttf", round(0.005 * px_per_m))
        big = ImageFont.truetype("C:/Windows/Fonts/malgunbd.ttf", round(0.012 * px_per_m))
    except OSError:
        font = big = ImageFont.load_default()

    def centered(text, y, f=font):
        box = draw.textbbox((0, 0), text, font=f)
        draw.text(((page_w - (box[2] - box[0])) // 2, y), text, fill=0, font=f)
        return y + (box[3] - box[1])

    # "UP" above the quiet zone (outside the marker)
    up_bottom = top - quiet - round(0.004 * px_per_m)
    box = draw.textbbox((0, 0), "▲ UP", font=big)
    draw.text(((page_w - (box[2] - box[0])) // 2, up_bottom - (box[3] - box[1]) - box[1]), "▲ UP", fill=0, font=big)
    # light guide showing the quiet-zone boundary (outside the marker, dotted corners only)
    q0, q1 = (left - quiet, top - quiet), (left + side + quiet, top + side + quiet)
    tick = round(0.004 * px_per_m)
    for (x, y), (dx, dy) in (((q0[0], q0[1]), (1, 1)), ((q1[0], q0[1]), (-1, 1)),
                             ((q0[0], q1[1]), (1, -1)), ((q1[0], q1[1]), (-1, -1))):
        draw.line((x, y, x + dx * tick, y), fill=160, width=2)
        draw.line((x, y, x, y + dy * tick), fill=160, width=2)
    # 5 cm ruler with 1 cm ticks
    y = q1[1] + round(0.012 * px_per_m)
    cm = px_per_m / 100
    x0 = round((page_w - 5 * cm) / 2)
    thick = max(3, dpi // 75)
    draw.rectangle((x0, y, round(x0 + 5 * cm), y + thick), fill=0)
    for k in range(6):
        x = round(x0 + k * cm)
        draw.rectangle((x - thick // 2, y - round(0.003 * px_per_m), x + thick // 2, y + thick), fill=0)
        draw.text((x - round(0.001 * px_per_m), y + round(0.002 * px_per_m)), str(k), fill=0, font=font)
    y = centered("5 cm 눈금자 (1 cm 간격)", y + round(0.009 * px_per_m)) + round(0.006 * px_per_m)
    y = centered(f"{dictionary_name}   ID {marker_id}   검은 사각형 한 변 {size_cm:g} cm"
                 + (f"   ({purpose})" if purpose else ""), y) + round(0.004 * px_per_m)
    y = centered("A4, 100%(실제 크기)로 인쇄 - '페이지에 맞춤' 끄기. 흰 여백을 자르지 말 것", y) + round(0.004 * px_per_m)
    centered("UP(위쪽 변)이 보트 선수를 향하게, 평평하게 부착", y)
    return page, (left, top, side)


def write(page, out_dir: Path, stem: str, dpi: int):
    out_dir.mkdir(parents=True, exist_ok=True)
    png, pdf = out_dir / f"{stem}.png", out_dir / f"{stem}.pdf"
    page.save(png, dpi=(dpi, dpi))
    page.convert("RGB").save(pdf, resolution=dpi)
    return png, pdf


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dict", default="DICT_4X4_50", dest="dictionary")
    p.add_argument("--id", type=int, default=0)
    p.add_argument("--size-cm", type=float, help="black-square side; default: both 5 (standin) and 10 (boat)")
    p.add_argument("--margin-cells", type=int, default=1, help="white quiet zone in marker cells (>= 1)")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--out", type=Path, default=ROOT / "outputs/aruco")
    args = p.parse_args()
    sizes = [(args.size_cm, "")] if args.size_cm else list(DEFAULT_SIZES)
    for size, purpose in sizes:
        try:
            page, _ = render(args.dictionary, args.id, size, margin_cells=args.margin_cells, dpi=args.dpi,
                             purpose=purpose)
        except ValueError as exc:
            sys.exit(f"오류: {exc}")
        stem = f"aruco_{args.dictionary}_id{args.id}_{size:g}cm" + (f"_{purpose}" if purpose else "")
        png, pdf = write(page, args.out, stem, args.dpi)
        print(f"저장: {pdf}\n      {png}")
    print("인쇄: A4, 100%(실제 크기). 검은 사각형 한 변과 5 cm 눈금자를 자로 재서 확인하고, "
          "다르면 configs/aruco.yaml의 marker_length_m을 실제 길이로 바꾸세요.")


if __name__ == "__main__":
    main()
