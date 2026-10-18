"""
DispatchManager — class_srv.puml "dispatch" 패키지 (SD-02 흐름).

AI 파이프라인(TemporalAggregator)이 아직 없으므로, 이미 N프레임 누적 판정을 마친
JudgementResult가 들어온다고 가정하고 받는다 (routers/judgement.py의 개발용 주입 엔드포인트 참고).
"""
import datetime

from sqlalchemy.orm import Session

from .. import config, homography, models, schemas
from ..services import alert_service, config_service, event_repository
from .guidance_controller import guidance_controller


class DispatchManager:
    CANCEL_GRACE_SEC = config.CANCEL_GRACE_SEC

    def __init__(self):
        self.active_event_id: str | None = None

    def has_active_event(self) -> bool:
        return self.active_event_id is not None

    async def on_judgement(self, db: Session, result: schemas.JudgementResultIn) -> models.DrowningEvent | None:
        active_config = config_service.get_active_config(db)

        if result.verdict != "drowning" or result.confidence < active_config.conf_threshold:
            return None  # 정상/이상 또는 임계값 미달 — 출동하지 않음 (판단 보류/정상 처리는 AI 계층 몫)

        if self.has_active_event():
            # EX-13: 다중 익수 시 신뢰도 최상위 1인만 표적으로 삼고 나머지는 경보만.
            await alert_service.warn(
                db, "MULTI_TARGET",
                f"이미 출동 중 — track {result.track_id} 추가 감지는 경보만 발행 (EX-13)",
                level="info",
            )
            return None

        # 실좌표 변환 (호모그래피 캘리브레이션이 없으면 이미지 좌표를 그대로 사용 — 개발 단계 임시값)
        calib = config_service.get_active_calibration(db)
        if calib:
            import json
            import numpy as np
            H = np.array(json.loads(calib.h_matrix))
            world_x, world_y = homography.to_world(H, result.img_x, result.img_y)
        else:
            world_x, world_y = result.img_x, result.img_y

        event = models.DrowningEvent(
            event_id=event_repository.new_event_id(db),
            track_id=result.track_id,
            img_x=result.img_x, img_y=result.img_y,
            world_x=world_x, world_y=world_y,
            verdict=result.verdict,
            confidence=result.confidence,
            status="DISPATCHED",
            model_version=result.model_version,
            prompt_version=result.prompt_version,
            config_version=active_config.config_version,
            latency_ms=result.latency_ms,
        )
        event_repository.save(db, event)
        # PrivacyMasker를 거친 근거 프레임 — 실제 파이프라인 연결 전까지는 자리표시자만 기록
        event_repository.mask_and_save_frames(db, event.event_id, [])

        mission = models.Mission(
            event_id=event.event_id, trigger="AUTO",
            target_x=world_x, target_y=world_y, status="NAVIGATING",
        )
        db.add(mission)
        db.commit()
        db.refresh(mission)

        self.active_event_id = event.event_id

        await alert_service.raise_alarm(db, event)
        guidance_controller.start(mission.mission_id, world_x, world_y)
        return event

    async def click_target(self, db: Session, target_x: float, target_y: float) -> models.Mission:
        """E-03: 관리자가 화면을 클릭해 수동으로 출동 지점을 지정."""
        mission = models.Mission(
            event_id=None, trigger="CLICK_TARGET",
            target_x=target_x, target_y=target_y, status="NAVIGATING",
        )
        db.add(mission)
        db.commit()
        db.refresh(mission)
        guidance_controller.start(mission.mission_id, target_x, target_y)
        return mission

    async def cancel(self, db: Session, event_id: str, by: str) -> bool:
        """EX-12: 발행 후 CANCEL_GRACE_SEC 이내 출동 취소."""
        event = db.query(models.DrowningEvent).filter(models.DrowningEvent.event_id == event_id).first()
        if not event or event.status != "DISPATCHED":
            return False

        elapsed = (datetime.datetime.utcnow() - event.occurred_at).total_seconds()
        if elapsed > self.CANCEL_GRACE_SEC:
            return False

        guidance_controller.request_cancel()
        event.status = "CANCELLED"
        event.is_false_positive = True
        db.commit()

        self.active_event_id = None
        await alert_service.event_cancelled(event_id)
        return True

    def clear_active(self):
        self.active_event_id = None


dispatch_manager = DispatchManager()
