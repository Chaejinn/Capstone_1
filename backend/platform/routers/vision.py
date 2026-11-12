"""Authenticated, site-scoped proxy for persistent Modal tracking sessions."""
import hashlib
import os
import re
import time
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import require_operator_or_admin

router = APIRouter(prefix='/vision', tags=['camera tracking'])


def install_timing(app):
    @app.middleware('http')
    async def timing(request: Request, call_next):
        if request.url.path.startswith('/api/vision/'):
            request.state.vision_started = time.perf_counter()
        return await call_next(request)


def scope(site_id: str, request: Request, user=Depends(require_operator_or_admin), db: Session = Depends(get_db)):
    site = db.query(models.Site).filter(models.Site.id == site_id).first()
    if site is None or not site.enabled:
        raise HTTPException(403, '사용 가능한 사이트를 선택하세요.')
    elapsed = (time.perf_counter() - getattr(request.state, 'vision_started', time.perf_counter())) * 1000
    return hashlib.sha256(str(user.id).encode()).hexdigest(), site_id, {'auth_site_ms': round(elapsed, 1)}


async def forward(path, method, identity, body=None, content_type=None):
    url = os.environ.get('VISION_SERVICE_URL', '').rstrip('/')
    key = os.environ.get('VISION_SERVICE_API_KEY', '')
    if not url or not key:
        raise HTTPException(503, '추적 서버 연결 설정이 필요합니다.')
    headers = {'Authorization': 'Bearer ' + key, 'X-Vision-Owner': identity[0], 'X-Vision-Site': identity[1]}
    if content_type:
        headers['Content-Type'] = content_type
    try:
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.request(method, url + path, headers=headers, content=body)
        elapsed = (time.perf_counter() - started) * 1000
        if response.status_code >= 400:
            message = '추적 서버 요청 실패 (HTTP %d)' % response.status_code
            if response.status_code == 404 and path.startswith('/v1/edge/'):
                try:
                    detail = response.json().get('detail')
                except (ValueError, AttributeError):
                    detail = None
                if detail == 'No local camera telemetry':
                    message = '현재 사용자·사이트·카메라에 해당하는 PC 분석 결과가 수신되지 않았습니다. PC 전송 상태와 연결 식별값을 확인하세요.'
                elif detail == 'Source frame expired or unavailable':
                    message = '해당 분석 이미지가 만료됐거나 아직 중계되지 않았습니다.'
            if response.status_code == 422:
                detail = response.json().get('detail')
                # Only allow known validation diagnostics, never arbitrary remote bodies.
                if isinstance(detail, str):
                    match = re.fullmatch(r'stale/future browser frame; observed_age_seconds=(-?\d+\.\d+); limit=(\d+); synchronize clocks', detail)
                    if match:
                        message = ('프레임 촬영 시각 검증 실패: 도착 시 나이 %ss, 허용 %ss; 인증·사이트 %.1fms, 추적 서버 왕복 %.1fms'
                                   % (match[1], match[2], identity[2]['auth_site_ms'], elapsed))
                    elif detail in ('Frame ID or image dimensions are invalid', 'frame_id must strictly increase within a stream', 'UTC timestamp required'):
                        message += ': ' + detail
            raise HTTPException(response.status_code if response.status_code in (404, 413, 422, 429) else 502,
                                message)
        data = response.json()
        if isinstance(data, dict):
            data['proxy_timing'] = {**identity[2], 'tracking_roundtrip_ms': round(elapsed, 1)}
        return data
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, '추적 서버에 연결할 수 없습니다.') from None


async def read_body(request, limit):
    body = bytearray()
    async for part in request.stream():
        body.extend(part)
        if len(body) > limit:
            raise HTTPException(413, '프레임 크기 제한을 초과했습니다.')
    return bytes(body)


@router.post('/streams', status_code=201)
async def create(identity=Depends(scope),db:Session=Depends(get_db)):
    import json
    from .camera_settings import configuration
    _,_,value=configuration(db,identity[1])
    payload={'camera_id':'camera-01','configuration':value.model_dump(mode='json')}
    opened=await forward('/v1/streams','POST',identity,json.dumps(payload).encode(),'application/json')
    if (value.revision or value.homography.enabled or value.aruco.enabled) and opened.get('configuration_revision')!=value.revision:
        if opened.get('stream_id'):
            await forward('/v1/streams/'+opened['stream_id'],'DELETE',identity)
        raise HTTPException(502,'추적 서버가 저장한 카메라 설정을 적용하지 못했습니다.')
    return opened


@router.post('/streams/{stream_id}/frames')
async def frames(stream_id: UUID, request: Request, identity=Depends(scope)):
    kind = request.headers.get('content-type', '')
    if not kind.lower().startswith('multipart/form-data;'):
        raise HTTPException(415, '이미지 multipart 요청이 필요합니다.')
    return await forward(f'/v1/streams/{stream_id}/frames', 'POST', identity,
                         await read_body(request, 5 * 1024 * 1024 + 65536), kind)


@router.get('/streams/{stream_id}/results')
async def results(stream_id: UUID, identity=Depends(scope)):
    from fastapi.responses import JSONResponse
    data = await forward(f'/v1/streams/{stream_id}/results', 'GET', identity)
    return JSONResponse(data, headers={'Cache-Control': 'no-store'})


@router.get('/edge/{camera_id}')
async def edge_latest(camera_id: str, identity=Depends(scope)):
    from fastapi.responses import JSONResponse
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', camera_id):
        raise HTTPException(422, '카메라 ID가 올바르지 않습니다.')
    data = await forward(f'/v1/edge/{camera_id}', 'GET', identity)
    return JSONResponse(data, headers={'Cache-Control': 'no-store'})


@router.get('/edge/{camera_id}/frames/{frame_id}')
async def edge_frame(camera_id: str, frame_id: int, session_id: UUID, identity=Depends(scope)):
    from fastapi.responses import JSONResponse
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', camera_id) or frame_id < 1:
        raise HTTPException(422, '카메라 또는 프레임 ID가 올바르지 않습니다.')
    data = await forward(f'/v1/edge/{camera_id}/frames/{frame_id}?session_id={session_id}', 'GET', identity)
    return JSONResponse(data, headers={'Cache-Control': 'no-store'})


@router.delete('/streams/{stream_id}')
async def close(stream_id: UUID, identity=Depends(scope)):
    return await forward(f'/v1/streams/{stream_id}', 'DELETE', identity)
