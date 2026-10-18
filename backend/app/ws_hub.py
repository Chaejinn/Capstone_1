"""
WebSocketHub — class_srv.puml의 api/monitor 패키지.
단일 엔드포인트(/ws)에 연결된 모든 관제/관리자 단말에 토픽 기반으로 브로드캐스트한다.
동시 접속 3대 가정 (§2.4.1).
"""
import datetime
import json
from typing import List

from fastapi import WebSocket


class WebSocketHub:
    def __init__(self):
        self._clients: List[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._clients:
            self._clients.remove(ws)

    async def broadcast(self, topic: str, payload: dict):
        message = {
            "topic": topic,
            "ts": datetime.datetime.utcnow().isoformat() + "Z",
            "payload": payload,
        }
        text = json.dumps(message, ensure_ascii=False, default=str)
        dead = []
        for ws in self._clients:
            try:
                await ws.send_text(text)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = WebSocketHub()
