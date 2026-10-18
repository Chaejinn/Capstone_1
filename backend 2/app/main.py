"""
Drown Guardian 판단 서버 진입점 — deploy.puml의 "판단 서버" 노드 중 FastAPI app 부분.
카메라 1대·보드 1대 단일 배치를 전제하며, 로그인/사이트 개념은 두지 않는다
(팀 공식 설계서 v0.2 기준 — erd.puml, class_srv.puml, deploy.puml).
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, SessionLocal, engine
from .routers import ai_bridge, calibration, config_router, events, judgement, mission, status, ws
from .services import config_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        config_service.get_active_config(db)  # 없으면 기본 config_snapshot 시드
    finally:
        db.close()
    yield


app = FastAPI(title="Drown Guardian 판단 서버", version="0.2.0", lifespan=lifespan)

# 로컬 Wi-Fi AP 내부에서만 동작(NFR-ARC-001) — 대시보드가 다른 포트/오리진에서 서빙될 수 있어 개방.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(status.router)
app.include_router(config_router.router)
app.include_router(calibration.router)
app.include_router(events.router)
app.include_router(mission.router)
app.include_router(judgement.router)
app.include_router(ai_bridge.router)
app.include_router(ws.router)


@app.get("/health")
def health():
    return {"status": "ok"}
