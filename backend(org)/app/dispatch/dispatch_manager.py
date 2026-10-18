"""AI 브리지를 기존 누적 판정 및 출동 처리에 연결한다."""
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy.orm import Session

from .. import config, schemas
from ..routers.events import process_judgement


@dataclass
class DispatchResult:
    event_id: int


class DispatchManager:
    async def on_judgement(self, db: Session, judgement: schemas.JudgementResultIn):
        body = schemas.VLMClassificationResponse(
            request_id=str(uuid4()),
            track_id=str(judgement.track_id),
            site_id=config.CAMERA_SITE_ID,
            classification=judgement.verdict,
            confidence=judgement.confidence,
            model_version=judgement.model_version,
            inference_ms=judgement.latency_ms,
        )
        # 이미지 픽셀을 보드의 실세계 목표 좌표로 사용하지 않는다.
        event = await process_judgement(db, body)
        return DispatchResult(event.id) if event is not None else None


dispatch_manager = DispatchManager()
