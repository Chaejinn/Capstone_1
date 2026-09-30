"""
Drown Guardian 백엔드 진입점.
- 기존 프론트(js/auth.js, localStorage 기반)를 그대로 대체하도록 설계됨.
- 기동 시 테이블 생성 + 최소 시드(실제 관리자 계정 1개 + 사이트 4개 + 기본 임계값)만 넣는다.
  가짜 운영자 placeholder 계정(chacha/kyuryang/chaejin)은 의도적으로 시드하지 않는다.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config, models, security
from .database import Base, SessionLocal, engine
from .camera import camera as camera_device
from .routers import camera, audit, auth, contacts, events, settings, sites, users, ws

SEED_SITES = [
    {"id": "chunjeon", "name": "금오천 일대", "meta": "CAM-01 · BOARD-01 · 실내 수조 실증", "status": "운영중", "enabled": True},
    {"id": "river-b", "name": "낙동강 체육공원", "meta": "다중 노드 확장 · 범위 외 (후속 과제)", "status": "준비중", "enabled": False},
    {"id": "farm-c", "name": "금호강 낚시스팟", "meta": "확장 응용 · 범위 외 (후속 과제)", "status": "준비중", "enabled": False},
    {"id": "port-d", "name": "선산대교 밑 낚시스팟", "meta": "확장 응용 · 범위 외 (후속 과제)", "status": "준비중", "enabled": False},
]


def seed_db():
    db = SessionLocal()
    try:
        if not db.query(models.User).filter(models.User.username == config.ADMIN_ID).first():
            db.add(
                models.User(
                    username=config.ADMIN_ID,
                    password_hash=security.hash_password(config.ADMIN_PW),
                    name=config.ADMIN_NAME,
                    role="admin",
                    active=True,
                )
            )

        for s in SEED_SITES:
            if not db.query(models.Site).filter(models.Site.id == s["id"]).first():
                db.add(models.Site(**s))

        if not db.query(models.GlobalSettings).filter(models.GlobalSettings.id == 1).first():
            db.add(
                models.GlobalSettings(
                    id=1,
                    thresh_conf=config.DEFAULT_THRESH_CONF,
                    thresh_frames=config.DEFAULT_THRESH_FRAMES,
                )
            )

        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    seed_db()
    try:
        yield
    finally:
        camera_device.close()


app = FastAPI(title="Drown Guardian API", version="1.0.0", lifespan=lifespan)

# 프론트엔드가 별도 포트/오리진에서 서빙되는 개발 환경을 가정 — 필요 시 배포 도메인으로 좁힐 것.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(camera.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(sites.router)
app.include_router(settings.router)
app.include_router(contacts.router)
app.include_router(audit.router)
app.include_router(events.router)
app.include_router(ws.router)


@app.get("/health")
def health():
    return {"status": "ok"}
