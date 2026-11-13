# 카메라 AI 분석 연결

## 0.8·15프레임 판정 운영 반영 (2026-11-06)

사용자가 확인한 시간 기준은 **15프레임 판정 성립 후 3초 내 출동 명령**입니다.
15개 분석 프레임을 3초 안에 수집한다는 기준은 아닙니다.

`backend/platform/drowning_gate.py`에 같은 추적 대상의 실제 익수 점수가
0.8 이상인 독립 분석 프레임 15개를 연속 누적하는 판정을 추가했습니다.
점수 미달·UNCLEAR·정상·대상 소실·분석 실패·오래된 프레임은 누적을
초기화하며, 중복·역순 프레임은 추가 증거로 세지 않습니다.
최초 확정 시각은 후속 프레임으로 미뤄지지 않습니다.

모델 배포 준비본은 반올림 전 Moondream2 `DROWNING` 정규화 라벨 점수를
`drowning_score`로 반환하도록 변경했습니다. RF-DETR 탐지 점수나 시간 투표
비율을 이 점수로 대체하지 않습니다. 이 값은 보정된 익수 확률이 아닙니다.
화면의 점수·누적 개수 표시를 포함해 모델 API·추적 서버·Vercel에 배포했습니다.
판정 단위 테스트 5개 및 카메라 JS 테스트가 통과했습니다.
별도 서버 통합 테스트에서 합성 입력 14프레임 미확정, 15프레임 확정,
16번째에도 최초 확정 시각 유지 및 미보정 출동 차단을 확인했습니다.
이는 합성 판정 입력 검증이며 실제 익수 영상의 인식 정확도 검증은 아닙니다.
운영 웹의 실제 모델 샘플 3장도 HTTP 200이었고, 익수 점수·조건·추적 ID가
전달됐습니다. SWIMMING 샘플은 누적 0, confirmed=false로 유지됐습니다.
Vercel 배포 ID: dpl_3BPJuftimveczxCR1usWZLdpAzrp.

실측 좌표 보정·보트 브릿지는 아직 제공되지 않았습니다.
출동 차단 상태를 명시하며, 실제 명령 발행·3초 기한·실물 출동·복귀·완료는
검증하지 않았습니다. 기본 `SimulatedBoardLink` 흐름과 실제 하드웨어 완료를
구분해야 합니다. 이 절의 구현으로 전체 요구사항 충족을 주장하지 않습니다.

## 추론 속도 개선 (2026-11-06)

운영 T4 GPU에서 Moondream2의 BF16 연산을 FP16 혼합 정밀도 추론으로
변경했습니다. LoRA는 기존 BF16 방식으로 병합한 뒤 가중치를 변환하므로
학습 어댑터와 질문, 입력 크기, 분류 임계값은 그대로입니다.
BF16로 고정된 이미지 전처리는 autocast로 연산 자료형을 맞추고,
분류는 `torch.inference_mode()`에서 실행합니다. CPU 및 BF16 하드웨어
지원 GPU는 기존 정밀도를 유지합니다.

동일 T4·동일 샘플(640×480, 대상 3개)의 별도 비교에서 중앙 추론 시간이
6,677.77ms → 934.11ms로 감소했습니다. 이 샘플의 탐지·분류 결과와 응답의
소수 4자리 분류 점수는 같았습니다. 일반적인 정확도 동등성을 입증한 것은 아닙니다.

운영 웹 경유 검증은 3회 모두 업로드·분석 성공, ID 1·2·3 유지,
`SWIMMING` 3개였습니다. 모델 추론 시간은 첫 요청 2.663초,
이후 1.059초·1.127초였습니다. 샘플 전송 시각→추론 완료는 각각
5.565초·3.758초·3.808초이며 실제 웹캠 촬영 지연을 측정한 값은 아닙니다.
모델 콜드 스타트와 네트워크 지연은 여전히 존재하고,
실시간 15프레임 판정 요구사항 충족을 뜻하지 않습니다.

API 주소가 같아 Vercel 코드·환경변수는 변경하지 않았습니다.
프레임 접수 제한 2초와 결과 만료 기준도 그대로 유지했습니다.
모델 원본 저장소에 반영할 패치는 `Ai파일/patches/moondream2-t4-fp16.patch`,
측정 기록은 `Ai파일/reports/ai-inference-speed-2026-11-06.json`입니다.
실제 배포본은 `Ai파일/local-model/modal-moondream2-deploy`에 있습니다.
롤백 시 Modal 컨테이너의 `DG_MODEL_PRECISION=bf16` 설정 후 재배포합니다.

## 실시간 영상과 분석 화면 분리

큰 카메라 화면은 브라우저 웹캠을 계속 재생합니다. AI 분석 결과는 그 아래
작은 `최근 AI 분석 프레임` 화면에 해당 촬영 이미지와 박스·추적 ID를 함께
표시합니다. 분석 이미지는 라이브 영상을 덮지 않습니다.
최근 결과는 다음 분석 중에도 유지하며 촬영 시각, 촬영 후 경과 시간,
모델 추론 시간을 표시합니다. AI 요청 실패 시에도 카메라는 계속 재생하고,
연결 해제·로그아웃 시 영상과 결과 및 경과 시간 타이머를 정리합니다.
이 변경은 표시 방식의 개선이며 추론 속도나 15프레임 판정 성능 개선을 뜻하지 않습니다.

## 422 원인·지연 측정 (2026-11-05)

운영 배포 소스에서 DB 연결 풀(`pool_size=2`, `max_overflow=1`) 반영을 확인했습니다.
운영 함수는 미국 동부(`iad1`), Neon DB는 싱가포르(`ap-southeast-1`)에 있었습니다.
Vercel 프로젝트의 Fluid 함수 기본 리전과 로컬 `vercel.json`을 싱가포르(`sin1`)로
맞추고 기존 운영 소스를 재배포했습니다. 배포 `dpl_GKEKXJFERQ7GRHVcv7Hi6bqSCCJR`의
`READY`, 리전 `sin1`, 운영 `/api/health`의 HTTP 200 및 `x-vercel-id`의 `sin1`을
확인했습니다.

리전 변경 후 운영 웹 프록시로 기존 샘플 JPEG를 전송했습니다. 첫 연결은 업로드 HTTP 200
이후 분석 단계에서 `ValueError`를 반환했습니다. 새 연결에서 순차 전송한 3장은 모두
업로드 HTTP 200, 인증·사이트 조회 7.7–8.8ms, 추적 서버 왕복 1,107.6–1,135.0ms로
422 없이 접수됐습니다. 3장 모두 분석 결과를 받았고 ByteTrack 세대 0, ID 1·2·3이
유지됐습니다. 전송용 촬영 시각부터 추론 완료까지 9.001–9.155초, 모델 추론은
7,056.6–7,164.0ms였습니다. 두 테스트 스트림은 HTTP 200으로 삭제했습니다.
실제 웹캠 검증은 아니며, 첫 연결의 분석 오류 원인과 재발 여부는 미확인입니다.

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
- Modal 배포 준비본: `Ai파일/local-model/modal-moondream2-deploy` (가중치 포함, Git 제외)
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
같은 export 결과여야 합니다. 모델 코드는 `Ai파일/local-model/Detective-model`에 필요합니다.

- `Ai파일/local-model/Detective-model/outputs/onnx-stage2/rfdetr_fp32.onnx`
- `Ai파일/local-model/Detective-model/outputs/onnx-stage2/export_manifest.json`
- `Ai파일/local-model/Detective-model/weights/moondream/model.json` (`model_id` 포함)

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

모델 소스는 `Ai파일/local-model/Detective-model`에 내려받았으며 Git 추적에서 제외됩니다.
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


### 2026-11-13 좌표축·마커 방향·PID 점검

- 호모그래피 설정 영상에 좌하단 원점, +X/+Y 화살표와 첫 4점의 실제 좌표를 표시합니다. 영상 픽셀 Y(아래로 증가)와 실제 좌표 Y(위로 증가)는 별개이며 변환 부호를 임의로 바꾸지 않았습니다.
- 원본 영상·보정 영상·AI 전송 영상의 해상도와 비율 불일치를 표시합니다. 전송은 최대 너비 960px이며 종횡비를 유지합니다.
- 기준점 4개 미만, 실측 크기 누락, 잘못된 사각형 순서·면적은 클라이언트에서 안내합니다. 서버의 정밀 검증은 유지합니다.
- 운영 chunjeon 설정 점검: revision 2, 호모그래피 비활성, 기준점 0개, image_size 및 실측 크기 없음. 해당 상태에서 활성화를 요청하면 422를 재현했습니다. 점검 요청은 검증 단계에서 거부됐고 운영 설정은 바꾸지 않았습니다. 이전 사용자 오류의 요청 본문은 확보하지 못했습니다.
- ArUco 관측에 화살표를 표시합니다. 측정된 방향·호모그래피가 있으면 실제 보드 방향을 역투영하며, 없으면 ‘마커 앞 · 보드 방향 미보정’으로 구분합니다.
- LAN BoatControl에 제한 적분과 포화 시 누적 방지를 추가했습니다. Kp=.8, Ki=0, Kd=.15 기본값을 유지합니다. 이 제어기는 Vercel에서 실물 보드에 연결된 것이 아니며, 브릿지·조향 부호·게인 실측 검증은 미완료입니다.
