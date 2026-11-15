"""Durable, leased departure mailbox, separate from simulated test commands."""
import hashlib
import json
import math
import time
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, Float, Integer, String, Text
from sqlalchemy.orm import Session

from ..database import Base, get_db
from .vision import forward, scope

router = APIRouter(prefix='/board-control', tags=['board departure'])


class Channel(Base):
    __tablename__ = 'board_departure_channels'
    site_id = Column(String(80), primary_key=True)
    bridge_id = Column(String(36), nullable=False)
    lease_until = Column(Float, default=0)
    revision = Column(Integer, default=0)
    packet = Column(Text, default='{}')


class Receipt(Base):
    __tablename__ = 'board_departure_receipts'
    id = Column(String(64), primary_key=True)


class BridgeInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    bridge_id: UUID


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    stream_id: UUID
    frame_id: int = Field(ge=1)


def channel(db, site_id):
    return db.query(Channel).filter_by(site_id=site_id).with_for_update().first()


def write(row, command, **extra):
    row.revision += 1
    row.packet = json.dumps(dict(command=command, issued_at=time.time(), **extra))


@router.post('/connect')
def connect(body: BridgeInput, identity=Depends(scope), db: Session = Depends(get_db)):
    row = channel(db, identity[1])
    if row is not None and row.lease_until > time.time() and row.bridge_id != str(body.bridge_id):
        raise HTTPException(409, '이미 연결된 보드 브릿지가 있습니다.')
    if row is None:
        row = Channel(site_id=identity[1], revision=0)
        db.add(row)
    row.bridge_id = str(body.bridge_id)
    row.lease_until = time.time() + 4
    write(row, 'STOP')
    db.commit()
    return dict(revision=row.revision, command='STOP')


@router.post('/poll')
def poll(body: BridgeInput, identity=Depends(scope), db: Session = Depends(get_db)):
    row = channel(db, identity[1])
    if row is None or row.bridge_id != str(body.bridge_id):
        raise HTTPException(409, '브릿지를 다시 연결하세요.')
    if row.lease_until <= time.time():
        write(row, 'ESTOP')
    row.lease_until = time.time() + 4
    db.commit()
    return dict(revision=row.revision, **json.loads(row.packet))


@router.post('/stop')
def stop(identity=Depends(scope), db: Session = Depends(get_db)):
    row = channel(db, identity[1])
    if row is not None:
        write(row, 'ESTOP')
        db.commit()
    return dict(ok=True)


@router.post('/simulate')
def simulate(identity=Depends(scope), db: Session = Depends(get_db)):
    """Explicit physical departure test; never creates an AI judgement or rescue event."""
    row = channel(db, identity[1])
    if row is None or row.lease_until <= time.time():
        raise HTTPException(409, 'Windows 출동 브릿지가 연결되지 않았습니다.')
    previous = json.loads(row.packet).get('command')
    if previous != 'STOP':
        raise HTTPException(409, '이미 출동했거나 비상정지 상태입니다. 브릿지를 다시 시작하세요.')
    write(row, 'DISPATCH', simulation=True, source='SIMULATED_DROWNING',
          throttle=5, max_seconds=3, expires_at=time.time()+3)
    db.commit()
    return dict(status='ISSUED', simulation=True, throttle=5, max_seconds=3)


def eligible(analysis, frame_id, now):
    if not isinstance(analysis, dict) or analysis.get('expired') is not False or analysis.get('frame_id') != frame_id:
        return None
    for item in analysis.get('detections', []):
        if item.get('confirmed') is not True or item.get('coordinate_valid') is not True:
            continue
        try:
            age = now - datetime.fromisoformat(item['confirmed_at'].replace('Z', '+00:00')).timestamp()
            coords = [item['target_x_m'], item['target_y_m']]
            if (0 <= age <= 3 and item['consecutive_frames'] >= 15
                    and item['drowning_score'] >= 0.8 and item.get('track_id') is not None
                    and all(isinstance(n, (int, float)) and math.isfinite(n) for n in coords)):
                return item
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    return None


@router.post('/dispatch')
async def dispatch(body: EvidenceInput, identity=Depends(scope), db: Session = Depends(get_db)):
    # Retrieve model evidence ourselves; never accept browser-provided scores or coordinates.
    snapshot = await forward(f'/v1/streams/{body.stream_id}/results', 'GET', identity)
    item = eligible(snapshot.get('analysis'), body.frame_id, time.time())
    if item is None:
        raise HTTPException(409, '최신 익수 확정·좌표 보정 조건을 충족하지 않았습니다.')
    evidence_key = hashlib.sha256(
        f"{identity[0]}:{identity[1]}:{body.stream_id}:{item.get('track_generation')}:{item['track_id']}".encode()
    ).hexdigest()
    row = channel(db, identity[1])
    if row is None or row.lease_until <= time.time():
        raise HTTPException(409, 'Windows 출동 브릿지가 연결되지 않았습니다.')
    if json.loads(row.packet).get('command') == 'ESTOP':
        raise HTTPException(409, '비상정지 상태입니다. 브릿지를 다시 시작하세요.')
    if db.get(Receipt, evidence_key):
        return dict(status='ALREADY_ISSUED')
    # One departure per armed session; reconnect locally to arm another mission.
    if json.loads(row.packet).get('command') == 'DISPATCH':
        raise HTTPException(409, '이미 출동했습니다. 다음 출동은 브릿지를 다시 시작하세요.')
    db.add(Receipt(id=evidence_key))
    write(row, 'DISPATCH', throttle=5, max_seconds=3,
          expires_at=time.time() + 3, target_x_m=item['target_x_m'], target_y_m=item['target_y_m'])
    db.commit()
    return dict(status='ISSUED', revision=row.revision, max_seconds=3, throttle=5)
