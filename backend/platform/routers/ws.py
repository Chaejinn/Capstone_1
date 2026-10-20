"""
관제 대시보드 실시간 푸시용 WebSocket.
연결: ws://<host>/ws/{site_id}?token=<JWT>
인증: 쿼리 파라미터로 JWT를 받는다 (브라우저 WebSocket API는 커스텀 헤더를 못 붙이므로).
"""
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from .. import models, security
from ..database import SessionLocal
from ..ws_manager import manager

router = APIRouter(tags=["ws"])


def _authenticate(token: str | None) -> models.User | None:
    if not token:
        return None
    payload = security.decode_access_token(token)
    if not payload:
        return None
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.username == payload.get("sub")).first()
        if user and user.active:
            return user
        return None
    finally:
        db.close()


@router.websocket("/ws/{site_id}")
async def site_ws(websocket: WebSocket, site_id: str, token: str | None = Query(default=None)):
    user = _authenticate(token)
    if not user:
        await websocket.close(code=4401)
        return

    await manager.connect(site_id, websocket)
    try:
        while True:
            # 대시보드는 보통 수신 전용이지만, 연결 유지를 위해 핑/퐁 메시지를 읽어만 둔다.
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(site_id, websocket)
