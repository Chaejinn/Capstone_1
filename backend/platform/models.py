"""
SQLAlchemy ORM 모델.
프론트엔드(js/auth.js)의 localStorage 스키마(dg_users/dg_sites/dg_global_settings/dg_audit)와
필드명을 최대한 맞춰서, 이 백엔드가 그 프론트를 그대로 대체할 수 있게 했다.
"""
import datetime
import json

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
)
from sqlalchemy.orm import relationship

from .database import Base


def now_utc():
    return datetime.datetime.utcnow()


class User(Base):
    """운영자/관리자 계정. FR-SEC-004(제안) — 관제 대시보드 인증·권한 분리."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(50), nullable=False)
    role = Column(String(20), nullable=False, default="operator")  # 'operator' | 'admin'
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=now_utc)


class Site(Base):
    """감시 사이트. 관제 대시보드 사이트 선택 화면과 1:1 대응."""
    __tablename__ = "sites"

    id = Column(String(30), primary_key=True)  # 예: 'chunjeon'
    name = Column(String(100), nullable=False)
    meta = Column(String(200), default="")
    status = Column(String(20), default="준비중")  # '운영중' | '준비중'
    enabled = Column(Boolean, default=False)
    # FR-SUR-002: 감시 ROI 다각형 좌표 (JSON 문자열로 저장 — [{x,y}, ...], 0~100 상대좌표)
    roi_json = Column(Text, default="[]")

    def roi(self):
        try:
            return json.loads(self.roi_json or "[]")
        except (json.JSONDecodeError, TypeError):
            return []

    def set_roi(self, points):
        self.roi_json = json.dumps(points, ensure_ascii=False)


class GlobalSettings(Base):
    """전역 판정 임계값 (FR-JDG-004). 싱글턴 — id=1 행 하나만 사용."""
    __tablename__ = "global_settings"

    id = Column(Integer, primary_key=True, default=1)
    thresh_conf = Column(Float, default=0.90)
    thresh_frames = Column(Integer, default=15)


class AuditLog(Base):
    """관리자 조작 감사 로그 (FR-MON-006, 제안 항목)."""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=now_utc, index=True)
    actor = Column(String(50), default="system")
    action = Column(String(300), nullable=False)


class Contact(Base):
    """알림 대상 (관제 대시보드 설정 화면)."""
    __tablename__ = "contacts"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(String(30), ForeignKey("sites.id"), index=True)
    name = Column(String(50), nullable=False)
    phone = Column(String(30), default="")
    notify = Column(Boolean, default=True)


class Event(Base):
    """
    익수 이벤트 로그 (FR-JDG-005, FR-MON-005).
    VLM 판정 결과를 서버가 수신해 N프레임 누적·임계값 비교(FR-JDG-003/004) 후
    이 테이블에 기록하고, 상태 변화를 WebSocket으로 관제 대시보드에 푸시한다.
    """
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    site_id = Column(String(30), ForeignKey("sites.id"), index=True)
    track_id = Column(String(50), index=True)

    state = Column(String(10), default="ON")  # 'ON' | 'OFF'
    confidence = Column(Float, default=0.0)
    real_x_m = Column(Float, nullable=True)
    real_y_m = Column(Float, nullable=True)

    dispatch_status = Column(
        String(20), default="DISPATCHED"
    )  # DISPATCHED/EN_ROUTE/ARRIVED/DEPLOYING/COMPLETED/CANCELLED
    off_reason = Column(String(30), nullable=True)  # rescued/false_alarm_ack/track_lost
    evidence_frame_indices = Column(Text, default="[]")  # JSON 배열

    since = Column(DateTime, default=now_utc)
    ended_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now_utc)

    def evidence(self):
        try:
            return json.loads(self.evidence_frame_indices or "[]")
        except (json.JSONDecodeError, TypeError):
            return []
