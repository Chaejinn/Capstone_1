from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from . import models, security
from .database import get_db

# tokenUrl은 문서화용 표기일 뿐, 실제 로그인은 /auth/login, /auth/admin-login 둘 다 사용 가능
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="인증이 필요합니다.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    payload = security.decode_access_token(token)
    if payload is None:
        raise credentials_exception
    username = payload.get("sub")
    if username is None:
        raise credentials_exception
    user = db.query(models.User).filter(models.User.username == username).first()
    if user is None or not user.active:
        raise credentials_exception
    return user


def require_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return user


def require_operator_or_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role not in ("operator", "admin"):
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    return user
