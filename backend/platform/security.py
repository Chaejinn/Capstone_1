"""비밀번호 해싱(bcrypt)과 JWT 발급/검증.

지난번 프론트엔드 전용 프로토타입에서 지적했던 A1 리스크(관리자 비밀번호가
JS 코드에 평문으로 노출)를 여기서 실제로 해소한다 — 비밀번호는 DB에 bcrypt
해시로만 저장되고, 인증은 서버가 발급한 JWT로 검증한다.
"""
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from . import config

# passlib의 CryptContext는 최신 bcrypt(>=4.1)와 버전 감지 방식이 어긋나는 알려진 호환성
# 문제가 있어(bcrypt.__about__ 제거됨), bcrypt 라이브러리를 직접 사용한다.
_BCRYPT_MAX_BYTES = 72


def hash_password(plain: str) -> str:
    raw = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    raw = plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(raw, hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, config.SECRET_KEY, algorithm=config.ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, config.SECRET_KEY, algorithms=[config.ALGORITHM])
    except JWTError:
        return None
