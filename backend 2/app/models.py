"""
SQLAlchemy ORM 모델 — erd.puml을 그대로 따른다 (테이블명/필드명 1:1 대응).
로그인/사이트 개념은 팀 설계서에 없으므로 넣지 않는다 (카메라 1대·보드 1대 단일 배치 전제).
"""
import datetime
import json

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
)

from .database import Base


def now_utc():
    return datetime.datetime.utcnow()


class DrowningEvent(Base):
    __tablename__ = "drowning_event"

    event_id = Column(String(40), primary_key=True)  # 예: EVT-20261015-0003
    occurred_at = Column(DateTime, default=now_utc)
    track_id = Column(Integer)
    img_x = Column(Float, nullable=True)
    img_y = Column(Float, nullable=True)
    world_x = Column(Float, nullable=True)  # m
    world_y = Column(Float, nullable=True)  # m
    verdict = Column(String(20))            # normal_swimming | abnormal | drowning
    confidence = Column(Float)
    status = Column(String(20), default="DETECTED")  # DETECTED|DISPATCHED|CANCELLED|COMPLETED|ABORTED
    is_false_positive = Column(Boolean, default=False)
    model_version = Column(String(50), nullable=True)
    prompt_version = Column(String(50), nullable=True)
    config_version = Column(Integer, ForeignKey("config_snapshot.config_version"), nullable=True)
    latency_ms = Column(Integer, nullable=True)


class EventFrame(Base):
    __tablename__ = "event_frame"

    frame_id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(40), ForeignKey("drowning_event.event_id"), index=True)
    seq = Column(Integer)
    captured_at = Column(DateTime, default=now_utc)
    file_path = Column(String(300))
    masked = Column(Boolean, default=True)  # 항상 1 — PrivacyMasker를 거친 프레임만 저장 (NFR-SEC-001/002)


class Mission(Base):
    __tablename__ = "mission"

    mission_id = Column(Integer, primary_key=True, autoincrement=True)
    event_id = Column(String(40), ForeignKey("drowning_event.event_id"), nullable=True)
    trigger = Column(String(20))  # AUTO | CLICK_TARGET
    target_x = Column(Float, nullable=True)
    target_y = Column(Float, nullable=True)
    started_at = Column(DateTime, default=now_utc)
    ended_at = Column(DateTime, nullable=True)
    result = Column(String(20), nullable=True)       # COMPLETED|CANCELLED|ABORTED|FAILSAFE
    fail_reason = Column(String(200), nullable=True)
    retries = Column(Integer, default=0)
    # 시뮬레이션 진행 상태 표시용 (DB 영속 필드는 아니지만 보드 상태 조회 편의를 위해 저장)
    status = Column(String(20), default="NAVIGATING")


class EstopLog(Base):
    __tablename__ = "estop_log"

    estop_id = Column(Integer, primary_key=True, autoincrement=True)
    mission_id = Column(Integer, ForeignKey("mission.mission_id"), nullable=True)
    source = Column(String(20))  # DASHBOARD | PHYSICAL | FAILSAFE
    issued_at = Column(DateTime, default=now_utc)
    ack_at = Column(DateTime, nullable=True)
    latency_ms = Column(Integer, nullable=True)


class SystemAlert(Base):
    __tablename__ = "system_alert"

    alert_id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(30))   # COMM_LOST | LOW_LIGHT | LOW_BATTERY | ...
    level = Column(String(10), default="warn")  # info|warn|crit
    message = Column(String(300))
    raised_at = Column(DateTime, default=now_utc)
    cleared_at = Column(DateTime, nullable=True)


class ConfigSnapshot(Base):
    """ROI·판정 임계값 설정 — 바꿀 때마다 새 행(버전)을 만든다 (오탐 분석 시 추적용)."""
    __tablename__ = "config_snapshot"

    config_version = Column(Integer, primary_key=True, autoincrement=True)
    saved_at = Column(DateTime, default=now_utc)
    saved_by = Column(String(50), default="system")
    roi_polygon = Column(Text, default="[]")  # JSON [{x,y}, ...]
    conf_threshold = Column(Float, default=0.90)
    persist_frames = Column(Integer, default=15)
    window_n = Column(Integer, default=8)
    vlm_timeout_s = Column(Float, default=1.5)
    is_active = Column(Boolean, default=True)

    def roi(self):
        try:
            return json.loads(self.roi_polygon or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    def set_roi(self, points):
        self.roi_polygon = json.dumps(points, ensure_ascii=False)


class Calibration(Base):
    """호모그래피 캘리브레이션 (기준점 4점 → 3x3 변환행렬)."""
    __tablename__ = "calibration"

    calib_id = Column(Integer, primary_key=True, autoincrement=True)
    img_points = Column(Text)    # JSON 4점 [[x,y],...]
    world_points = Column(Text)  # JSON 4점(m) [[x,y],...]
    h_matrix = Column(Text)      # JSON 3x3
    reproj_error_m = Column(Float)
    created_at = Column(DateTime, default=now_utc)
    is_active = Column(Boolean, default=True)


class NotifyTarget(Base):
    """알림 대상 (E-04 감시 설정의 일부)."""
    __tablename__ = "notify_target"

    target_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50))
    client_id = Column(String(100))  # 브라우저 알림 구독 식별자 등
    priority = Column(Integer, default=1)
    enabled = Column(Boolean, default=True)
