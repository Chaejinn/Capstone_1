# Drown Guardian

카메라로 대상을 확인하고, AI 분석 결과와 구조보드 상태를 보여주는 관제 웹입니다.

**웹 사용:** https://drown-guardian.vercel.app → 로그인 → 사이트 선택 → 카메라 연결

## 어디를 열면 되나요?

| 하고 싶은 일 | 열어 볼 곳 |
| --- | --- |
| 화면·버튼·색상 수정 | [code/](code/README.md) |
| 로그인·설정 저장·AI 연결 수정 | [backend/](backend/README.md) |
| 보드 연결 | [hardware/](hardware/README.md) |
| 사용 방법·배포 방법 확인 | [docs/](docs/README.md) |
| AI 담당자 자료 확인 | [Ai파일/](Ai파일/README.md) — 원본 구조 유지 |
| 수정한 기능 검사 | [tests/](tests/README.md) |
| 빌드·관리 도구 실행 | [scripts/](scripts/README.md) |

## 웹을 내 컴퓨터에서 실행하기

저장소 최상위 폴더에서 실행합니다. Python 가상환경을 사용하는 것을 권장합니다.

```sh
python -m pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000
```

브라우저에서 http://127.0.0.1:8000 을 여세요.
카메라는 브라우저 사용 권한이 필요하며, 실제 AI 분석에는 별도 AI 서버 설정이 필요합니다.
설정 방법은 [운영·배포 안내](docs/운영배포.md)에 있습니다.

## 최상위 설정 파일

- `app.py`: 웹 서버를 시작하는 파일입니다.
- `requirements.txt`: 웹 서버에 필요한 Python 패키지 목록입니다.
- `vercel.json`, `.vercelignore`: Vercel 배포 설정입니다.
- `.gitignore`: Git에 올리지 않을 파일 목록입니다.
- `requirements-local-ai.txt`: AI 담당 폴더의 패키지 목록으로 연결하는 기존 호환 파일입니다.
- [MODEL_STREAM.md](MODEL_STREAM.md), [EDGE_INTEGRATION.md](EDGE_INTEGRATION.md): 기존 AI 연결 기록입니다. AI 폴더에서 참조하므로 경로를 유지합니다.

## 꼭 알아 두세요

- 실제 사용하는 화면 원본은 `code/`입니다. `public/`은 배포할 때 자동 생성합니다.
- `Ai파일/`의 모델·도구·받은 자료는 이번 정리에서 변경하지 않았습니다. 큰 모델과 로컬 가상환경은 Git에 포함되지 않을 수 있습니다.
- 환경변수 파일, 로컬 DB, 가상환경은 개인 실행 자료입니다. 공유하거나 임의로 지우지 마세요.
- 현재 USB 브릿지의 검증 범위는 **10% 추진, 최대 0.8초 직진과 정지**입니다. 전체 자율 구조·복귀 완료를 의미하지 않습니다.

정리한 항목과 이전 파일의 새 위치는 [파일 정리 내역](docs/파일정리.md)을 참고하세요.
