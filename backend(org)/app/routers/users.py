"""관리자 전용 — 운영자 계정 관리 (admin.html 사용자 관리 탭)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import config, models, schemas, security
from ..audit import log as audit_log
from ..database import get_db
from ..deps import require_admin

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), admin: models.User = Depends(require_admin)):
    return db.query(models.User).order_by(models.User.created_at.desc()).all()


@router.post("", response_model=schemas.UserOut)
def create_user(
    body: schemas.UserCreateByAdmin,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    if body.username == config.ADMIN_ID:
        raise HTTPException(400, "사용할 수 없는 아이디입니다.")
    if db.query(models.User).filter(models.User.username == body.username).first():
        raise HTTPException(400, "이미 사용 중인 아이디입니다.")

    user = models.User(
        username=body.username,
        password_hash=security.hash_password(body.password),
        name=body.name,
        role="operator",
        active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit_log(db, actor=admin.username, action=f"운영자 계정 생성: {user.username}")
    return user


@router.patch("/{user_id}/active", response_model=schemas.UserOut)
def set_active(
    user_id: int,
    body: schemas.UserActiveUpdate,
    db: Session = Depends(get_db),
    admin: models.User = Depends(require_admin),
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "사용자를 찾을 수 없습니다.")
    if user.role == "admin":
        raise HTTPException(400, "관리자 계정은 변경할 수 없습니다.")
    user.active = body.active
    db.commit()
    db.refresh(user)
    audit_log(db, actor=admin.username, action=f"운영자 {'활성화' if body.active else '비활성화'}: {user.username}")
    return user


@router.delete("/{user_id}")
def delete_user(
    user_id: int, db: Session = Depends(get_db), admin: models.User = Depends(require_admin)
):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(404, "사용자를 찾을 수 없습니다.")
    if user.role == "admin":
        raise HTTPException(400, "관리자 계정은 삭제할 수 없습니다.")
    db.delete(user)
    db.commit()
    audit_log(db, actor=admin.username, action=f"운영자 삭제: {user.username}")
    return {"ok": True}
