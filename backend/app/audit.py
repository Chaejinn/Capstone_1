from sqlalchemy.orm import Session

from . import models


def log(db: Session, actor: str, action: str):
    """FR-MON-006(제안): 관리자 조작 감사 로그."""
    entry = models.AuditLog(actor=actor, action=action)
    db.add(entry)
    db.commit()
