"""사이트 목록/ROI. 조회는 운영자+관리자, enabled·ROI 수정은 관리자 전용."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..audit import log as audit_log
from ..database import get_db
from ..deps import require_admin, require_operator_or_admin

router = APIRouter(prefix="/sites", tags=["sites"])


def _site_out(site: models.Site) -> schemas.SiteOut:
    return schemas.SiteOut(
        id=site.id, name=site.name, meta=site.meta, status=site.status, enabled=site.enabled
    )


@router.get("", response_model=list[schemas.SiteOut])
def list_sites(
    db: Session = Depends(get_db), user: models.User = Depends(require_operator_or_admin)
):
    return [_site_out(s) for s in db.query(models.Site).all()]


@router.get("/{site_id}/roi", response_model=schemas.RoiUpdate)
def get_roi(
    site_id: str, db: Session = Depends(get_db), user: models.User = Depends(require_operator_or_admin)
):
    site = db.query(models.Site).filter(models.Site.id == site_id).first()
    if not site:
        raise HTTPException(404, "사이트를 찾을 수 없습니다.")
    return schemas.RoiUpdate(points=site.roi())


@router.patch("/{site_id}/enabled", response_model=schemas.SiteOut)
def set_enabled(
    site_id: str,
    body: schemas.SiteEnabledUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    site = db.query(models.Site).filter(models.Site.id == site_id).first()
    if not site:
        raise HTTPException(404, "사이트를 찾을 수 없습니다.")
    site.enabled = body.enabled
    site.status = "운영중" if body.enabled else "준비중"
    db.commit()
    db.refresh(site)
    audit_log(db, actor=admin.username, action=f"사이트 {'활성화' if body.enabled else '비활성화'}: {site.name}")
    return _site_out(site)


@router.put("/{site_id}/roi", response_model=schemas.RoiUpdate)
def set_roi(
    site_id: str,
    body: schemas.RoiUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    """FR-SUR-002: 다각형 ROI 좌표(0~100 상대좌표) 저장."""
    site = db.query(models.Site).filter(models.Site.id == site_id).first()
    if not site:
        raise HTTPException(404, "사이트를 찾을 수 없습니다.")
    site.set_roi([p.model_dump() for p in body.points])
    db.commit()
    audit_log(db, actor=admin.username, action=f"ROI 수정: {site.name}")
    return schemas.RoiUpdate(points=site.roi())
