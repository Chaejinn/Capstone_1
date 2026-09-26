"""Pydantic 요청/응답 스키마.

VLM 인터페이스(§VLM_인터페이스_스키마.md)와 프론트-백엔드 이벤트 스키마
(§백엔드_프론트_이벤트_스키마.md)에서 정의한 필드명을 그대로 따른다.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------- Auth ----------------

class SignupRequest(BaseModel):
    username: str = Field(min_length=6, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=50)


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str
    name: str


class MeResponse(BaseModel):
    username: str
    name: str
    role: str


# ---------------- Users (admin) ----------------

class UserOut(BaseModel):
    id: int
    username: str
    name: str
    role: str
    active: bool

    class Config:
        from_attributes = True


class UserCreateByAdmin(BaseModel):
    username: str = Field(min_length=6, max_length=50)
    password: str = Field(min_length=8, max_length=128)
    name: str


class UserActiveUpdate(BaseModel):
    active: bool


# ---------------- Sites ----------------

class SiteOut(BaseModel):
    id: str
    name: str
    meta: str
    status: str
    enabled: bool

    class Config:
        from_attributes = True


class SiteEnabledUpdate(BaseModel):
    enabled: bool


class RoiPoint(BaseModel):
    x: float
    y: float


class RoiUpdate(BaseModel):
    points: List[RoiPoint]


# ---------------- Settings ----------------

class GlobalSettingsOut(BaseModel):
    thresh_conf: float
    thresh_frames: int


class GlobalSettingsUpdate(BaseModel):
    thresh_conf: float = Field(ge=0.5, le=0.99)
    thresh_frames: int = Field(ge=5, le=30)


# ---------------- Contacts ----------------

class ContactOut(BaseModel):
    id: int
    site_id: str
    name: str
    phone: str
    notify: bool

    class Config:
        from_attributes = True


class ContactCreate(BaseModel):
    site_id: str
    name: str
    phone: str = ""
    notify: bool = True


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    notify: Optional[bool] = None


# ---------------- Audit ----------------

class AuditOut(BaseModel):
    id: int
    timestamp: datetime
    actor: str
    action: str

    class Config:
        from_attributes = True


# ---------------- VLM 판정 인터페이스 (AI 모듈 → 서버) ----------------
# VLM_인터페이스_스키마.md §2 기준

class VLMClassificationResponse(BaseModel):
    request_id: str
    track_id: str
    site_id: str
    camera_id: str = "CAM-01"
    classification: Literal["normal_swimming", "abnormal", "drowning"]
    confidence: float = Field(ge=0.0, le=1.0)
    real_x_m: Optional[float] = None
    real_y_m: Optional[float] = None
    evidence_frame_indices: List[int] = []
    reasoning: Optional[str] = None
    model_name: str = "unknown"
    model_version: str = "unknown"
    inference_ms: Optional[int] = None
    error: Optional[dict] = None


class AckEventRequest(BaseModel):
    """FR-MON-007(제안): 관리자가 경보를 오탐/구조완료로 확인 종료."""
    off_reason: Literal["rescued", "false_alarm_ack", "track_lost"]


class EventOut(BaseModel):
    id: int
    site_id: str
    track_id: str
    state: str
    confidence: float
    real_x_m: Optional[float]
    real_y_m: Optional[float]
    dispatch_status: str
    off_reason: Optional[str]
    since: datetime
    ended_at: Optional[datetime]

    class Config:
        from_attributes = True


class DispatchStatusUpdate(BaseModel):
    """개입 계층(차유비 파트)이 진행 단계를 보고할 때 사용."""
    status: Literal["DISPATCHED", "EN_ROUTE", "ARRIVED", "DEPLOYING", "COMPLETED", "CANCELLED"]
    distance_remaining_m: Optional[float] = None


# ---------------- WebSocket 이벤트 봉투 ----------------
# 백엔드_프론트_이벤트_스키마.md §1 공통 봉투 구조

class WSEnvelope(BaseModel):
    type: Literal["PERSON_COUNT", "DROWNING_STATUS", "DISPATCH_COMMAND", "BOARD_TELEMETRY"]
    site_id: str
    timestamp: datetime
    payload: dict
