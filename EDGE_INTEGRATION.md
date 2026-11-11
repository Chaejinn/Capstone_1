# 로컬 AI → 배포 관제 웹 연결

## 운영 반영 확인 (2026-11-11)

- 운영 주소: https://drown-guardian.vercel.app
- 웹 수신·조회 API와 `edge-camera.js`, 관제 화면을 운영에 반영했습니다.
- `DG_EDGE_INGEST_KEY`, `DG_EDGE_SITE_ID=chunjeon`, `DG_EDGE_CAMERA_ID=camera-01`을
  Vercel Production에 설정했습니다. 수신 키 값은 이 문서와 프런트엔드에 포함하지 않습니다.
  AI PC의 `WEB_BACKEND_TOKEN`에는 해당 키를 별도로 안전하게 전달해 설정해야 합니다.
- 출동과 무관한 `INTEGRATION_TEST` / `UNCLEAR` 관측으로 실제 수신·DB 조회·중복 방지를
  확인했습니다. 촬영 시각이 없는 테스트 관측이므로 실시간 결과로 표시하지 않습니다.
- **Modal edge API도 실제로 존재합니다.** `/v1/edge/{camera}`와 분석 이미지 경로를
  운영 OpenAPI에서 확인했습니다. 확인한 사이트 `chunjeon`, 카메라 `camera-01`,
  소유자 ID `1` 조합의 조회는 `404 / No local camera telemetry`였습니다.
  이는 해당 조합에 보관 중인 데이터가 없다는 뜻이며 API 미배포를 의미하지 않습니다.
  다른 소유자·사이트·카메라로 송신 중인지는 이 결과만으로 판단할 수 없습니다.
- 실제 PC의 시간 동기화·중계 성공 및 실제 카메라 데이터 표시는 아직 검증하지 않았습니다.

이 변경은 웹 수신·조회·화면 기능입니다. 기존 Modal 브라우저 카메라 경로와
외부 AI 결과를 합쳐 15프레임을 다시 집계하지 않습니다. 외부 결과 수신만으로
익수 확정·출동 명령을 생성하지 않습니다.

## 1. hybrid: 로컬 PC → Modal 중계 → 관제 웹

AI 저장소의 `src/delivery/edge.py`에 정의된 `edge-telemetry-v1` 계약을 사용합니다.

- 관제 조회: `GET /api/vision/edge/{camera_id}?site_id={site_id}`
- 분석 이미지: `GET /api/vision/edge/{camera_id}/frames/{frame_id}?site_id={site_id}&session_id={UUID}`
- 웹 서버는 기존 `VISION_SERVICE_URL`, `VISION_SERVICE_API_KEY`로 Modal의
  `/v1/edge/...` 경로에 전달합니다. 운영 Modal에 해당 경로가 있어야 합니다.
  웹 변경만으로 Modal의 404는 해결되지 않습니다.
- 로컬 PC의 `WEB_OPERATOR_ID`는 관제 웹 로그인 사용자의 **DB 사용자 ID**여야 합니다.
  로그인 아이디 문자열과 다릅니다. 생산자·조회자의 SHA256 소유자 값과
  `WEB_SITE_ID`, 카메라 ID가 일치해야 같은 중계 데이터를 볼 수 있습니다.
- PC의 `VISION_SERVICE_URL`은 웹에서 사용하는 동일한 추적 서비스 주소여야 합니다.
  별도의 GPU `/detect` 앱 주소와 혼동하지 마세요.
- Windows 시간을 동기화하세요. 기존 미래 시각 허용 0.5초·프레임 접수 2초는 변경하지 않았습니다.
- PC HTTP 오류 로그 개선과 Modal edge 경로 배포는 AI 저장소에서 필요합니다.

## 2. deployed: 로컬 PC → 관제 웹 직접 수신

새 관측 수신 API는 `POST /api/edge/classification`입니다.
기존 `/api/vlm/classification`의 Vercel 503 차단을 제거하지 않았습니다.
해당 경로의 메모리 프레임 카운터·출동 코드를 그대로 켜는 대신 별도 경로를 제공합니다.

Vercel 서버 환경변수:

```dotenv
DG_EDGE_INGEST_KEY=<별도 생성한 32자 이상의 무작위 서비스 키>
DG_EDGE_SITE_ID=chunjeon
DG_EDGE_CAMERA_ID=camera-01
```

AI 측 `WEB_BACKEND_TOKEN`에는 위 서비스 키를 설정하고, 실제 판정 송신 URL을
`https://drown-guardian.vercel.app/api/edge/classification`으로 지정합니다.
AI 설정의 `key_env`가 다른 이름이면 해당 설정도 맞춰야 합니다.
웹 사용자 로그인 JWT나 Modal 추론 키를 이 키와 혼용하지 마세요.
환경변수 설정 후 웹 재배포가 필요합니다. 키는 브라우저 코드에 넣지 않습니다.

인증: `Authorization: Bearer <서비스 키>` / 요청: `Content-Type: application/json`

```json
{
  "event_id": "camera-session-UUID:frame-123:track-7",
  "site_id": "chunjeon",
  "camera_id": "camera-01",
  "track_id": 7,
  "state": "DROWNING",
  "confidence": 1.0,
  "confidence_source": "vote_ratio",
  "frame_id": 123,
  "captured_at": "2026-11-11T00:00:00Z"
}
```

예시 시각은 실제 촬영 시각으로 교체하세요. 제공된 시각은 시간대가 필요하며
미래 0.5초 초과 또는 30초 초과 과거는 422로 거부합니다.
30초는 **완료된 분석 결과 수신** 기준이며, 기존 이미지 업로드 2초 제한과 다릅니다.
시각이 없으면 기록은 수신하지만 화면에서 최신 분석으로 표시하지 않습니다.

`request_id`는 `event_id`의 별칭으로 허용하며,
`classification: drowning/normal_swimming/abnormal`도 지원합니다.
`site_id`, `camera_id`는 필수이며 서비스에 설정한 값과 같아야 합니다.
`confidence`가 투표 비율이라면 모델 점수 `drowning_score`로 복사하지 마세요.
추가 필드는 판정 근거로 사용하지 않으며 원본 영상은 이 API에 저장하지 않습니다.

응답 200: `accepted`, `observation_id`, `received_at`, `observation`,
`judgement_verified:false`, `command_issued:false`, `status:OBSERVATION_ONLY`.
중복 event_id + 동일 관측 내용은 같은 ID를 반환하며, 내용이 바뀌면 409입니다.
재시도할 때 event_id와 sent_at을 포함한 같은 본문을 재사용하세요.
새 관측마다 새 event_id를 사용하세요. 401은 키, 403은 사이트·카메라,
422는 본문·시각, 503은 서버 설정을 확인하세요.

결과는 PostgreSQL의 새 `edge_judgements` 테이블에 저장됩니다.
기존 스키마 초기화 과정에서 테이블을 생성하며 파괴적 마이그레이션은 없습니다.
이는 관측 기록이며 실물 출동 이벤트 테이블과 분리됩니다.
현재 자동 보관 기간 정리는 없으므로 장기 운영 전 보관 정책이 필요합니다.

조회: `GET /api/edge/latest?site_id=chunjeon&camera_id=camera-01`
기존 운영자·관리자 로그인이 필요합니다. 서비스 키로 대시보드 조회를 허용하지 않습니다.

## 화면 확인 및 남은 검증

관제 웹에서 사이트를 선택한 뒤 **로컬 PC의 AI 결과 연결**을 펼쳐
`Modal 중계` 또는 `웹 직접 수신`과 카메라 ID를 선택하세요.
브라우저 카메라 분석과 로컬 결과 조회는 동시에 실행하지 않습니다.
직접 수신 경로는 메타데이터만 표시하고, hybrid 경로는 원본 분석 프레임을
세션·프레임 ID·촬영 시각이 일치할 때만 표시합니다.

서버에 전달된 `confirmed`나 투표 비율을 신뢰해 0.8 이상 15프레임을 충족했다고
표시하지 않습니다. AI와 웹의 판정 주체·점수 의미 합의, 실제 송신·운영 배포,
장시간 실제 카메라 테스트 및 15프레임 확정 후 3초 내 출동 검증은 별도입니다.
