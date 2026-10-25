"""Small authenticated HTTP contract for a bridge and foreground phone receiver."""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_operator_or_admin
from ..models import TestSignal

router = APIRouter(prefix="/test-signals", tags=["test-signals"],
                   dependencies=[Depends(require_operator_or_admin)])


class SignalInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    source: str = Field(default="bridge", min_length=1, max_length=80)
    message: str = Field(default="임의 패킷 수신 테스트", min_length=1, max_length=500)


def serialize(signal):
    return {"id": signal.id, "source": signal.source, "message": signal.message,
            "created_at": signal.created_at.isoformat() + "Z", "test": True}


@router.post("", status_code=201)
def send_signal(body: SignalInput, db: Session = Depends(get_db)):
    signal = TestSignal(source=body.source, message=body.message)
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return serialize(signal)


@router.get("")
def receive_signals(after_id: int = Query(default=0, ge=0),
                    latest: bool = False, db: Session = Depends(get_db)):
    query = db.query(TestSignal)
    if latest:
        row = query.order_by(TestSignal.id.desc()).first()
        return {"signals": [], "cursor": row.id if row else 0}
    rows = query.filter(TestSignal.id > after_id).order_by(TestSignal.id).limit(100).all()
    return {"signals": [serialize(row) for row in rows],
            "cursor": rows[-1].id if rows else after_id}
