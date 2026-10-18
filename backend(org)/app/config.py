"""
설정값 — 환경변수로 덮어쓸 수 있음.
NFR-ARC-001(엣지 추론, 외부 네트워크 없이 동작) 대응: 기본값만으로 완전히 로컬에서 기동 가능.
"""
import os

# JWT 서명 키. 배포 시 반드시 환경변수 DG_SECRET_KEY로 교체할 것.
SECRET_KEY = os.environ.get("DG_SECRET_KEY", "drown-guardian-dev-secret-CHANGE-ME")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.environ.get("DG_TOKEN_EXPIRE_MIN", "480"))  # 8시간

# SQLite (FR-MON-005: "SQLite (확장 시 PostgreSQL)")
DATABASE_URL = os.environ.get("DG_DATABASE_URL") or os.environ.get("POSTGRES_URL") or os.environ.get("DATABASE_URL") or "sqlite:///./drown_guardian.db"
if DATABASE_URL.startswith(("postgres://", "postgresql://")):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.split("://", 1)[1]
IS_VERCEL = os.environ.get("VERCEL") == "1"
CAMERA_ENABLED = os.environ.get("DG_CAMERA_ENABLED", "0" if IS_VERCEL else "1") == "1"
if IS_VERCEL and (DATABASE_URL.startswith("sqlite") or SECRET_KEY == "drown-guardian-dev-secret-CHANGE-ME"):
    raise RuntimeError("Vercel requires a persistent PostgreSQL database and DG_SECRET_KEY.")

# 고정 관리자 계정 (FR-SEC-004). 최초 기동 시 DB에 bcrypt 해시로 시딩됨 — 평문은 여기 최초 1회만 존재.
ADMIN_ID = os.environ.get("DG_ADMIN_ID", "capstone1")
ADMIN_PW = os.environ.get("DG_ADMIN_PW", "20262026")
ADMIN_NAME = "시스템 관리자"

# 판정 파이프라인 기본값 (FR-JDG-004 — 전역 기본 임계값)
DEFAULT_THRESH_CONF = 0.90
DEFAULT_THRESH_FRAMES = 15

# NFR-PER-001: 탐지-출동 응답 지연 목표 (경고 로그용, 강제 차단은 아님)
DISPATCH_LATENCY_TARGET_SEC = 3.0

# USB camera index or a server-configured MJPEG/RTSP URL. Never supplied by clients.
CAMERA_SOURCE = os.environ.get("DG_CAMERA_SOURCE", "0")
CAMERA_SITE_ID = os.environ.get("DG_CAMERA_SITE_ID", "chunjeon")
CAMERA_WIDTH = max(1, int(os.environ.get("DG_CAMERA_WIDTH", "1280")))
CAMERA_HEIGHT = max(1, int(os.environ.get("DG_CAMERA_HEIGHT", "720")))
CAMERA_FPS = max(1, min(60, int(os.environ.get("DG_CAMERA_FPS", "15"))))
CAMERA_JPEG_QUALITY = max(1, min(100, int(os.environ.get("DG_CAMERA_JPEG_QUALITY", "80"))))
CAMERA_TIMEOUT = max(1, float(os.environ.get("DG_CAMERA_TIMEOUT", "5")))
