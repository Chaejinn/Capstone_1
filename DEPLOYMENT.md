# Vercel 전체 서비스 배포

## 로컬 통합 실행

저장소 루트에서 `python3 -m uvicorn app:app --host 127.0.0.1 --port 8000`으로 실행합니다.
`app.py`는 `backend.app.main`의 단일 FastAPI 앱을 실행합니다.
`backend/platform`에는 인증·사이트·카메라 기능, `backend/app`에는 판단·미션·보트 기능이 있으며
DB 엔진·세션·테이블 메타데이터를 공유합니다. `backend(org)`는 실행에 사용하지 않는 참고 원본입니다.

- `/api/auth`, `/api/sites`, `/api/users`: 계정·사이트·관리자 API
- `/api/sites/{site_id}/camera/stream`: 로그인 인증된 서버 카메라 스트림
- `/api/boat`: 실제 보트 명령 및 비상정지 API
- `/api/status`, `/api/config`, `/api/calibration`, `/api/mission`: 판단·설정·미션 API
- `/api/mission/events`: 판단 서버 이벤트 (`/api/events`는 플랫폼 이벤트)
- `/api/ai`: 플랫폼 AI 프레임 누적 판정
- `/api/judgement/ai`: 판단 서버 직접 AI 연동
- `/api/ws/{site_id}`, `/ws`: 사이트별 푸시 및 판단 서버 WebSocket
- `/api/docs`: 전체 API 문서

관리자 로그인은 `http://127.0.0.1:8000/admin-login.html`에서 합니다.
사이트 선택 후 대시보드에서 **기존 웹캠 서버**를 선택하고, 서버 주소에
`http://127.0.0.1:8000/api`와 백엔드 로그인 정보를 입력하면 서버 카메라 영상을 봅니다.
**이 기기 카메라**는 브라우저에서 직접 카메라를 여는 방식입니다.
동일 카메라를 서버와 브라우저에서 동시에 사용하지 않는 것을 권장합니다.
서버 카메라 사용에는 `python3 -m pip install opencv-python`이 추가로 필요합니다.

판단 API 제공과 AI 판정→대시보드 상태→실제 출동의 자동 연결은 별개입니다.
현재 대시보드 구조 진행과 판단 서버의 기본 BoardLink는 시뮬레이션입니다.
판단·미션·WebSocket은 로컬에서 활성화하며 Vercel에서는 비활성화합니다.

검증: `python3 -m unittest discover -s tests -p test_unified_server.py -v`

저장소 루트에서 배포합니다. `code/`만 배포하면 API가 포함되지 않습니다.

- 진입점: `app.py` (FastAPI), API 경로: `/api`
- 프론트: `scripts/build-vercel.py`가 `code/`의 HTML/CSS/JS를 `public/`으로 복사
- Vercel 설정: `vercel.json`
- Python 의존성: 루트 `requirements.txt` (카메라/OpenCV 제외)
- 실제 로그인·회원가입·계정 관리·사이트 관리·전역 설정·감사 로그는 API와 DB 사용
- 브라우저에는 JWT 세션만 저장하며 계정 비밀번호를 저장하지 않음

## 배포 환경변수

Vercel Marketplace의 PostgreSQL(예: Neon)을 프로젝트에 연결합니다.
`DG_DATABASE_URL`, `POSTGRES_URL`, `DATABASE_URL` 순으로 연결 문자열을 읽습니다.
Vercel에서는 SQLite나 임시 파일 DB로 대체하지 않습니다.

`DG_SECRET_KEY`에 임의의 긴 JWT 서명 키를 설정하고, 관리자 최초 생성용
`DG_ADMIN_ID`와 `DG_ADMIN_PW`를 설정합니다. 기존 로컬 DB와 계정은 업로드하지 않습니다.
신규 DB 테이블·관리자·사이트·기본 설정은 최초 실행 시 자동 생성됩니다.

```sh
vercel login
vercel link
vercel integration add neon --name drown-guardian-db --plan free -e production
vercel env add DG_SECRET_KEY production
vercel env add DG_ADMIN_ID production
vercel env add DG_ADMIN_PW production
vercel --prod
```

배포 후 `/api/health`와 `/api/docs`를 확인하고 로그인 화면에서 회원가입과
관리자 계정 로그인을 확인합니다.

## 카메라·장치 후속 연동

Vercel의 로컬 카메라 스트림과 WebSocket 서버는 비활성화합니다.
관제 화면에서는 별도 카메라 PC가 제공하는 HTTPS AI 분석 영상에 직접 연결할 수 있습니다.
실행과 연결 방법은 [MODEL_STREAM.md](MODEL_STREAM.md)를 참고하세요.
연결 전 화면과 구조 동작은 시뮬레이션입니다. 프레임 누적을 사용하는 실제
AI 판정 수신도 Vercel에서는 503을 반환합니다. 카메라 및 실제 보드·AI 연동은
지속 실행되는 장치 서버에서 후속 구성해야 합니다. 기존 로컬 백엔드의 카메라
구현은 보존되어 있습니다.

## 검증

```sh
python -m pytest tests/test_deployment.py -q
node tests/test-auth.mjs
python scripts/build-vercel.py
```
