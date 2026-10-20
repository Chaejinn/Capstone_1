"""
사이트별 WebSocket 연결 관리 + 이벤트 브로드캐스트.
백엔드_프론트_이벤트_스키마.md §1 공통 봉투: {type, site_id, timestamp, payload}
"""
import datetime
import json
from typing import Dict, List

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, site_id: str, ws: WebSocket):
        await ws.accept()
        self._connections.setdefault(site_id, []).append(ws)

    def disconnect(self, site_id: str, ws: WebSocket):
        conns = self._connections.get(site_id, [])
        if ws in conns:
            conns.remove(ws)

    async def broadcast(self, site_id: str, msg_type: str, payload: dict):
        envelope = {
            "type": msg_type,
            "site_id": site_id,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "payload": payload,
        }
        dead = []
        for ws in self._connections.get(site_id, []):
            try:
                await ws.send_text(json.dumps(envelope, ensure_ascii=False, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(site_id, ws)


manager = ConnectionManager()
