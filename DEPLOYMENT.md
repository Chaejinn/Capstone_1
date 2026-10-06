# Vercel 전체 서비스 배포

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

이번 Vercel 배포에서는 카메라 UI/스트림과 WebSocket 서버를 비활성화합니다.
관제 화면의 영상·구조 동작은 시뮬레이션입니다. 프레임 누적을 사용하는 실제
AI 판정 수신도 Vercel에서는 503을 반환합니다. 카메라 및 실제 보드·AI 연동은
지속 실행되는 장치 서버에서 후속 구성해야 합니다. 기존 로컬 백엔드의 카메라
구현은 보존되어 있습니다.

## 검증

```sh
python -m pytest tests/test_deployment.py -q
node tests/test-auth.mjs
python scripts/build-vercel.py
```
