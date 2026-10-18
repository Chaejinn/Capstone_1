"""GET /api/status — SD-07: 설정 화면 진입 가능 여부(출동 중이면 진입 차단, NF-U-07)."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..dispatch.dispatch_manager import dispatch_manager
from ..dispatch.guidance_controller import guidance_controller

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status", response_model=schemas.StatusOut)
def get_status(db: Session = Depends(get_db)):
    return schemas.StatusOut(
        dispatch_in_progress=guidance_controller.is_busy(),
        active_mission_id=guidance_controller.active_mission_id if guidance_controller.is_busy() else None,
    )
