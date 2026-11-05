# 카메라 AI 분석 연결

## 422 원인·지연 측정 (2026-11-05)

프레임 접수 제한은 **2초로 유지**했습니다. 실제 거부 응답은
`observed_age_seconds=2.768; limit=2`였으며, Vercel 인증·사이트 조회에
1,982.4ms, 추적 서버 왕복에 240.4ms가 걸렸습니다. Vercel의 DB `NullPool`을
작은 연결 풀로 교체해 매 요청의 새 TCP/TLS 연결 비용을 줄였습니다.
운영자 활성 여부와 사이트 권한은 여전히 매 요청 DB에서 조회하며 캐시하지 않습니다.

배포 후 운영 웹 단일 연결로 동일 샘플 JPEG 3장을 순차 전송한 결과:

| 항목 | 측정 범위 |
| --- | --- |
| 프레임 업로드 | 3회 모두 HTTP 200 |
| 인증·사이트 조회 | 869.4–876.5ms |
| 추적 서비스 업로드 왕복 | 174.3–224.4ms |
| 모델 내부 추론 | 6,681.1–6,778.1ms |
| 촬영 시각→추론 완료 | 8.636–8.848초 |
| ByteTrack ID | 3회 모두 세대 0, ID 1·2·3 유지 |

별도로 GPU 시작 대기 약 28.8초를 관찰했습니다. 초기 요청에서 시작 대기와
추론이 합쳐져 약 35.3초 후 결과가 만료되는 현상도 확인했습니다.
콜드 스타트와 정상 추론 지연은 프레임 접수 제한과 다른 문제입니다.
현재 순차 분석 경로가 `익수 점수 0.8 이상·15프레임` 실시간 판정을 충족한다고
볼 수 없습니다. 이 측정은 실제 웹캠·이동 대상의 추적 정확도 검증도 아닙니다.

웹 프록시는 알려진 프레임 시각·크기 검증 오류만 구체적으로 표시하며,
임의 원격 오류 본문과 키는 노출하지 않습니다. 성공 응답의 `proxy_timing`으로
인증·사이트 조회와 추적 서버 왕복 시간을 확인할 수 있습니다.

## 웹 카메라 추적·ID (2026-11-05)

현재 웹 카메라는 `/api/vision/streams` 인증 프록시를 통해 Modal의
`drown-guardian-web-tracking` 서비스에 연결합니다. 이 서비스가 기존 GPU
`/detect`의 RF-DETR·Moondream2 결과를 ByteTrack에 전달하고, 카메라 연결별
추적 세션과 ID를 유지합니다. Vercel 서버의 `VISION_SERVICE_URL`과
`VISION_SERVICE_API_KEY`가 필요하며 키는 브라우저에 전달하지 않습니다.

운영자/관리자 로그인 및 활성 사이트 선택 후 카메라를 연결합니다.
프레임 업로드 후 해당 프레임의 분석이 끝날 때까지 결과를 조회하고,
완료되면 다음 프레임을 보냅니다. 박스와 `ID 세대-번호`는 정확히 분석한
이미지 위에 표시합니다. 분석 화면은 카메라 원본 FPS로 갱신되지 않습니다.
동일 대상 연결은 분석 프레임 사이의 ByteTrack 결과이며, 가림·교차 때의
신원 정확도를 보장하지 않습니다.

재연결·서버 재시작 시 새 세션이 만들어지고, 분석 관측 간격이 15초를
넘으면 추적기를 초기화하며 ID 세대를 올립니다. ID는 연결 내 식별자이며
영구 사람 ID가 아닙니다. 연결 해제 시 세션 삭제를 요청하고, 삭제 요청이
실패해도 서버는 비활성 세션을 120초 후 정리합니다.

이 추적 전용 서비스에는 수조 실측 보정을 넣지 않았습니다. 좌표는 미보정이며
자동출동 명령은 생성하지 않습니다. `/api/camera/analyze` 단일 프레임 API는
호환용으로 유지하지만 현재 카메라 화면은 추적 스트림 API를 사용합니다.

## 현재 운영 모델 (2026-11-05)

Modal의 `drown-guardian-api`에 RF-DETR ONNX와 **Moondream2 + 학습된 LoRA**를
배포했습니다. Moondream2 기본 버전은 `6b714b26eea5cbd9f31e4edb2541c170afa935ba`이며,
분류 어댑터는 전달받은 `drown-guardian-models.zip`의 파일입니다.
`model.json`의 `adapter_path`를 통해 실제 학습 어댑터를 로딩합니다.
분류는 Modal GPU에서 실행하며 기존 Moondream Cloud 분류 모델을 호출하지 않습니다.

- 운영 웹: https://drown-guardian.vercel.app
- 모델 API: https://kbkr504--drown-guardian-api-fastapi-app.us-east.modal.run
- Modal 배포 준비본: `local-model/modal-moondream2-deploy` (가중치 포함, Git 제외)
- Vercel 재배포: `dpl_uZwWBgZDCQ93dP2Ns85fCD3UJMGn`

운영 웹 로그인 후 `/api/camera/analyze`로 샘플 JPEG를 전송해 HTTP 200과
탐지 3개, `SWIMMING` 분류 3개를 확인했습니다. 이는 연동 확인이며 모델의
일반적인 정확도나 실제 웹캠·자동출동 검증을 뜻하지 않습니다.

배포 시 토크나이저의 고정 snapshot을 내려받은 뒤 Hugging Face 캐시의
`refs/main`도 같은 revision으로 지정해야 합니다. Moondream 내부에서
토크나이저를 revision 없이 읽기 때문에 이 설정이 없으면 오프라인 실행이 실패합니다.

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

1. [Vercel 대시보드](https://vercel.com/dashboard)의 `drown-guardian` 프로젝트 환경변수 설정에서
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
