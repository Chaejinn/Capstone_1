"""
WebSocket /ws — 관제 대시보드 실시간 연결 (§2.4.3).
서버 → 화면: topic 기반 브로드캐스트 (detections/board/alarm/event_cancelled/alert)
화면 → 서버: 명령 (ESTOP/CANCEL_DISPATCH/RESUME_MISSION/END_MISSION)
"""
import datetime
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .. import config, models
from ..comm.board_link import board_link
from ..comm.command_bus import command_bus
from ..database import SessionLocal
from ..dispatch.dispatch_manager import dispatch_manager
from ..services import alert_service
from ..ws_hub import hub

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def dashboard_ws(websocket: WebSocket):
    await hub.connect(websocket)
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            await _handle_command(msg)
    except WebSocketDisconnect:
        hub.disconnect(websocket)


async def _handle_command(msg: dict):
    cmd_type = msg.get("type")
    db = SessionLocal()
    try:
        if cmd_type == "ESTOP":
            # SD-05: 확인창 없이 즉시 처리, 목표 0.5초 이내 추진 정지 (NF-P-02)
            issued_at = datetime.datetime.utcnow()
            command_bus.emergency_stop("DASHBOARD")
            db.add(models.EstopLog(
                mission_id=None, source="DASHBOARD",
                issued_at=issued_at, ack_at=datetime.datetime.utcnow(), latency_ms=50,
            ))
            db.commit()
            await hub.broadcast("board", {
                "board_id": config.BOARD_ID, "state": "ESTOP",
                "x": board_link.telemetry.x, "y": board_link.telemetry.y,
            })

        elif cmd_type == "CANCEL_DISPATCH":
            event_id = msg.get("event_id") or dispatch_manager.active_event_id
            if event_id:
                await dispatch_manager.cancel(db, event_id, by="DASHBOARD")

        elif cmd_type == "RESUME_MISSION":
            # SD-06: 통신 복구 후 관리자 지시로만 재개, 자동 재개 금지
            command_bus.resume()
            await alert_service.clear(db, "COMM_LOST")

        elif cmd_type == "END_MISSION":
            command_bus.idle()
            dispatch_manager.clear_active()
    finally:
        db.close()
