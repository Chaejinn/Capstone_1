"""감사 로그 조회/초기화. 관리자 전용(admin.html 감사 로그 탭)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import require_admin

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[schemas.AuditOut])
def list_audit(
    limit: int = 500,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    return (
        db.query(models.AuditLog)
        .order_by(models.AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )


@router.delete("")
def clear_audit(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    db.query(models.AuditLog).delete()
    db.commit()
    return {"ok": True}
