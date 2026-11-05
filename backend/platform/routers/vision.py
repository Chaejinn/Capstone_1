"""Authenticated, site-scoped proxy for persistent Modal tracking sessions."""
import hashlib
import os
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import models
from ..database import get_db
from ..deps import require_operator_or_admin

router = APIRouter(prefix='/vision', tags=['camera tracking'])


def scope(site_id: str, user=Depends(require_operator_or_admin), db: Session = Depends(get_db)):
    site = db.query(models.Site).filter(models.Site.id == site_id).first()
    if site is None or not site.enabled:
        raise HTTPException(403, '사용 가능한 사이트를 선택하세요.')
    return hashlib.sha256(str(user.id).encode()).hexdigest(), site_id


async def forward(path, method, identity, body=None, content_type=None):
    url = os.environ.get('VISION_SERVICE_URL', '').rstrip('/')
    key = os.environ.get('VISION_SERVICE_API_KEY', '')
    if not url or not key:
        raise HTTPException(503, '추적 서버 연결 설정이 필요합니다.')
    headers = {'Authorization': 'Bearer ' + key, 'X-Vision-Owner': identity[0], 'X-Vision-Site': identity[1]}
    if content_type:
        headers['Content-Type'] = content_type
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.request(method, url + path, headers=headers, content=body)
        if response.status_code >= 400:
            raise HTTPException(response.status_code if response.status_code in (404, 413, 422, 429) else 502,
                                '추적 서버 요청 실패 (HTTP %d)' % response.status_code)
        return response.json()
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
async def create(identity=Depends(scope)):
    return await forward('/v1/streams', 'POST', identity, b'{"camera_id":"camera-01"}', 'application/json')


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


@router.delete('/streams/{stream_id}')
async def close(stream_id: UUID, identity=Depends(scope)):
    return await forward(f'/v1/streams/{stream_id}', 'DELETE', identity)
