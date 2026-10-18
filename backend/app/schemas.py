"""Pydantic 스키마 — 설계명세서 §2.4.2/2.4.3 메시지 규격을 그대로 따른다."""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel


# ---------------- status ----------------

class StatusOut(BaseModel):
    dispatch_in_progress: bool
    active_mission_id: Optional[int] = None


# ---------------- events (§2.4.3 REST) ----------------

class EventOut(BaseModel):
    event_id: str
    occurred_at: datetime
    track_id: Optional[int]
    img_x: Optional[float]
    img_y: Optional[float]
    world_x: Optional[float]
    world_y: Optional[float]
    verdict: Optional[str]
    confidence: Optional[float]
    status: str
    is_false_positive: bool
    model_version: Optional[str]
    prompt_version: Optional[str]
    config_version: Optional[int]
    latency_ms: Optional[int]

    class Config:
        from_attributes = True


class EventFrameOut(BaseModel):
    frame_id: int
    seq: int
    captured_at: datetime
    file_path: str
    masked: bool

    class Config:
        from_attributes = True


# ---------------- config: roi / judge / notify (E-04) ----------------

class RoiPoint(BaseModel):
    x: float
    y: float


class RoiUpdate(BaseModel):
    points: List[RoiPoint]


class RoiOut(BaseModel):
    config_version: int
    points: List[RoiPoint]


class JudgeConfigUpdate(BaseModel):
    conf_threshold: float
    persist_frames: int
    window_n: int
    vlm_timeout_s: float


class JudgeConfigOut(BaseModel):
    config_version: int
    conf_threshold: float
    persist_frames: int
    window_n: int
    vlm_timeout_s: float


class NotifyTargetOut(BaseModel):
    target_id: int
    name: str
    client_id: str
    priority: int
    enabled: bool

    class Config:
        from_attributes = True


class NotifyTargetCreate(BaseModel):
    name: str
    client_id: str
    priority: int = 1
    enabled: bool = True


class NotifyTargetUpdate(BaseModel):
    name: Optional[str] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


# ---------------- calibration (E-05) ----------------

class CalibrationRequest(BaseModel):
    img_points: List[List[float]]    # 4점 [[x,y],...] (이미지 픽셀)
    world_points: List[List[float]]  # 4점 [[x,y],...] (실좌표, m)


class CalibrationOut(BaseModel):
    calib_id: int
    h_matrix: List[List[float]]
    reproj_error_m: float
    accepted: bool
    reason: Optional[str] = None


# ---------------- mission / click-target (E-03) ----------------

class ClickTargetRequest(BaseModel):
    target_x: float  # m, 실좌표
    target_y: float


class MissionOut(BaseModel):
    mission_id: int
    event_id: Optional[str]
    trigger: str
    target_x: Optional[float]
    target_y: Optional[float]
    started_at: datetime
    ended_at: Optional[datetime]
    result: Optional[str]
    fail_reason: Optional[str]
    retries: int
    status: str

    class Config:
        from_attributes = True


# ---------------- judgement 수신 (AI 판단 파이프라인 → 서버, 내부용) ----------------
# 실제 배치에서는 같은 프로세스 안에서 TemporalAggregator.onJudgement()를 직접 호출하지만,
# AI 모듈이 아직 준비되지 않은 개발 단계에서는 이 REST 엔드포인트로 대체 입력한다.

class JudgementResultIn(BaseModel):
    track_id: int
    img_x: float
    img_y: float
    verdict: Literal["normal_swimming", "abnormal", "drowning"]
    confidence: float
    model_version: str = "dev-stub"
    prompt_version: str = "dev-stub"
    latency_ms: int = 0


# ---------------- WebSocket 메시지 (§2.4.3) ----------------

class WSMessage(BaseModel):
    topic: Literal["detections", "board", "alarm", "event_cancelled", "alert"]
    payload: dict


class WSCommand(BaseModel):
    type: Literal["ESTOP", "CANCEL_DISPATCH", "RESUME_MISSION", "END_MISSION"]
    event_id: Optional[str] = None
