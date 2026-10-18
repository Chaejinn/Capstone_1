"""POST /api/calibration — E-05: 기준점 4점 → H 행렬·오차 반환."""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..services import config_service

router = APIRouter(prefix="/api", tags=["calibration"])


@router.post("/calibration", response_model=schemas.CalibrationOut)
def calibrate(body: schemas.CalibrationRequest, db: Session = Depends(get_db)):
    try:
        row = config_service.save_calibration(db, body.img_points, body.world_points)
        return schemas.CalibrationOut(
            calib_id=row.calib_id,
            h_matrix=json.loads(row.h_matrix),
            reproj_error_m=row.reproj_error_m,
            accepted=True,
        )
    except config_service.ConfigValidationError as e:
        return schemas.CalibrationOut(
            calib_id=-1, h_matrix=[[0, 0, 0], [0, 0, 0], [0, 0, 0]],
            reproj_error_m=999.0, accepted=False, reason=str(e),
        )
