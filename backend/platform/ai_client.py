"""
AI 판정 서버(Modal에 배포된 /detect) 호출 클라이언트.

설정은 환경변수로만 받는다 (키를 코드/깃에 넣지 않기 위해):
  DG_AI_URL  (선택) 별도 모델 서버를 사용할 때 기본 주소 재정의
  DG_AI_KEY  Authorization: Bearer 에 들어갈 API 키
  DG_AI_TIMEOUT_S  (선택) 기본 45초 — Modal 콜드스타트 고려
"""
import os

import httpx

DEFAULT_AI_URL = "https://kbkr504--drown-guardian-api-fastapi-app.us-east.modal.run"
TIMEOUT_S = float(os.environ.get("DG_AI_TIMEOUT_S", "45"))


class AIClientError(Exception):
    pass


def _settings() -> tuple[str, str]:
    url = os.environ.get("DG_AI_URL", "").strip() or DEFAULT_AI_URL
    key = os.environ.get("DG_AI_KEY", "").strip()
    if not key:
        raise AIClientError("AI 접근 키가 설정되지 않았습니다. 서버의 DG_AI_KEY 설정 후 재배포가 필요합니다.")
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
        raise AIClientError("AI 서버에 연결할 수 없습니다. 잠시 후 다시 시도하세요.") from e

    if r.status_code in (401, 403):
        raise AIClientError("AI 서버 인증 실패 — DG_AI_KEY가 서버에 등록된 값과 다릅니다.")
    if r.status_code >= 400:
        raise AIClientError(f"AI 서버 오류 (HTTP {r.status_code})")
    try:
        return r.json()
    except ValueError:
        raise AIClientError("AI 서버 응답이 JSON이 아닙니다.")
