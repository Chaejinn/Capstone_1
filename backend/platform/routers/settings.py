"""전역 판정 임계값 (FR-JDG-004). 조회는 운영자+관리자, 수정은 관리자 전용."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import models, schemas
from ..audit import log as audit_log
from ..database import get_db
from ..deps import require_admin, require_operator_or_admin

router = APIRouter(prefix="/settings", tags=["settings"])


def _get_or_create(db: Session) -> models.GlobalSettings:
    row = db.query(models.GlobalSettings).filter(models.GlobalSettings.id == 1).first()
    if not row:
        from .. import config

        row = models.GlobalSettings(
            id=1, thresh_conf=config.DEFAULT_THRESH_CONF, thresh_frames=config.DEFAULT_THRESH_FRAMES
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("", response_model=schemas.GlobalSettingsOut)
def get_settings(
    db: Session = Depends(get_db), user: models.User = Depends(require_operator_or_admin)
):
    row = _get_or_create(db)
    return schemas.GlobalSettingsOut(thresh_conf=row.thresh_conf, thresh_frames=row.thresh_frames)


@router.put("", response_model=schemas.GlobalSettingsOut)
def update_settings(
    body: schemas.GlobalSettingsUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    row = _get_or_create(db)
    row.thresh_conf = body.thresh_conf
    row.thresh_frames = body.thresh_frames
    db.commit()
    audit_log(
        db, actor=admin.username,
        action=f"임계값 변경: conf={body.thresh_conf}, frames={body.thresh_frames}",
    )
    return schemas.GlobalSettingsOut(thresh_conf=row.thresh_conf, thresh_frames=row.thresh_frames)
