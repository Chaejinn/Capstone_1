"""
AI 판정 서버(Modal에 배포된 /detect) 호출 클라이언트.

설정은 환경변수로만 받는다 (키를 코드/깃에 넣지 않기 위해):
  DG_AI_URL  예) https://kbkr504--drown-guardian-api-fastapi-app.us-east.modal.run
  DG_AI_KEY  Authorization: Bearer 에 들어갈 API 키
  DG_AI_TIMEOUT_S  (선택) 기본 20초 — Modal 콜드스타트와 CPU 추론 지연을 감안
"""
import os

import httpx

TIMEOUT_S = float(os.environ.get("DG_AI_TIMEOUT_S", "20"))


class AIClientError(Exception):
    pass


def _settings() -> tuple[str, str]:
    url = os.environ.get("DG_AI_URL", "").strip()
    key = os.environ.get("DG_AI_KEY", "").strip()
    if not url or not key:
        raise AIClientError("DG_AI_URL / DG_AI_KEY 환경변수가 설정되지 않았습니다.")
    return url.rstrip("/"), key


async def health() -> dict:
    url, _ = _settings()
    async with httpx.AsyncClient(timeout=TIMEOUT_S) as c:
        r = await c.get(f"{url}/health")
    r.raise_for_status()
    return r.json()


async def detect(image_bytes: bytes, filename: str, content_type: str, frame_id: int | None = None) -> dict:
    """이미지 한 장을 AI 서버 /detect로 보내고 원본 JSON 응답을 돌려준다."""
    url, key = _settings()
    files = {"image": (filename, image_bytes, content_type or "image/jpeg")}
    data = {"frame_id": str(frame_id)} if frame_id is not None else {}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as c:
            r = await c.post(f"{url}/detect", headers={"Authorization": f"Bearer {key}"},
                             files=files, data=data)
    except httpx.TimeoutException:
        raise AIClientError(f"AI 서버 응답 시간 초과({TIMEOUT_S}초)")
    except httpx.HTTPError as e:
        raise AIClientError(f"AI 서버 연결 실패: {e}")

    if r.status_code in (401, 403):
        raise AIClientError("AI 서버 인증 실패 — DG_AI_KEY가 서버에 등록된 값과 다릅니다.")
    if r.status_code >= 400:
        raise AIClientError(f"AI 서버 오류 {r.status_code}: {r.text[:200]}")
    try:
        return r.json()
    except ValueError:
        raise AIClientError("AI 서버 응답이 JSON이 아닙니다.")
