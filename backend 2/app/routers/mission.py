"""POST /api/mission/click-target — E-03: 화면 클릭으로 목표 지정."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..dispatch.dispatch_manager import dispatch_manager
from ..dispatch.guidance_controller import guidance_controller

router = APIRouter(prefix="/api", tags=["mission"])


@router.post("/mission/click-target", response_model=schemas.MissionOut)
async def click_target(body: schemas.ClickTargetRequest, db: Session = Depends(get_db)):
    if guidance_controller.is_busy():
        raise HTTPException(409, "이미 출동이 진행 중입니다.")
    mission = await dispatch_manager.click_target(db, body.target_x, body.target_y)
    return mission
