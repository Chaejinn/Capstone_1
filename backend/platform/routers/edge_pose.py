"""Camera-PC pose telemetry for display; never calls the control/dispatch layer."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError, model_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import require_operator_or_admin
from .edge import service_identity, active_site
from .vision import read_body

router = APIRouter(prefix='/edge', tags=['external board observations'])


class Pose(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    timestamp: datetime
    frame_id: int = Field(ge=1, strict=True)
    tracking_valid: StrictBool
    heading_offset_measured: StrictBool
    x: float | None = Field(default=None, ge=0)
    y: float | None = Field(default=None, ge=0)
    heading: float | None = Field(default=None, ge=0, lt=360)
    unit: Literal['m'] = 'm'
    coordinate_frame: str = Field(min_length=1, max_length=80)
    calibration_id: str = Field(min_length=1, max_length=160)
    status: str = Field(min_length=1, max_length=80)

    @model_validator(mode='after')
    def valid_coordinates(self):
        if self.tracking_valid:
            if (not self.heading_offset_measured or self.status != 'tracked'
                    or any(value is None for value in (self.x, self.y, self.heading))):
                raise ValueError('Valid pose requires measured heading and coordinates')
        elif any(value is not None for value in (self.x, self.y, self.heading)):
            raise ValueError('Invalid pose must use null coordinates and heading')
        return self


class Packet(BaseModel):
    model_config = ConfigDict(extra='forbid')
    site_id: str = Field(min_length=1, max_length=30)
    camera_id: str = Field(min_length=1, max_length=80)
    session_id: UUID
    sequence: int = Field(ge=1, strict=True)
    pose: Pose


@router.get('/time')
def server_time():
    return JSONResponse({'server_time':datetime.now(timezone.utc).isoformat()},
                        headers={'Cache-Control':'no-store'})


@router.post('/pose')
async def ingest(request: Request, identity=Depends(service_identity), db: Session = Depends(get_db)):
    try:
        packet = Packet.model_validate_json(await read_body(request, 16384))
    except ValidationError:
        raise HTTPException(422, '보드 관측의 시각·좌표·단위·측정 상태를 확인하세요.') from None
    if (packet.site_id, packet.camera_id) != identity:
        raise HTTPException(403, '서비스에 허용된 사이트·카메라가 아닙니다.')
    active_site(db, packet.site_id)
    now = datetime.now(timezone.utc)
    if packet.pose.timestamp.utcoffset() is None:
        raise HTTPException(422, '관측 시각에 시간대가 필요합니다.')
    age = (now-packet.pose.timestamp).total_seconds()
    if not -0.5 <= age <= 30:
        raise HTTPException(422, {'code':'INVALID_TIMESTAMP', 'observed_age_seconds':round(age,3),
                                 'server_time':now.isoformat()})
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    data = json.dumps(packet.model_dump(mode='json'), sort_keys=True)
    row = db.query(models.EdgePose).filter_by(scope_key=key).with_for_update().first()
    if row:
        if row.session_id == str(packet.session_id):
            if packet.sequence == row.sequence and data == row.payload_json:
                return {'accepted_sequence':row.sequence,'command_issued':False}
            if packet.sequence <= row.sequence:
                raise HTTPException(409, '이전 순서의 관측입니다.')
            previous = json.loads(row.payload_json)['pose']
            if (packet.pose.frame_id <= previous['frame_id'] or
                    packet.pose.timestamp <= datetime.fromisoformat(previous['timestamp'])):
                raise HTTPException(409, '프레임 번호와 촬영 시각이 증가해야 합니다.')
        elif (now.replace(tzinfo=None)-row.updated_at).total_seconds() < 5:
            raise HTTPException(409, '다른 카메라 송신 세션이 활성 상태입니다.')
        row.session_id, row.sequence, row.payload_json = str(packet.session_id), packet.sequence, data
        row.updated_at = now.replace(tzinfo=None)
    else:
        row = models.EdgePose(scope_key=key, site_id=packet.site_id, camera_id=packet.camera_id,
            session_id=str(packet.session_id), sequence=packet.sequence, payload_json=data,
            updated_at=now.replace(tzinfo=None))
        db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '동시 카메라 송신 요청입니다. 최신 프레임으로 재시도하세요.') from None
    return {'accepted_sequence':packet.sequence, 'command_issued':False}


@router.get('/pose')
def latest(site_id: str, camera_id: str, db: Session = Depends(get_db),
           user=Depends(require_operator_or_admin)):
    active_site(db, site_id)
    key = hashlib.sha256(json.dumps((site_id,camera_id)).encode()).hexdigest()
    row = db.query(models.EdgePose).filter_by(scope_key=key).first()
    if row is None:
        raise HTTPException(404, '아직 수신한 보드 관측이 없습니다.')
    data = json.loads(row.payload_json)
    age = (datetime.now(timezone.utc)-datetime.fromisoformat(data['pose']['timestamp'])).total_seconds()
    # Keep the original 250 ms pose freshness semantics. Cloud display latency
    # must never make an old position usable for actual guidance.
    expired = not 0 <= age <= 0.25
    if expired:
        data['pose'].update(x=None,y=None,heading=None,tracking_valid=False,status='stale_frame')
    return JSONResponse({**data,'expired':expired,'age_seconds':round(age,3),'command_issued':False},
                        headers={'Cache-Control':'no-store'})
