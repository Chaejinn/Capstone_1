# 카메라 PC 측정 도구

전달받은 `homography-aruco.zip`을 이 디렉터리에 통합했습니다.
웹(`code/`, `backend/`)과 별도이며, RF-DETR·Moondream 모델 실행기나 보트 제어기가 아닙니다.
ZIP의 파일별 원본 해시는 `handoff-manifest.json`에 있습니다.

## 폴더

| 경로 | 용도 |
| --- | --- |
| `run.py`, `diagnose.py` | 공통 실행·읽기 전용 진단 |
| `scripts/homography/`, `src/homography/` | 보정 편집·픽셀→실좌표 변환 |
| `scripts/aruco/`, `src/aruco/` | 마커 생성·검출·헤딩 측정 |
| `scripts/publish_pose.py`, `src/web/` | 카메라 PC → 웹 관측 전송 |
| `configs/` | 이 도구에서 실제 사용하는 최소 설정 |
| `calibration/` | 실제 카메라 보정 파일; 초기 상태는 미보정 |
| `reference/` | ZIP의 전체 파이프라인 설정·잘못된 기존 보정값 보존본; 실행에 사용하지 않음 |
| `outputs/`, `.venv/` | 생성물·로컬 환경; Git/Vercel 제외 |
| `tests/` | 실제 카메라 없이 합성 마커·좌표·저장 동작 검증 |

## 설치

프로젝트 루트에서 Python 3.12 이상으로 실행합니다. 가상환경 활성화는 필요 없습니다.

macOS/Linux:

```sh
python3 -m venv edge-vision/.venv
edge-vision/.venv/bin/python -m pip install -r edge-vision/requirements.txt
edge-vision/.venv/bin/python edge-vision/run.py diagnose
```

Windows PowerShell:

```powershell
py -3.12 -m venv edge-vision\.venv
.\edge-vision\.venv\Scripts\python.exe -m pip install -r edge-vision\requirements.txt
.\edge-vision\.venv\Scripts\python.exe edge-vision\run.py diagnose
```

아래 `python`은 위 가상환경의 실행 파일을 의미합니다. `diagnose`는 카메라를 열지 않으며,
준비 완료는 종료 코드 0, 미보정·미측정·의존성 누락은 2, 설정 오류는 1입니다.
GUI 지원 확인은 창이 실제로 정상 표시됐다는 검증과 다릅니다.

## 실제 카메라 준비 순서

1. 다른 카메라 프로그램과 브라우저 카메라 연결을 종료합니다. 카메라는 한 프로그램만 사용합니다.
2. `python edge-vision/run.py print-marker`로 PDF/PNG를 생성합니다.
   A4 실제 크기 100%로 출력하고, 검은 사각형의 변 길이를 자로 재서 `configs/aruco.yaml`에 맞춥니다.
3. `python edge-vision/run.py calibrate`에서 현재 영상의 실제 수조 좌상→우상→우하→좌하를 지정하고 저장합니다.
   수조 크기 0.30×0.45 m는 전달받은 값이므로 현재 수조를 실측해 다르면 수정합니다.
4. `python edge-vision/run.py marker --world --write`에서 선수를 알려진 방향으로 고정하고
   헤딩 오프셋을 측정·저장합니다. 기본 기대 방향은 +Y=90도입니다.
5. `python edge-vision/run.py pose`로 여러 방향을 점검하고, 독립 검증점을 보정 편집기에 기록합니다.
6. `python edge-vision/run.py diagnose`를 다시 실행합니다. 실제 촬영·측정 없이는 준비 완료로 바꾸지 않습니다.

카메라 선택은 `--camera-index 1`, 편집기에 동영상 입력은 `--video sample.mp4`입니다.
원본 ZIP 보정점은 뒤집힌 순서로 진단되어 실행용 기본값에서 제거했습니다. 임의의 사각형이나
오프셋 0을 실제 측정값으로 저장하지 마세요. 헤딩 측정 전에도 `marker`로 픽셀 각도는 관찰할 수 있지만
`publish-pose`는 유효한 미터 좌표와 측정 기록이 있는 헤딩이 모두 필요합니다.

좌표는 수조 좌하단 원점, +X 오른쪽, +Y 위, 단위 m입니다.
헤딩은 +X=0도, 반시계 증가입니다. 0~1000 격자는 표시용이며 미터 좌표가 아닙니다.

## 웹 연결

Git에 포함되지 않는 `.env.edge-handoff`의 설정을 사용합니다. 다른 PC에서는 비공개로 전달받아
별도 `.env` 파일에 저장하세요. 키를 README나 프런트엔드에 복사하지 않습니다.

```sh
python edge-vision/run.py publish-pose --env-file .env.edge-handoff --check-web
python edge-vision/run.py publish-pose --env-file .env.edge-handoff
```

`--check-web`은 서버 시각과 왕복 시간을 조회하며 카메라나 POST를 사용하지 않습니다.
오차는 네트워크 지연의 영향을 받는 추정치입니다. PC 시각이 빠르면 OS에서 동기화하고 재확인합니다.
관측 시각을 서버 시각으로 덮어쓰거나 미래 시각 제한을 완화하지 않습니다.

`--dry-run`은 카메라/동영상을 읽어 전송할 JSON만 출력하고 웹에는 보내지 않습니다.
`--max-frames 10`으로 측정 횟수를 제한할 수 있습니다. 네트워크는 기본 1초 간격으로 최신 프레임만 보내며,
이미지·오래된 프레임을 대기열에 누적하지 않습니다. 원본 영상은 이 송신기에 저장하지 않습니다.

웹 API:

- `GET /api/edge/time`: 시각 진단
- `POST /api/edge/pose`: 전용 서비스 키로 보드 관측 수신
- `GET /api/edge/pose?site_id=chunjeon&camera_id=camera-01`: 로그인한 관제 사용자 조회

관제 화면에서 **로컬 PC의 AI 결과 연결 → 웹 직접 수신**을 선택합니다.
익수 분류 데이터가 없어도 보드 관측은 따로 조회됩니다.
관측은 카메라별 최신 1개만 DB에 보관하고, 중복·역순·동시 다른 송신 세션은 처리합니다.
서버에서 250 ms를 넘긴 좌표는 null로 바꾸며 화면도 남은 유효시간 후 좌표를 지웁니다.
따라서 클라우드 왕복이 느리면 위치가 ‘관측 만료’로 표시될 수 있습니다.
이 표시 경로는 실제 보트의 실시간 유도 경로가 아니며 출동 명령을 발행하지 않습니다.

AI 익수 판정은 기존 Modal 경로를 유지합니다. 이 ZIP에는 RF-DETR/Moondream 모델·15프레임 판정기·
보트 브릿지·복귀/완료 로직이 없으므로 도구 통합만으로 해당 기능이 완성됐다고 볼 수 없습니다.

## 검증

```sh
python -m unittest discover -s edge-vision/tests -v
```

합성 영상에서 마커 ID·미터 좌표·헤딩, 중복 마커, 프레임 만료, 보정 저장/재로드,
인쇄용 마커 재검출, HTTP 오류의 상태 코드·시각 원인을 검증합니다.
실물 수조 정확도·카메라 GUI 조작·보트 주행은 별도 현장 검증이 필요합니다.
