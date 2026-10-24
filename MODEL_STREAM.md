# 카메라 AI 분석 연결

현재 대시보드는 **카메라 연결 · AI 분석** 버튼 하나를 사용합니다.
브라우저 웹캠 → 로그인 인증된 `/api/camera/analyze` → Modal `/detect` 순서로
프레임을 전송하며, `bbox`와 `water_state`를 영상 위에 표시합니다.
분석은 한 번에 하나씩 실행하고 응답 후 1.5초 뒤 다음 프레임을 전송합니다.
박스는 최근 분석 프레임 기준이며 추적 결과나 실시간 위치를 보장하지 않습니다.
탐지 신뢰도는 상태 분류 신뢰도가 아닙니다. 자동 출동은 실행하지 않습니다.

웹 서버 실행 전에 `DG_AI_URL`에 Modal 서버 기본 주소, `DG_AI_KEY`에 API 키를
환경변수로 설정하세요. 모델 콜드 스타트를 고려하면 `DG_AI_TIMEOUT_S=45`를 권장합니다.
키는 브라우저에 전달하거나 소스 코드에 저장하지 않습니다.

```sh
python3 -m uvicorn app:app --host 127.0.0.1 --port 8000
```

`http://127.0.0.1:8000`에서 로그인하고 사이트 선택 후 카메라 연결 버튼을 누릅니다.
카메라 사용 권한을 허용해야 하며, 감지된 객체의 이미지 프레임은 Modal로 전송됩니다.
연결 해제·로그아웃·페이지 종료 시 촬영과 추가 분석 요청을 중단합니다.

모델 소스는 `local-model/Detective-model`에 내려받았으며 Git 추적에서 제외됩니다.
Modal 사용 시 로컬 학습 가중치나 Moondream 설치는 필요하지 않습니다.

## 참고: 별도 로컬 모델 스트림 실행

아래는 `scripts/model_stream.py`를 별도 도구로 사용하는 방법입니다.
현재 대시보드에는 기존 스트림 소스 선택 메뉴가 없습니다.

Detective-model의 RF-DETR → ByteTrack → Moondream 파이프라인이 OpenCV 창에 그린
추적 박스와 분류 결과를 그대로 JPEG 영상으로 제공합니다. 카메라를 두 번 열지 않습니다.
모델 저장소를 수정하지 않고 `scripts/model_stream.py`로 기존 파이프라인을 실행합니다.
영상 연결은 판정 이벤트 수신이나 구조보드 제어를 실행하지 않습니다.

## 카메라 PC에서 실행

먼저 [모델 저장소](https://github.com/DrownGuardian/Detective-model)의 설치 안내에 따라
Python 환경, 모델 가중치, Moondream 모델 정보와 API 키를 준비합니다.
`model_stream.py`는 **모델 의존성이 설치된 Python 환경**에서 실행해야 합니다.
아래 경로는 실제 두 저장소의 위치에 맞게 바꾸세요.

PowerShell:

```powershell
cd C:\Projects\Detective-model
$env:DG_MODEL_STREAM_TOKEN = (& .\venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))")
.\venv\Scripts\python.exe C:\Projects\Capstone1\scripts\model_stream.py --model-dir . --port 8765
```

macOS/Linux:

```sh
cd /path/to/Detective-model
export DG_MODEL_STREAM_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python /path/to/Capstone1/scripts/model_stream.py --model-dir . --port 8765
```

기본값은 로컬 PC의 `127.0.0.1:8765`에서 실행됩니다. 창 없이 실행하려면 `--headless`,
다른 카메라를 사용하려면 `--camera-index 1`을 추가합니다. 모델의 기존 CLI 옵션도 전달됩니다.
종료는 카메라 창에서 q/Esc 또는 터미널에서 Ctrl+C를 사용합니다.

## Vercel 화면에서 접속

카메라 PC의 서버를 HTTPS 역방향 프록시 또는 HTTPS 터널로 연결합니다.
터널은 `http://127.0.0.1:8765`로 전달하고, `/stream` 응답을 버퍼링하지 않아야 합니다.
Vercel 함수로 영상을 중계하지 않습니다. 모델 PC와 터널은 시청 중 계속 실행해야 합니다.
HTTPS 주소는 GitHub 저장소 주소나 Vercel 사이트 주소가 아니라 **영상 서버 주소**입니다.

1. 관제 화면 → 실시간 카메라 연결 → **AI 분석 영상**을 선택합니다.
2. 영상 서버 주소에 `https://camera.example.com`처럼 서버 기본 주소를 입력합니다.
3. 영상 연결 키에 실행 시 설정한 `DG_MODEL_STREAM_TOKEN` 값을 입력합니다.
4. **영상 연결**을 누르면 분석 영상과 `AI LIVE` 표시가 나옵니다.

키는 인증 헤더로 전송하며 브라우저 저장소에 보관하지 않습니다. 주소와 소스 선택만 저장합니다.
새로고침 후에는 키를 다시 입력해야 합니다. 기존 웹캠 서버는 소스를 바꾸고 `/api`를 포함한
백엔드 주소와 해당 서버의 계정을 입력하여 연결할 수 있습니다.

서버는 기본적으로 `https://drown-guardian.vercel.app`의 브라우저 요청만 허용합니다.
다른 도메인이나 로컬 화면을 쓴다면 `--origin https://your-dashboard.example.com`으로 지정합니다.
키가 틀리면 401, 모델 프레임이 없으면 503을 반환합니다. 10초 동안 새 프레임이 없으면
스트림을 종료하고, 관제 화면은 연결 끊김을 표시합니다. 다시 연결할 때 키를 다시 입력합니다.

## 검증 범위

```sh
python -m unittest discover -s tests -p test_model_stream.py
```

모델 가중치, API 키, 실제 카메라 및 외부 HTTPS 주소가 있어야 실제 영상 연결을 검증할 수 있습니다.
