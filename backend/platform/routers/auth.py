"""
회원가입/로그인.
- 회원가입은 운영자(role='operator')만 가능 (관리자 회원가입 없음 — 사용자 결정 사항).
- 관리자 아이디로는 회원가입 불가 (username == config.ADMIN_ID 차단).
- 로그인은 운영자/관리자 공용 — 발급된 토큰의 role로 프론트가 화면을 분기.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import config, models, schemas, security
from ..audit import log as audit_log
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=schemas.TokenResponse)
def signup(body: schemas.SignupRequest, db: Session = Depends(get_db)):
    if body.username == config.ADMIN_ID:
        raise HTTPException(400, "사용할 수 없는 아이디입니다.")
    exists = db.query(models.User).filter(models.User.username == body.username).first()
    if exists:
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

    audit_log(db, actor=user.username, action="회원가입")

    token = security.create_access_token({"sub": user.username, "role": user.role})
    return schemas.TokenResponse(
        access_token=token, role=user.role, username=user.username, name=user.name
    )


@router.post("/login", response_model=schemas.TokenResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """OAuth2PasswordRequestForm 사용 → Swagger UI의 Authorize 버튼과 바로 호환.
    username/password 필드로 curl -d 'username=...&password=...' 형태로도 호출 가능."""
    user = db.query(models.User).filter(models.User.username == form.username).first()
    if not user or not security.verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다.")
    if not user.active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "비활성화된 계정입니다.")

    audit_log(db, actor=user.username, action="로그인")

    token = security.create_access_token({"sub": user.username, "role": user.role})
    return schemas.TokenResponse(
        access_token=token, role=user.role, username=user.username, name=user.name
    )


@router.get("/me", response_model=schemas.MeResponse)
def me(user: models.User = Depends(get_current_user)):
    return schemas.MeResponse(username=user.username, name=user.name, role=user.role)
