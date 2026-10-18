"""
EventRepository — class_srv.puml "storage" 패키지.
디스크에 쓰는 경로는 여기 하나뿐이며, PrivacyMasker를 통과한 프레임만 저장한다 (NFR-SEC-001/002).
"""
import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from .. import models


def new_event_id(db: Session) -> str:
    today = datetime.datetime.utcnow().strftime("%Y%m%d")
    count_today = (
        db.query(models.DrowningEvent)
        .filter(models.DrowningEvent.event_id.like(f"EVT-{today}-%"))
        .count()
    )
    return f"EVT-{today}-{count_today + 1:04d}"


def save(db: Session, event: models.DrowningEvent) -> models.DrowningEvent:
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def mask_and_save_frames(db: Session, event_id: str, frame_paths: List[str]):
    """PrivacyMasker.mask()를 거쳤다고 가정한 프레임 경로만 event_frame에 기록한다.
    실제 카메라/추론 파이프라인이 없는 개발 단계에서는 플레이스홀더 경로를 그대로 기록한다."""
    for i, path in enumerate(frame_paths):
        db.add(models.EventFrame(
            event_id=event_id, seq=i, file_path=path, masked=True,
        ))
    db.commit()


def list_events(db: Session, dt_from: Optional[datetime.datetime], dt_to: Optional[datetime.datetime]):
    q = db.query(models.DrowningEvent)
    if dt_from:
        q = q.filter(models.DrowningEvent.occurred_at >= dt_from)
    if dt_to:
        q = q.filter(models.DrowningEvent.occurred_at <= dt_to)
    return q.order_by(models.DrowningEvent.occurred_at.desc()).all()


def get_frames(db: Session, event_id: str):
    return (
        db.query(models.EventFrame)
        .filter(models.EventFrame.event_id == event_id)
        .order_by(models.EventFrame.seq)
        .all()
    )


def purge_older_than(db: Session, days: int) -> int:
    """§2.1: 매일 1회 30일 지난 이벤트+프레임 삭제 (스케줄러에서 호출)."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    old_events = db.query(models.DrowningEvent).filter(models.DrowningEvent.occurred_at < cutoff).all()
    count = 0
    for ev in old_events:
        db.query(models.EventFrame).filter(models.EventFrame.event_id == ev.event_id).delete()
        db.delete(ev)
        count += 1
    db.commit()
    return count
