"""AlertService — class_srv.puml "api/monitor" 패키지."""
from sqlalchemy.orm import Session

from .. import models
from ..ws_hub import hub


async def raise_alarm(db: Session, event: "models.DrowningEvent"):
    """익수 경보 — SD-02: broadcast('alarm', 요약정보) + 화면 자동 전환."""
    await hub.broadcast("alarm", {
        "event_id": event.event_id,
        "track_id": event.track_id,
        "world_x": event.world_x,
        "world_y": event.world_y,
        "confidence": event.confidence,
        "occurred_at": event.occurred_at.isoformat() + "Z",
    })


async def event_cancelled(event_id: str):
    await hub.broadcast("event_cancelled", {"event_id": event_id})


async def warn(db: Session, alert_type: str, message: str, level: str = "warn") -> models.SystemAlert:
    row = models.SystemAlert(type=alert_type, level=level, message=message)
    db.add(row)
    db.commit()
    db.refresh(row)
    await hub.broadcast("alert", {
        "alert_id": row.alert_id, "type": row.type, "level": row.level,
        "message": row.message, "state": "raised",
    })
    return row


async def clear(db: Session, alert_type: str):
    import datetime
    row = (
        db.query(models.SystemAlert)
        .filter(models.SystemAlert.type == alert_type, models.SystemAlert.cleared_at.is_(None))
        .order_by(models.SystemAlert.alert_id.desc())
        .first()
    )
    if row:
        row.cleared_at = datetime.datetime.utcnow()
        db.commit()
    await hub.broadcast("alert", {"type": alert_type, "state": "cleared"})
