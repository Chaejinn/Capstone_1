"""Hardware-free command simulator with durable command history."""
import json
from threading import Lock
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, Integer, Text
from sqlalchemy.orm import Session

from ..database import Base, get_db
from ..deps import require_operator_or_admin
from ..models import TestSignal
from .test_signals import serialize


class TestCommand(Base):
    __tablename__ = 'test_control_commands'
    id = Column(Integer, primary_key=True)
    packet = Column(Text, nullable=False)


class CommandInput(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    command: Literal['DISPATCH', 'ESTOP', 'CLEAR_ESTOP', 'CANCEL', 'RETURN', 'DEPLOY', 'COMPLETE', 'RESET']
    target_x: float = 5
    target_y: float = 0


router = APIRouter(prefix='/test-control', tags=['test-control'],
                   dependencies=[Depends(require_operator_or_admin)])
lock = Lock()


def current(db):
    last = db.query(TestCommand).order_by(TestCommand.id.desc()).first()
    return json.loads(last.packet)['state'] if last else dict(status='IDLE', estop=False, target=None)


@router.get('')
def receive(after_id: int = Query(0, ge=0), latest: bool = False, db: Session = Depends(get_db)):
    query = db.query(TestCommand)
    if latest:
        last = query.order_by(TestCommand.id.desc()).first()
        return dict(packets=[], cursor=last.id if last else 0, state=current(db))
    rows = query.filter(TestCommand.id > after_id).order_by(TestCommand.id).limit(100).all()
    return dict(packets=[json.loads(row.packet) for row in rows],
                cursor=rows[-1].id if rows else after_id, state=current(db))


def send(body: CommandInput, db: Session = Depends(get_db)):
    # This simulator runs on a single local server process.
    with lock:
        state = current(db)
        command = body.command
        if state['estop'] and command not in ('ESTOP', 'CLEAR_ESTOP', 'RESET'):
            raise HTTPException(409, '비상정지를 먼저 해제하세요.')
        if command == 'RESET':
            state = dict(status='IDLE', estop=False, target=None)
        elif command == 'ESTOP':
            state.update(status='STOPPED', estop=True)
        elif command == 'CLEAR_ESTOP':
            state = dict(status='IDLE', estop=False, target=None)
        elif command == 'DISPATCH':
            state.update(status='DISPATCHED', target=dict(x=body.target_x, y=body.target_y))
        else:
            state['status'] = dict(CANCEL='CANCELLED', RETURN='RETURNING',
                                   DEPLOY='DEPLOYING', COMPLETE='COMPLETED')[command]
        labels = dict(DISPATCH='출동', ESTOP='비상정지', CLEAR_ESTOP='비상정지 해제',
                      CANCEL='출동 취소', RETURN='복귀', DEPLOY='구조망 전개',
                      COMPLETE='구조 완료', RESET='초기화')
        signal = TestSignal(source='control-test', message=f'[제어 테스트] {labels[command]} · {state["status"]}')
        db.add(signal)
        db.flush()
        packet = {**serialize(signal), 'command': command, 'state': state}
        record = TestCommand(packet=json.dumps(packet, ensure_ascii=False))
        db.add(record)
        db.flush()
        packet['command_id'] = record.id
        record.packet = json.dumps(packet, ensure_ascii=False)
        db.commit()
        return packet


@router.post('', status_code=201)
def send_and_notify(body: CommandInput, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    from .test_push import deliver
    packet = send(body, db)
    background_tasks.add_task(deliver, packet)
    return packet


@router.get('/auto')
async def auto_status():
    from ..test_automation import automation
    return automation.status()


@router.post('/auto/start')
async def auto_start():
    from ..test_automation import automation
    return automation.start()


@router.post('/auto/stop')
async def auto_stop():
    from ..test_automation import automation
    return await automation.stop()
