"""
[개발용] POST /api/dev/judgement — AI 판단 파이프라인이 아직 붙기 전, JudgementResult를
직접 주입해서 출동 흐름 전체(SD-02~05)를 테스트하기 위한 엔드포인트.

공식 설계서(§2.4.3)의 REST 표에는 없는 경로다 — 실제 배치에서는 TemporalAggregator가
같은 프로세스 안에서 DispatchManager.on_judgement()를 직접 호출하며, 이 라우터는
AI 모듈이 준비되기 전까지의 임시 대역이다. AI 모듈이 통합되면 이 라우터는 제거하고
그쪽에서 dispatch_manager.on_judgement()를 직접 import해서 호출하면 된다.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..dispatch.dispatch_manager import dispatch_manager

router = APIRouter(prefix="/api/dev", tags=["dev"])


@router.post("/judgement", response_model=schemas.EventOut | None)
async def inject_judgement(body: schemas.JudgementResultIn, db: Session = Depends(get_db)):
    return await dispatch_manager.on_judgement(db, body)
