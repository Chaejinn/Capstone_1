"""Independent, durable homography and ArUco settings for the browser camera."""
import hashlib
import json
from uuid import uuid4
from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from .. import models
from ..camera_configuration import CameraConfiguration, Homography, Aruco, homography_report
from ..database import get_db
from ..deps import require_admin
from ..audit import log as audit_log
from .vision import scope, forward

router=APIRouter(prefix='/vision',tags=['camera configuration'])
CAMERA='camera-01'


def configuration(db,site_id,for_update=False):
    key=hashlib.sha256(json.dumps([site_id,CAMERA]).encode()).hexdigest()
    query=db.query(models.CameraConfiguration).filter_by(scope_key=key)
    if for_update:query=query.with_for_update()
    row=query.first()
    return key,row,(CameraConfiguration.model_validate_json(row.payload_json) if row else CameraConfiguration())


@router.get('/configuration')
def read(identity=Depends(scope),db:Session=Depends(get_db)):
    from fastapi.responses import JSONResponse
    _,_,value=configuration(db,identity[1])
    return JSONResponse({**value.model_dump(mode='json'),'homography_report':homography_report(value.homography)},headers={'Cache-Control':'no-store'})


def save(db,identity,part,value,admin):
    key,row,current=configuration(db,identity[1],for_update=True)
    if part=='homography':value.calibration_id=str(uuid4())
    setattr(current,part,value);current.revision+=1
    payload=current.model_dump_json()
    if row:row.payload_json=payload;row.updated_at=models.now_utc()
    else:db.add(models.CameraConfiguration(scope_key=key,site_id=identity[1],camera_id=CAMERA,payload_json=payload))
    try:db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'동시에 설정을 저장했습니다. 새로 조회한 뒤 다시 저장하세요.') from None
    audit_log(db,actor=admin.username,action=f'카메라 {part} 설정 변경: site={identity[1]} revision={current.revision}')
    return {**current.model_dump(mode='json'),'homography_report':homography_report(current.homography)}


@router.put('/configuration/homography')
def homography(body:Homography,identity=Depends(scope),admin=Depends(require_admin),db:Session=Depends(get_db)):
    return save(db,identity,'homography',body,admin)


@router.put('/configuration/aruco')
def aruco(body:Aruco,identity=Depends(scope),admin=Depends(require_admin),db:Session=Depends(get_db)):
    return save(db,identity,'aruco',body,admin)


@router.post('/aruco/marker')
async def marker(body:Aruco,identity=Depends(scope)):
    return await forward('/v1/vision/marker','POST',identity,body.model_dump_json().encode(),'application/json')


@router.post('/configuration/inspect')
async def inspect(image:UploadFile=File(...),identity=Depends(scope),db:Session=Depends(get_db)):
    import base64
    if image.content_type not in ('image/jpeg','image/png'):raise HTTPException(415,'JPEG 또는 PNG가 필요합니다.')
    raw=await image.read(2*1024*1024+1)
    if not raw or len(raw)>2*1024*1024:raise HTTPException(413,'설정 확인용 이미지는 2 MiB 이하여야 합니다.')
    _,_,value=configuration(db,identity[1])
    payload={'image_base64':base64.b64encode(raw).decode(),'configuration':value.model_dump(mode='json')}
    return await forward('/v1/vision/inspect','POST',identity,json.dumps(payload).encode(),'application/json')
