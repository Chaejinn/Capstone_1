# Drown Guardian 백엔드 (FastAPI)

기존 프론트엔드(`js/auth.js`, localStorage 기반 가짜 인증)를 대체하는 실제 백엔드.
SQLite + JWT + bcrypt 기반이며, `DG_DATABASE_URL` 환경변수만 바꾸면 PostgreSQL 등으로도 교체 가능(SRS FR-MON-005 비고 참고).

## 1. 설치

```bash
cd backend
pip install -r requirements.txt
```

## 2. 실행

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

최초 기동 시 자동으로:
- `drown_guardian.db` (SQLite) 생성
- 실제 관리자 계정 시드: `capstone1` / `20262026` (bcrypt 해시로 저장, 평문 노출 없음)
- 4개 사이트 시드 (`금오천 일대` 등 — 프론트 `DG.SITES`와 동일)
- 기본 판정 임계값 시드 (`thresh_conf=0.90`, `thresh_frames=15`)

가짜 운영자 placeholder 계정(chacha/kyuryang/chaejin 등)은 **의도적으로 시드하지 않음** — 실제 운영자는 회원가입(`/auth/signup`)으로만 생성됨.

Swagger 문서: `http://localhost:8000/docs`

## 3. 환경변수 (전부 기본값만으로도 완전히 로컬 동작 — NFR-ARC-001)

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DG_SECRET_KEY` | (개발용 기본값) | JWT 서명 키. 배포 전 반드시 변경 |
| `DG_TOKEN_EXPIRE_MIN` | `480` | 토큰 만료(분) |
| `DG_DATABASE_URL` | `sqlite:///./drown_guardian.db` | DB 연결 문자열 |
| `DG_ADMIN_ID` | `capstone1` | 관리자 아이디 |
| `DG_ADMIN_PW` | `20262026` | 관리자 비밀번호(최초 시드에만 사용) |

## 4. 주요 엔드포인트

### 인증
- `POST /auth/signup` — 운영자 회원가입 (관리자 아이디로는 가입 불가)
- `POST /auth/login` — 로그인 (form-urlencoded: `username`, `password`) → JWT 발급
- `GET /auth/me` — 내 정보 (Bearer 토큰 필요)

### 사용자 관리 (관리자 전용)
- `GET /users`, `POST /users`, `PATCH /users/{id}/active`, `DELETE /users/{id}`

### 사이트
- `GET /sites` (운영자+관리자)
- `GET/PUT /sites/{id}/roi` — ROI 폴리곤 좌표 (`[{x,y}, ...]`, 0~100 상대좌표, FR-SUR-002)
- `PATCH /sites/{id}/enabled` (관리자)

### 설정
- `GET /settings`, `PUT /settings` (관리자) — `thresh_conf`(0.5~0.99), `thresh_frames`(5~30)

### 연락처 (관리자 전용)
- `GET/POST /contacts`, `PATCH/DELETE /contacts/{id}`

### 감사 로그 (관리자 전용)
- `GET /audit`, `DELETE /audit`

### VLM 판정 수신 + 이벤트
- `POST /vlm/classification` — VLM 모듈이 프레임 판정 결과를 보고하는 엔드포인트.
  N프레임 연속 누적(`thresh_frames`) + 신뢰도(`thresh_conf`) 조건을 모두 만족해야
  `Event`가 생성되고 대시보드로 `DROWNING_STATUS`/`DISPATCH_COMMAND`가 푸시됨.
  **VLM이 `error`를 보고하면 절대 자동으로 정상/익수를 확정하지 않고 판단을 보류함.**
- `GET /events` — 이벤트 목록 (운영자+관리자)
- `POST /events/{id}/ack` — 경보 종료 처리 (`rescued`/`false_alarm_ack`/`track_lost`)
- `PATCH /events/{id}/dispatch` — 출동 진행 단계 갱신 (관리자, 보드 쪽에서 호출 가정)
- `POST /board/estop`, `POST /board/estop/clear` — 비상정지 (유일하게 남은 수동 개입)

### 실시간 대시보드 푸시
- `WS /ws/{site_id}?token=<JWT>` — 연결 후 `PERSON_COUNT`/`DROWNING_STATUS`/`DISPATCH_COMMAND`/`BOARD_TELEMETRY`
  이벤트를 JSON으로 push 받음 (공통 봉투: `{type, site_id, timestamp, payload}`).

## 5. curl 예시

```bash
# 로그인
curl -X POST http://localhost:8000/auth/login \
  -d "username=capstone1&password=20262026"

# 회원가입
curl -X POST http://localhost:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"username":"operator01","password":"pass1234","name":"홍길동"}'

# 인증 필요 요청
curl http://localhost:8000/sites \
  -H "Authorization: Bearer <access_token>"
```

## 6. 프론트엔드 연동 시 참고

- `js/auth.js`의 `dg*` 함수들(로컬스토리지 기반)을 이 API에 대한 `fetch` 호출로 교체하면 됨.
  필드명(`username`/`name`/`role`/`enabled`/`thresh_conf`/`thresh_frames` 등)은 기존 프론트 스키마와 최대한 맞춰둠.
- 대시보드의 `state.mode`(구 AUTO/MANUAL)는 백엔드에서는 더 이상 MANUAL 값을 주지 않음 —
  `BOARD_TELEMETRY.mode`는 `AUTO` 또는 `ESTOP`만 사용 (가상조이스틱/수동모드 삭제 반영).

## 7. 테스트 방법 (수동 검증 완료된 항목)

- 회원가입/로그인/`/me`, 관리자 아이디로 가입 차단(400)
- 역할 기반 접근 제어 (운영자가 관리자 전용 라우트 접근 시 403)
- 사이트 목록/설정 조회, 임계값 수정(범위 검증 포함)
- VLM 판정 → N프레임 누적 → 임계값 도달 시에만 `Event` 생성 및 웹소켓 브로드캐스트
- VLM 오류 응답 시 상태 미변경(판단 보류) 확인
- 이벤트 ack(구조완료) → 감사 로그 기록 → 웹소켓 브로드캐스트
- 비상정지/해제
- 미인증 요청 401, JWT 포함 웹소켓 연결

## 8. 웹캠 MJPEG 스트리밍

백엔드 컴퓨터에 연결된 USB 웹캠을 OpenCV로 읽어 JPEG 프레임으로 전송합니다.
별도 장치의 MJPEG URL도 서버의 `DG_CAMERA_SOURCE`로 지정할 수 있습니다.
브라우저 컴퓨터의 웹캠을 직접 업로드하는 기능은 아닙니다.

```bash
cd backend
pip install -r requirements.txt
DG_CAMERA_SOURCE=0 DG_CAMERA_SITE_ID=chunjeon uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DG_CAMERA_SOURCE` | `0` | USB 장치 인덱스 또는 서버에서 접근 가능한 MJPEG/RTSP URL |
| `DG_CAMERA_SITE_ID` | `chunjeon` | 카메라가 연결된 사이트 |
| `DG_CAMERA_WIDTH` / `DG_CAMERA_HEIGHT` | `1280` / `720` | 요청 해상도; 실제 해상도는 장치 지원에 따름 |
| `DG_CAMERA_FPS` | `15` | JPEG 전송 최대 FPS (1~60) |
| `DG_CAMERA_JPEG_QUALITY` | `80` | JPEG 품질 (1~100) |
| `DG_CAMERA_TIMEOUT` | `5` | 첫 프레임/새 프레임 대기 제한(초) |

- `GET /sites/{site_id}/camera/stream` — `multipart/x-mixed-replace; boundary=frame` 응답.
  각 part는 `Content-Type: image/jpeg`, `Content-Length`와 JPEG 데이터로 구성됩니다.
- 기존 `/auth/login`의 Bearer JWT가 필요합니다. 운영자/관리자만 활성 사이트의 카메라에 접근합니다.
  `<img>` 직접 연결을 위한 `?token=<JWT>`도 지원하나, URL 로그 노출을 피하도록 Bearer 방식을 권장합니다.
- 미인증 401, 권한/비활성 사이트 403, 없는 사이트/카메라 404, 카메라 초기 연결 실패 503.
  전송 중 장치 오류·수신 지연 또는 JWT 만료 시 스트림을 종료합니다.
- 한 프로세스의 캡처 스레드 하나를 모든 시청자가 공유합니다. 느린 클라이언트에는 최신 프레임만 전달합니다.
  첫 연결 시 장치를 열고 서버 종료 시 닫습니다. USB 장치 중복 점유를 막기 위해 **worker 1개**로 실행하세요.
  장치/드라이버의 `read()` 자체가 멈추면 서버 재시작이 필요할 수 있습니다.
- macOS에서는 백엔드를 실행하는 터미널에 카메라 접근 권한이 필요합니다.

대시보드의 **웹캠 연결 설정**에서 백엔드 주소와 **백엔드에 등록된 계정**을 입력하고
**웹캠 연결**을 누릅니다. 기존 프론트 로그인은 localStorage 기반이므로 별도 백엔드 로그인이 필요합니다.
비밀번호와 JWT는 저장하지 않으며, 영상 요청은 Authorization 헤더를 사용합니다.
HTTPS 페이지에서는 백엔드도 HTTPS로 제공해야 합니다.
시뮬레이션 일시정지는 영상 수신을 중단하지 않으며, **연결 해제**로 수신을 중단합니다.
실제 영상 표시 중에는 가상 감지 박스·보드·ROI를 숨깁니다. 실제 AI 감지 결과 연동은 별도입니다.

검증(실제 웹캠 없이 가상 프레임 사용):

```bash
pip install pytest httpx
cd backend
python -m pytest tests/test_camera.py
```

구현 참고: [FastAPI StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse),
[OpenCV JPEG 인코딩](https://docs.opencv.org/4.x/d4/da8/group__imgcodecs.html).
