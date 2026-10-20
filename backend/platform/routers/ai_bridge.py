"""
AI 판정 서버(Modal /detect) ↔ 판단 서버(이 백엔드) 연결.

  POST /api/ai/health        AI 서버 가동 여부 확인
  POST /api/ai/detect-raw    이미지를 AI 서버로 보내고 원본 응답을 그대로 반환 (응답 형식 확인용)
  POST /api/ai/frame         이미지 → AI 판정 → JudgementResultIn으로 변환 → 출동 로직 실행

주의: /detect의 응답 스키마를 아직 확정받지 못해서 map_to_judgement()는 흔한 필드명을
넓게 허용하는 방식으로 짰다. 실제 응답을 보고 이 함수 한 곳만 고치면 된다.
"""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from .. import ai_client, schemas
from ..database import get_db
from ..dispatch.dispatch_manager import dispatch_manager

router = APIRouter(prefix="/ai", tags=["ai"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # AI 서버 제한 5 MiB


def _norm_verdict(label) -> str:
    s = str(label).lower()
    if "drown" in s:
        return "drowning"
    if "abnormal" in s or "anomal" in s or "distress" in s:
        return "abnormal"
    return "normal_swimming"


def _first(d: dict, keys, default=None):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def map_to_judgement(data: dict, frame_id: int | None) -> schemas.JudgementResultIn:
    """AI 서버 응답 → JudgementResultIn. 필드를 찾지 못하면 ValueError."""
    items = _first(data, ["detections", "results", "predictions", "people", "persons"])
    candidates = items if isinstance(items, list) and items else [data]

    best = None
    for it in candidates:
        if not isinstance(it, dict):
            continue
        label = _first(it, ["verdict", "classification", "label", "class", "status"])
        conf = _first(it, ["confidence", "score", "prob", "probability"])
        if label is None or conf is None:
            continue
        verdict = _norm_verdict(label)
        rank = (verdict == "drowning", float(conf))
        if best is None or rank > best[0]:
            best = (rank, it, verdict, float(conf))

    if best is None:
        raise ValueError("응답에서 판정(verdict/label)과 신뢰도(confidence/score)를 찾지 못했습니다.")

    _, it, verdict, conf = best
    bbox = _first(it, ["bbox", "box", "xyxy"])
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
        img_x, img_y = (x1 + x2) / 2, (y1 + y2) / 2
    else:
        img_x = float(_first(it, ["img_x", "x", "cx"], 0.0))
        img_y = float(_first(it, ["img_y", "y", "cy"], 0.0))

    return schemas.JudgementResultIn(
        track_id=int(_first(it, ["track_id", "id"], 0)),
        img_x=img_x, img_y=img_y,
        verdict=verdict, confidence=max(0.0, min(1.0, conf)),
        model_version=str(_first(data, ["model_version", "model"], "ai-server")),
        prompt_version=str(_first(data, ["prompt_version"], "ai-server")),
        latency_ms=int(_first(data, ["latency_ms", "inference_ms", "elapsed_ms"], 0)),
    )


async def _read_image(image: UploadFile) -> bytes:
    body = await image.read()
    if not body:
        raise HTTPException(400, "빈 이미지입니다.")
    if len(body) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "이미지는 5 MiB 이하여야 합니다.")
    return body


@router.post("/health")
async def ai_health():
    try:
        return await ai_client.health()
    except ai_client.AIClientError as e:
        raise HTTPException(502, str(e))
    except Exception as e:
        raise HTTPException(502, f"AI 서버 상태 확인 실패: {e}")


@router.post("/detect-raw")
async def detect_raw(image: UploadFile = File(...), frame_id: int | None = Form(default=None)):
    body = await _read_image(image)
    try:
        return await ai_client.detect(body, image.filename or "frame.jpg", image.content_type, frame_id)
    except ai_client.AIClientError as e:
        raise HTTPException(502, str(e))


@router.post("/frame")
async def process_frame(
    image: UploadFile = File(...),
    frame_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
):
    body = await _read_image(image)
    try:
        raw = await ai_client.detect(body, image.filename or "frame.jpg", image.content_type, frame_id)
    except ai_client.AIClientError as e:
        raise HTTPException(502, str(e))

    try:
        judgement = map_to_judgement(raw, frame_id)
    except (ValueError, TypeError) as e:
        # 판단 보류 원칙: 변환 실패를 정상/익수로 확정하지 않는다.
        raise HTTPException(422, {"message": f"AI 응답 변환 실패(판단 보류): {e}", "raw": raw})

    event = await dispatch_manager.on_judgement(db, judgement)
    return {
        "judgement": judgement.model_dump(),
        "dispatched": event is not None,
        "event_id": event.event_id if event else None,
    }
