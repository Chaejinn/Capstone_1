# Drown Guardian 판단 서버 (FastAPI)

**팀 공식 설계서 v0.2**(`erd.puml`, `class_srv.puml`, `class_ai.puml`, `deploy.puml`, `sd01~07.puml`) 기준으로
다시 작성한 백엔드. 이전 버전(로그인/다중 사이트 프로토타입)은 설계와 맞지 않아 `backend_old/`로
옮겨두고 이 버전으로 대체함.

## 설계와 다른 점 (구버전 대비)

- **로그인/회원가입 없음.** 팀 설계서에 계정 개념이 없음 (카메라 1대·보드 1대 단일 배치, 로컬 Wi-Fi AP 안에서만 동작).
- **사이트 개념 없음.** 단일 배치 전제라 `sites` 테이블 삭제.
- **DB 스키마를 ERD 그대로 사용**: `drowning_event`, `event_frame`, `mission`, `estop_log`, `system_alert`, `config_snapshot`(버전관리), `calibration`, `notify_target`.
- **API 경로/WebSocket 토픽을 설계서 §2.4.3 그대로 사용**: `/api/status`, `/api/events`, `/api/events/{id}/frames`, `/api/config/roi|judge|notify`, `/api/calibration`, `/api/mission/click-target`, `/ws`(토픽: `detections`/`board`/`alarm`/`event_cancelled`/`alert`, 명령: `ESTOP`/`CANCEL_DISPATCH`/`RESUME_MISSION`/`END_MISSION`).

## 이번에 구현한 것 / 아직 시뮬레이션인 것

| 계층 | 상태 |
|---|---|
| `api/monitor`, `storage` (config/event/alert 서비스, WebSocketHub) | ✅ 실제 구현 |
| `dispatch`, `comm` (DispatchManager, GuidanceController, CommandBus, BoardLink) | ✅ 로직 구현, **BoardLink는 시뮬레이션** (실제 UDP·라즈베리파이 없음) |
| `ingest`, `perception`, `judgement` (카메라·검출·추적·VLM·N프레임 누적) | ❌ AI 담당 팀원 몫 (`class_ai.puml`). 대신 `POST /api/dev/judgement`로 이미 판정된 결과를 직접 주입해서 테스트 가능 |
| 하드웨어(RPi `board_agent`, Arduino `fw_main`) | ❌ HW 담당 팀원 몫 (`class_hw.puml`). `SimulatedBoardLink`가 대역 |

AI/HW 모듈이 준비되면 `app/routers/judgement.py`(개발용 주입 엔드포인트)를 지우고, 그쪽 코드에서
`app.dispatch.dispatch_manager.dispatch_manager.on_judgement(db, result)`을 직접 호출하면 되고,
`app/comm/board_link.py`의 `SimulatedBoardLink`를 실제 UDP `BoardLink`로 교체하면 된다 —
`GuidanceController`/`CommandBus`는 인터페이스가 같아서 그대로 둬도 됨.

## 설치 · 실행

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

기동 시 `drown_guardian.db`(SQLite)가 생기고, `config_snapshot` 기본값(신뢰도 0.90·15프레임)이 자동 시드됨.

Swagger 문서: `http://localhost:8000/docs`

## API 요약 (§2.4.3)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/api/status` | 출동 진행 중 여부 (설정 화면 진입 차단용, NF-U-07) |
| GET | `/api/events?from&to` | 이벤트 목록 |
| GET | `/api/events/{id}/frames` | 근거 스냅샷 |
| GET/PUT | `/api/config/roi` | 감시 ROI (최소 3점, EX-15) |
| GET/PUT | `/api/config/judge` | 판정 임계값(conf_threshold/persist_frames/window_n/vlm_timeout_s) |
| GET/POST/PATCH/DELETE | `/api/config/notify` | 알림 대상 |
| POST | `/api/calibration` | 기준점 4점 → H 행렬·재투영오차 (0.15m 초과 시 거부) |
| POST | `/api/mission/click-target` | 화면 클릭 목표 지정 (E-03) |
| POST | `/api/dev/judgement` | **[개발용]** AI 판정 결과 직접 주입 |
| WS | `/ws` | 실시간 토픽 구독 + 명령 전송 |

### WebSocket

서버 → 화면 (topic 필드로 구분):
- `board`: 보드 상태/위치/헤딩/거리/배터리/PWM
- `alarm`: 익수 경보 요약
- `event_cancelled`: 출동 취소 확인
- `alert`: 시스템 경고 발생/해소 (`state: "raised"|"cleared"`)
- `detections`: (AI 모듈 연결 전까지는 미발행)

화면 → 서버 (명령):
```json
{"type": "ESTOP"}
{"type": "CANCEL_DISPATCH", "event_id": "EVT-20261015-0003"}
{"type": "RESUME_MISSION"}
{"type": "END_MISSION"}
```

## 테스트 방법 (수동 검증 완료)

- ROI 3점 미만 저장 거부(EX-15), 저장 시 `config_snapshot` 버전 증가
- 캘리브레이션 정상/오차초과 케이스, H 행렬 계산 정확도 확인
- `normal_swimming` 판정 주입 시 출동 안 함, `drowning`+고신뢰도 주입 시 출동
- 출동 중 추가 `drowning` 판정은 새 이벤트 생성 안 하고 경보만 (EX-13)
- 출동 중 `/api/mission/click-target` 호출 시 409
- 전체 미션 시뮬레이션(NAVIGATING→TERMINAL_APPROACH→ALIGNING→DEPLOYING→HOLDING) 약 3.6초 내 완료, 이벤트 상태 COMPLETED로 갱신
- 3초 유예 내 `CANCEL_DISPATCH` 시 이벤트 CANCELLED + `is_false_positive=true`, 미션 중단
- WebSocket 연결 시 진행 중인 미션의 `board` 텔레메트리 실시간 수신 확인
