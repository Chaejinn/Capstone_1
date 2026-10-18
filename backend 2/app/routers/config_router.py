"""GET·PUT /api/config/roi, /judge, /notify — SD-07 (E-04)."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..services import config_service

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("/roi", response_model=schemas.RoiOut)
def get_roi(db: Session = Depends(get_db)):
    active = config_service.get_active_config(db)
    return schemas.RoiOut(config_version=active.config_version, points=active.roi())


@router.put("/roi", response_model=schemas.RoiOut)
def put_roi(body: schemas.RoiUpdate, db: Session = Depends(get_db)):
    try:
        new = config_service.save_roi(db, [p.model_dump() for p in body.points], saved_by="admin")
    except config_service.ConfigValidationError as e:
        raise HTTPException(400, str(e))
    return schemas.RoiOut(config_version=new.config_version, points=new.roi())


@router.get("/judge", response_model=schemas.JudgeConfigOut)
def get_judge(db: Session = Depends(get_db)):
    active = config_service.get_active_config(db)
    return schemas.JudgeConfigOut(
        config_version=active.config_version,
        conf_threshold=active.conf_threshold,
        persist_frames=active.persist_frames,
        window_n=active.window_n,
        vlm_timeout_s=active.vlm_timeout_s,
    )


@router.put("/judge", response_model=schemas.JudgeConfigOut)
def put_judge(body: schemas.JudgeConfigUpdate, db: Session = Depends(get_db)):
    new = config_service.save_judge_config(
        db, body.conf_threshold, body.persist_frames, body.window_n, body.vlm_timeout_s,
        saved_by="admin",
    )
    return schemas.JudgeConfigOut(
        config_version=new.config_version,
        conf_threshold=new.conf_threshold,
        persist_frames=new.persist_frames,
        window_n=new.window_n,
        vlm_timeout_s=new.vlm_timeout_s,
    )


@router.get("/notify", response_model=list[schemas.NotifyTargetOut])
def list_notify(db: Session = Depends(get_db)):
    return db.query(models.NotifyTarget).all()


@router.post("/notify", response_model=schemas.NotifyTargetOut)
def create_notify(body: schemas.NotifyTargetCreate, db: Session = Depends(get_db)):
    row = models.NotifyTarget(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/notify/{target_id}", response_model=schemas.NotifyTargetOut)
def update_notify(target_id: int, body: schemas.NotifyTargetUpdate, db: Session = Depends(get_db)):
    row = db.query(models.NotifyTarget).filter(models.NotifyTarget.target_id == target_id).first()
    if not row:
        raise HTTPException(404, "알림 대상을 찾을 수 없습니다.")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/notify/{target_id}")
def delete_notify(target_id: int, db: Session = Depends(get_db)):
    row = db.query(models.NotifyTarget).filter(models.NotifyTarget.target_id == target_id).first()
    if not row:
        raise HTTPException(404, "알림 대상을 찾을 수 없습니다.")
    db.delete(row)
    db.commit()
    return {"ok": True}
