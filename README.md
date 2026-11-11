# Drown Guardian · 관제 플랫폼

캡스톤디자인 「Drown Guardian」의 웹 관제 플랫폼과 카메라 PC 측정 도구입니다.

## 폴더 구조

| 경로 | 역할 |
| --- | --- |
| `code/` | 로그인·사이트 선택·관리자·관제 화면과 JS/CSS |
| `backend/platform/` | 사용자 인증, 사이트, AI 결과·보드 관측 수신, DB 저장 |
| `backend/app/` | 통합 FastAPI 진입점, 좌표·판정·보트 연결 모듈 |
| `app.py`, `vercel.json` | 로컬·Vercel 웹 실행 진입점과 배포 설정 |
| `Ai파일/` | 받은 AI 자료·모델·보정 도구·추적 서비스·패치·검증 기록 |
| `scripts/` | 웹 빌드와 기존 AI 명령의 호환 진입점 |
| `tests/`, `Ai파일/reports/` | 웹 테스트와 작업·검증 기록 |
| `Ai파일/patches/` | 별도 AI 저장소에 적용했던 변경 패치 |

`backend(org)/`, `dist/`, `code.zip`은 이전 자료로 남아 있습니다.
현재 웹 진입점은 `app.py`이며 프런트엔드는 `code/`입니다.
가상환경, 비밀키, 로컬 모델 파일과 실행 중 생성물은 Git에 포함하지 않습니다.

## 웹 실행과 배포

웹 의존성은 루트 `requirements.txt`를 사용합니다.
설치·환경변수·배포 방법은 [DEPLOYMENT.md](DEPLOYMENT.md)를 참고하세요.
운영 웹은 https://drown-guardian.vercel.app 입니다.
사용자 인증과 권한 검증은 서버 API에서 수행합니다.

브라우저 카메라의 AI 분석은 Vercel 인증 프록시를 통해 별도 Modal 추적·추론 서비스에 연결됩니다.
로컬 PC에서 별도로 측정·분석한 결과는 [EDGE_INTEGRATION.md](EDGE_INTEGRATION.md)의
외부 관측 수신 경로를 사용합니다. 웹 정적 파일만 배포해서 AI 모델이 실행되지는 않습니다.

## 호모그래피·ArUco 도구

AI 자료 전체 분류는 [Ai파일/README.md](Ai파일/README.md)를 참고하세요.
전달받은 도구는 [Ai파일/edge-vision/README.md](Ai파일/edge-vision/README.md)에 정리했습니다.
웹 서버와 별도 가상환경을 사용하며, 실제 카메라 보정과 헤딩 측정을 먼저 진행해야 합니다.
합성 영상 검증과 실제 수조·하드웨어 검증의 범위는
[인수·개발 결과](Ai파일/reports/homography-aruco-2026-11-12.md)에 구분했습니다.

## 실제 출동 상태

화면 시뮬레이션, AI 관측 수신, 실제 보트 제어는 별도 경로입니다.
외부 위치 관측 수신만으로 익수 확정이나 출동 명령을 발행하지 않습니다.
실물 브릿지·현장 보정·익수 판정 성립 후 3초 내 명령 발행 검증은
[BOAT_BRIDGE.md](BOAT_BRIDGE.md), [MODEL_STREAM.md](MODEL_STREAM.md)를 참고하세요.
