"""External AI observations, separate from temporal judgement and boat control."""
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import AliasChoices, BaseModel, Field, ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import require_operator_or_admin
from .vision import read_body

router = APIRouter(prefix="/edge", tags=["external AI observations"])


class Observation(BaseModel):
    event_id: str = Field(min_length=1, max_length=160,
                          validation_alias=AliasChoices("event_id", "request_id"))
    track_id: str | int
    site_id: str = Field(min_length=1, max_length=30)
    camera_id: str = Field(min_length=1, max_length=80)
    state: Literal["SWIMMING", "DROWNING", "UNCLEAR"] | None = None
    classification: Literal["normal_swimming", "abnormal", "drowning"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    confidence_source: str | None = Field(default=None, max_length=100)
    drowning_score: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    frame_id: int | None = Field(default=None, ge=1)
    captured_at: datetime | None = None
    sent_at: datetime | None = None
    model_name: str | None = Field(default=None, max_length=100)
    model_version: str | None = Field(default=None, max_length=100)


def service_identity(request: Request):
    key = os.environ.get("DG_EDGE_INGEST_KEY", "")
    site = os.environ.get("DG_EDGE_SITE_ID", "")
    camera = os.environ.get("DG_EDGE_CAMERA_ID", "")
    if len(key) < 32 or not site or not camera:
        raise HTTPException(503, "외부 AI 수신 키·사이트·카메라 설정이 필요합니다.")
    scheme, _, supplied = request.headers.get("authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(supplied.encode(), key.encode()):
        raise HTTPException(401, "외부 AI 서비스 인증에 실패했습니다.")
    return site, camera


def active_site(db, site_id):
    site = db.query(models.Site).filter(models.Site.id == site_id, models.Site.enabled.is_(True)).first()
    if site is None:
        raise HTTPException(403, "사용 가능한 사이트를 선택하세요.")


def receipt(row):
    return {"accepted": True, "observation_id": row.id,
            "received_at": row.created_at.isoformat() + "Z",
            "observation": json.loads(row.payload_json),
            "judgement_verified": False, "command_issued": False,
            "status": "OBSERVATION_ONLY"}


@router.post("/classification")
async def ingest(request: Request, identity=Depends(service_identity), db: Session = Depends(get_db)):
    raw = await read_body(request, 65536)
    try:
        observation = Observation.model_validate_json(raw)
    except ValidationError:
        raise HTTPException(422, "event_id/request_id, track_id, site_id, camera_id 및 올바른 판정 값이 필요합니다.") from None
    if (observation.site_id, observation.camera_id) != identity:
        raise HTTPException(403, "서비스에 허용된 사이트·카메라와 일치하지 않습니다.")
    active_site(db, observation.site_id)
    if observation.state is None and observation.classification is None:
        raise HTTPException(422, "state 또는 classification이 필요합니다.")
    mapping = {"normal_swimming": "SWIMMING", "drowning": "DROWNING", "abnormal": "UNCLEAR"}
    if observation.classification:
        expected = mapping[observation.classification]
        if observation.state is not None and observation.state != expected:
            raise HTTPException(422, "state와 classification이 일치하지 않습니다.")
        observation.state = expected
    if not str(observation.track_id).strip() or len(str(observation.track_id)) > 160:
        raise HTTPException(422, "올바른 track_id가 필요합니다.")
    now = datetime.now(timezone.utc)
    for name in ("captured_at", "sent_at"):
        timestamp = getattr(observation, name)
        if timestamp is not None:
            if timestamp.utcoffset() is None:
                raise HTTPException(422, name + "에는 시간대가 필요합니다.")
            age = (now - timestamp).total_seconds()
            if not -0.5 <= age <= 30:
                raise HTTPException(422, {"code": "INVALID_TIMESTAMP", "field": name,
                                         "observed_age_seconds": round(age, 3),
                                         "future_tolerance_seconds": 0.5, "max_age_seconds": 30,
                                         "server_time": now.isoformat()})
    payload = json.dumps(observation.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    event_key = hashlib.sha256(json.dumps([*identity, observation.event_id]).encode()).hexdigest()
    previous = db.query(models.EdgeJudgement).filter_by(event_key=event_key).first()
    if previous:
        if previous.payload_json != payload:
            raise HTTPException(409, "동일 event_id의 판정 내용이 변경되었습니다.")
        return receipt(previous)
    row = models.EdgeJudgement(event_key=event_key, site_id=observation.site_id,
                               camera_id=observation.camera_id, payload_json=payload)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.query(models.EdgeJudgement).filter_by(event_key=event_key).first()
        if row is None or row.payload_json != payload:
            raise HTTPException(409, "동일 event_id의 요청 충돌입니다.") from None
    db.refresh(row)
    return receipt(row)


@router.get("/latest")
def latest(site_id: str, camera_id: str, db: Session = Depends(get_db),
           user=Depends(require_operator_or_admin)):
    active_site(db, site_id)
    row = (db.query(models.EdgeJudgement).filter_by(site_id=site_id, camera_id=camera_id)
           .order_by(models.EdgeJudgement.id.desc()).first())
    if row is None:
        raise HTTPException(404, "아직 수신한 외부 AI 결과가 없습니다.")
    data = receipt(row)
    capture = data["observation"].get("captured_at")
    age = ((datetime.now(timezone.utc) - datetime.fromisoformat(capture)).total_seconds()
           if capture else None)
    data["expired"] = age is None or not -0.5 <= age <= 30
    return JSONResponse(data, headers={"Cache-Control": "no-store"})
