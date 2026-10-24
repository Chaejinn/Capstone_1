"""Authenticated camera frame inference; does not trigger dispatch."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from .. import ai_client
from ..deps import require_operator_or_admin

router = APIRouter(prefix='/camera', tags=['camera analysis'],
                   dependencies=[Depends(require_operator_or_admin)])


@router.post('/analyze')
async def analyze(image: UploadFile = File(...), frame_id: int | None = Form(None)):
    body = await image.read(5 * 1024 * 1024 + 1)
    if not body:
        raise HTTPException(400, '빈 이미지입니다.')
    if len(body) > 5 * 1024 * 1024:
        raise HTTPException(413, '이미지는 5 MiB 이하여야 합니다.')
    if image.content_type not in ('image/jpeg', 'image/png', 'image/webp'):
        raise HTTPException(415, 'JPEG, PNG, WebP 이미지를 사용하세요.')
    try:
        return await ai_client.detect(body, image.filename or 'frame.jpg', image.content_type, frame_id)
    except ai_client.AIClientError as exc:
        raise HTTPException(502, str(exc)) from exc
