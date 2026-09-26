"""
VLM 판정 결과 수신 + N프레임 누적/임계값 판정(FR-JDG-003/004) + 출동 명령/대시보드 푸시.

판정 철학(VLM_인터페이스_스키마.md): VLM 오류나 불충분한 정보는 절대로 자동으로
'정상'이나 '익수'로 확정하지 않는다 — 카운터를 유지한 채 판단을 보류한다.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..audit import log as audit_log
from ..database import get_db
from ..deps import require_admin, require_operator_or_admin
from ..routers.settings import _get_or_create as get_settings_row
from ..ws_manager import manager

router = APIRouter(tags=["events"])

# track_id별 연속 'drowning' 판정 누적 카운터 (프로세스 메모리 — 재시작 시 초기화됨).
_consecutive_drowning: dict[str, int] = {}


def _active_event(db: Session, track_id: str) -> models.Event | None:
    return (
        db.query(models.Event)
        .filter(models.Event.track_id == track_id, models.Event.state == "ON")
        .order_by(models.Event.id.desc())
        .first()
    )


@router.post("/vlm/classification", response_model=schemas.EventOut | None)
async def ingest_vlm_classification(
    body: schemas.VLMClassificationResponse, db: Session = Depends(get_db)
):
    """AI 추론 모듈(VLM)이 판정 결과를 이 엔드포인트로 POST한다.
    인증은 별도 서비스 토큰으로 분리하는 것이 이상적이나, 1차 구현에서는
    로컬 네트워크 내부 호출만 가정하고 개방해 둔다 (NFR-ARC-001 참고)."""

    settings_row = get_settings_row(db)
    track_id = body.track_id

    # VLM이 오류를 보고한 경우 — 자동으로 정상/익수를 확정하지 않고 그대로 보류.
    if body.error:
        return None

    if body.classification == "drowning" and body.confidence >= settings_row.thresh_conf:
        count = _consecutive_drowning.get(track_id, 0) + 1
        _consecutive_drowning[track_id] = count

        if count >= settings_row.thresh_frames and not _active_event(db, track_id):
            event = models.Event(
                site_id=body.site_id,
                track_id=track_id,
                state="ON",
                confidence=body.confidence,
                real_x_m=body.real_x_m,
                real_y_m=body.real_y_m,
                dispatch_status="DISPATCHED",
            )
            import json as _json

            event.evidence_frame_indices = _json.dumps(body.evidence_frame_indices)
            db.add(event)
            db.commit()
            db.refresh(event)

            audit_log(db, actor="system", action=f"익수 감지: track={track_id} site={body.site_id}")

            await manager.broadcast(
                body.site_id,
                "DROWNING_STATUS",
                {
                    "state": "ON",
                    "track_id": track_id,
                    "confidence": body.confidence,
                    "real_coords": {"x": body.real_x_m, "y": body.real_y_m},
                    "since": event.since.isoformat() + "Z",
                    "evidence_frame_indices": body.evidence_frame_indices,
                },
            )
            await manager.broadcast(
                body.site_id,
                "DISPATCH_COMMAND",
                {
                    "board_id": "BOARD-01",
                    "target_track_id": track_id,
                    "status": "DISPATCHED",
                    "target_coords": {"x": body.real_x_m, "y": body.real_y_m},
                    "dispatched_at": event.since.isoformat() + "Z",
                },
            )
            return event
    else:
        # normal_swimming 이거나 confidence 미달 — 누적 카운터 리셋 (FR-JDG-003).
        # 단, 'abnormal'은 완전한 정상도 익수도 아니므로 카운터를 건드리지 않고 보류.
        if body.classification == "normal_swimming":
            _consecutive_drowning[track_id] = 0

    return None


@router.get("/events", response_model=list[schemas.EventOut])
def list_events(
    site_id: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_operator_or_admin),
):
    q = db.query(models.Event)
    if site_id:
        q = q.filter(models.Event.site_id == site_id)
    if state:
        q = q.filter(models.Event.state == state)
    return q.order_by(models.Event.id.desc()).limit(200).all()


@router.post("/events/{event_id}/ack", response_model=schemas.EventOut)
async def ack_event(
    event_id: int,
    body: schemas.AckEventRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_operator_or_admin),
):
    """운영자/관리자가 경보를 구조완료/오탐/추적유실로 종료 처리 (FR-MON-007, 제안)."""
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "이벤트를 찾을 수 없습니다.")

    import datetime

    event.state = "OFF"
    event.off_reason = body.off_reason
    event.ended_at = datetime.datetime.utcnow()
    event.dispatch_status = "COMPLETED" if body.off_reason == "rescued" else "CANCELLED"
    db.commit()
    db.refresh(event)

    _consecutive_drowning.pop(event.track_id, None)
    audit_log(db, actor=user.username, action=f"이벤트 종료({body.off_reason}): track={event.track_id}")

    await manager.broadcast(
        event.site_id,
        "DROWNING_STATUS",
        {
            "state": "OFF",
            "track_id": event.track_id,
            "off_reason": event.off_reason,
            "duration_sec": (event.ended_at - event.since).total_seconds(),
        },
    )
    await manager.broadcast(
        event.site_id,
        "DISPATCH_COMMAND",
        {
            "board_id": "BOARD-01",
            "target_track_id": event.track_id,
            "status": event.dispatch_status,
        },
    )
    return event


@router.patch("/events/{event_id}/dispatch", response_model=schemas.EventOut)
async def update_dispatch_status(
    event_id: int,
    body: schemas.DispatchStatusUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """개입 계층(보드)이 출동 진행 단계를 보고 — DISPATCHED→EN_ROUTE→ARRIVED→DEPLOYING→COMPLETED."""
    event = db.query(models.Event).filter(models.Event.id == event_id).first()
    if not event:
        raise HTTPException(404, "이벤트를 찾을 수 없습니다.")

    event.dispatch_status = body.status
    db.commit()
    db.refresh(event)

    await manager.broadcast(
        event.site_id,
        "DISPATCH_COMMAND",
        {
            "board_id": "BOARD-01",
            "target_track_id": event.track_id,
            "status": body.status,
            "distance_remaining_m": body.distance_remaining_m,
        },
    )
    return event


@router.post("/board/estop")
async def trigger_estop(
    site_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_operator_or_admin),
):
    """비상정지 (유일하게 남은 수동 개입 — FR-SAF-005/NFR-SAF-001)."""
    audit_log(db, actor=user.username, action=f"비상정지 발동: site={site_id}")
    await manager.broadcast(
        site_id, "BOARD_TELEMETRY", {"board_id": "BOARD-01", "mode": "ESTOP", "comm_status": "OK"}
    )
    return {"ok": True}


@router.post("/board/estop/clear")
async def clear_estop(
    site_id: str,
    db: Session = Depends(get_db),
    user: models.User = Depends(require_operator_or_admin),
):
    audit_log(db, actor=user.username, action=f"비상정지 해제: site={site_id}")
    await manager.broadcast(
        site_id, "BOARD_TELEMETRY", {"board_id": "BOARD-01", "mode": "AUTO", "comm_status": "OK"}
    )
    return {"ok": True}
