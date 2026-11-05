# 카메라 AI 분석 연결

## Modal 배포 없이 로컬 실행

`scripts/local_ai.py`는 웹과 모델의 실제 `/detect` API를 하나의 로컬 서버로
실행합니다. RF-DETR는 CPU로 실행하므로 Mac에서도 CUDA가 필요하지 않습니다.
학습된 Moondream 분류는 기존 모델 코드대로 클라우드 API를 사용하므로 인터넷과
`MOONDREAM_API_KEY`가 필요합니다. 완전한 오프라인 추론은 아닙니다.

AI 담당자에게 다음 세 파일과 Moondream 접근 키를 받으세요. ONNX와 manifest는
같은 export 결과여야 합니다. 모델 코드는 `local-model/Detective-model`에 필요합니다.

- `local-model/Detective-model/outputs/onnx-stage2/rfdetr_fp32.onnx`
- `local-model/Detective-model/outputs/onnx-stage2/export_manifest.json`
- `local-model/Detective-model/weights/moondream/model.json` (`model_id` 포함)

Python 3.10 이상으로 저장소 루트에서 실행합니다. 기존 `.venv`가 3.9라면
새 환경을 사용하세요. 키는 저장소나 채팅에 붙여넣지 않습니다.

```sh
python3 -m venv .venv-ai
.venv-ai/bin/python -m pip install -r requirements-local-ai.txt
read -s 'MOONDREAM_API_KEY?Moondream API key: '
export MOONDREAM_API_KEY
.venv-ai/bin/python scripts/local_ai.py --check
.venv-ai/bin/python scripts/local_ai.py
```

위 비밀 입력 명령은 macOS 기본 zsh 기준입니다. Windows에서는 동일 키를 환경변수로
설정하고 가상환경의 `Scripts/python.exe`로 실행합니다.
`http://127.0.0.1:8000`에서 로그인 → 사이트 선택 → 관제 화면의
**카메라 연결 · AI 분석**을 누르세요. 웹캠 프레임은 인증된
`/api/camera/analyze` → 로컬 `/local-ai/detect`로 전달됩니다.
웹과 모델 사이 인증 키는 실행마다 자동 생성하며 브라우저에 보내지 않습니다.
실행 도구는 모델 저장소와 배포 설정을 수정하지 않습니다.
다른 모델 경로는 `--model-dir /path/to/Detective-model`, 포트는 `--port 8001`로 지정합니다.
이 실행 방식에서는 `DG_AI_URL`, `DG_AI_KEY`를 따로 설정할 필요가 없습니다.

모델 파일·키가 없는 상태에서는 실행 전 누락 항목을 출력하고 종료합니다.
실제 카메라 추론은 파일과 키를 준비한 뒤 확인해야 합니다.

## 기존 Modal 연결

### Vercel 웹에서 사용

연결 대상은 배포된 **GPU 이미지 추론 API**입니다. 브라우저 수집 앱의
`/v1/streams`와는 별도 경로이며, 현재 웹은 `/detect`로 이미지 한 장씩 분석합니다.
학습 모델 파일을 웹 서버에 설치할 필요는 없습니다.

1. [Vercel 환경변수 설정](https://vercel.com/chaejinns-projects/drown-guardian/settings/environment-variables)에서
   `DG_AI_KEY`를 추가합니다. 값은 담당자가 모델 서버에 등록한
   `DROWN_GUARDIAN_API_KEY`와 같아야 합니다. Production 환경을 선택하세요.
   프로젝트 화면이 열리지 않으면 Vercel 대시보드에서 `drown-guardian` 프로젝트의
   Settings → Environment Variables로 이동합니다.
2. 기본 AI 주소는 `https://kbkr504--drown-guardian-api-fastapi-app.us-east.modal.run`입니다.
   다른 서버를 사용할 때만 `DG_AI_URL`을 설정합니다. 경로 `/detect`는 붙이지 않습니다.
3. 코드를 배포하고, 환경변수 변경 후에는 Production을 재배포합니다.
   대기 시간 기본값은 45초이며 Vercel 함수 실행 시간은 60초로 설정합니다.
4. 배포된 웹에서 운영자/관리자로 로그인하고 사이트를 선택한 뒤
   **카메라 연결 · AI 분석**을 누르고 카메라 권한을 허용합니다.
5. `AI LIVE`, 탐지 수, 분석 시간이 표시되면 해당 프레임의 응답을 받은 것입니다.
   `UNCLEAR`는 분류 보류이며 익수 확정을 뜻하지 않습니다.

AI 키는 Vercel 서버에만 설정합니다. HTML/JS, Git, 채팅에 넣지 않습니다.
실제 장치에서 카메라 권한과 분석 응답을 확인해야 연결 검증이 완료됩니다.

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
