"""알림 대상 CRUD. 관리자 전용(admin.html 설정 화면)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..audit import log as audit_log
from ..database import get_db
from ..deps import require_admin

router = APIRouter(prefix="/contacts", tags=["contacts"])


@router.get("", response_model=list[schemas.ContactOut])
def list_contacts(
    site_id: str | None = None,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    q = db.query(models.Contact)
    if site_id:
        q = q.filter(models.Contact.site_id == site_id)
    return q.all()


@router.post("", response_model=schemas.ContactOut)
def create_contact(
    body: schemas.ContactCreate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    if not db.query(models.Site).filter(models.Site.id == body.site_id).first():
        raise HTTPException(404, "사이트를 찾을 수 없습니다.")
    contact = models.Contact(**body.model_dump())
    db.add(contact)
    db.commit()
    db.refresh(contact)
    audit_log(db, actor=admin.username, action=f"연락처 추가: {contact.name}")
    return contact


@router.patch("/{contact_id}", response_model=schemas.ContactOut)
def update_contact(
    contact_id: int,
    body: schemas.ContactUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(404, "연락처를 찾을 수 없습니다.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(contact, k, v)
    db.commit()
    db.refresh(contact)
    audit_log(db, actor=admin.username, action=f"연락처 수정: {contact.name}")
    return contact


@router.delete("/{contact_id}")
def delete_contact(
    contact_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)
):
    contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(404, "연락처를 찾을 수 없습니다.")
    db.delete(contact)
    db.commit()
    audit_log(db, actor=admin.username, action=f"연락처 삭제: {contact.name}")
    return {"ok": True}
