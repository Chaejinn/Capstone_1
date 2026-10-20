"""GET /api/events, /api/events/{id}/frames — FR-MON-004."""
import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..services import event_repository

router = APIRouter(prefix="/api/mission", tags=["events"])


@router.get("/events", response_model=list[schemas.EventOut])
def list_events(
    from_: datetime.datetime | None = Query(default=None, alias="from"),
    to: datetime.datetime | None = None,
    db: Session = Depends(get_db),
):
    return event_repository.list_events(db, from_, to)


@router.get("/events/{event_id}/frames", response_model=list[schemas.EventFrameOut])
def get_event_frames(event_id: str, db: Session = Depends(get_db)):
    return event_repository.get_frames(db, event_id)
