"""Authenticated MJPEG camera stream, suitable for an <img> element."""
import time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from .. import config, models, security
from ..camera import CameraUnavailable, camera, mjpeg_part
from ..database import SessionLocal
from ..deps import get_current_user, oauth2_scheme

router = APIRouter(prefix='/sites', tags=['camera'])


def camera_access(site_id: str, token: str | None = Query(default=None),
                  bearer: str | None = Depends(oauth2_scheme)):
    # Close the DB session before streaming (including on older FastAPI versions).
    with SessionLocal() as db:
        value = bearer or token
        user = get_current_user(token=value, db=db)
        if user.role not in ('operator', 'admin'):
            raise HTTPException(403, '접근 권한이 없습니다.')
        site = db.query(models.Site).filter(models.Site.id == site_id).first()
        if not site:
            raise HTTPException(404, '사이트를 찾을 수 없습니다.')
        if not site.enabled:
            raise HTTPException(403, '비활성화된 사이트입니다.')
        if site_id != config.CAMERA_SITE_ID:
            raise HTTPException(404, '이 사이트에 설정된 카메라가 없습니다.')
        return security.decode_access_token(value)['exp']


@router.get('/{site_id}/camera/stream', response_class=StreamingResponse)
async def stream_camera(expires: float = Depends(camera_access)):
    camera.start()
    try:
        first = await camera.next_frame()
    except CameraUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    async def frames():
        sequence, jpeg = first
        try:
            while time.time() < expires:
                yield mjpeg_part(jpeg)
                sequence, jpeg = await camera.next_frame(sequence)
        except CameraUnavailable:
            pass  # Headers already sent: end the stream so the viewer can reconnect.
        yield b'--frame--\r\n'

    return StreamingResponse(frames(), media_type='multipart/x-mixed-replace; boundary=frame',
                             headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})
