# AI 담당 자료와 AI 개발 코드

규랑님에게 받은 파일, AI 저장소 소스, 모델, 보정 도구 및 후속 개발 코드를 이 폴더에 모았습니다.
받은 자료와 웹 연동 과정에서 수정한 코드를 아래처럼 구분합니다.

| 경로 | 내용 | Git 관리 |
| --- | --- | --- |
| `받은원본/homography-aruco.zip` | 전달받은 호모그래피·ArUco ZIP 원본 복사본 | 제외 |
| `local-model/received-models-2026-11-05/` | 기존에 압축 해제한 RF-DETR·Moondream 전달 모델과 추가 준비한 기반 모델 | 제외 |
| `local-model/Detective-model/` | AI 담당자 GitHub 저장소 체크아웃 | 별도 저장소, 웹 Git에서 제외 |
| `local-model/modal-moondream2-deploy/` | 실제 배포에 사용한 소스·모델·CPU 서비스 빌드 컨텍스트 | 제외 |
| `local-model/optimization-backups/` | 최적화 이전 백업 | 제외 |
| `edge-vision/` | 전달받은 보정·ArUco 도구를 정리하고 수정한 실행 코드 | 포함 |
| `edge-vision/reference/` | ZIP의 기존 설정·미검증 보정값 보존본 | 포함 |
| `services/tracking/` | 웹 설정을 실제 처리에 적용하도록 수정한 Modal CPU 추적 코드 | 포함 |
| `tools/` | 로컬 AI 실행·영상 중계·배포 준비 스크립트 | 포함 |
| `patches/` | AI 모델 최적화 등 변경 패치 | 포함 |
| `reports/` | AI 성능·보정·웹 연동 검증 기록 | 포함 |
| `requirements-local-ai.txt` | 로컬 AI 추가 의존성 | 포함 |

`edge-vision/.venv/`, `local-model/.venv-modal/`, `local-model/.venv-tracking/`은
기존 로컬 가상환경을 함께 옮긴 것입니다. 모델과 생성물도 기존 파일을 그대로 보존했습니다.
현재 확인되는 ZIP 원본은 `받은원본/`에 복사했고, 모델 전달본은 이미 압축 해제되어 있던
`local-model/received-models-2026-11-05/`에 보존했습니다.

AI 원본 소스는 [DrownGuardian/Detective-model](https://github.com/DrownGuardian/Detective-model)의
별도 Git 체크아웃으로 유지합니다. 웹 저장소에 남아 있던 이전 위치의 Git 링크는 제거했으며,
로컬 체크아웃의 실제 파일과 Git 이력은 새 위치에 그대로 있습니다.
새 PC에서 원본 소스가 필요하면 별도로 해당 저장소를 내려받아야 합니다.

## 시작 위치

- [호모그래피·ArUco 측정 도구](edge-vision/README.md)
- [웹 카메라의 Modal 추적 서비스](services/tracking/README.md)
- [웹 연동 안내](../EDGE_INTEGRATION.md), [모델 연결 기록](../MODEL_STREAM.md)
- [호모그래피·ArUco 인수 결과](reports/homography-aruco-2026-11-12.md)

프로젝트 루트에서 실행하는 예:

```sh
Ai파일/edge-vision/.venv/bin/python Ai파일/edge-vision/run.py diagnose
python3 Ai파일/tools/prepare-tracking.py
python3 Ai파일/tools/local_ai.py --help
```

기존 `scripts/local_ai.py`, `scripts/model_stream.py`, `scripts/prepare-tracking.py`는
기존 실행 명령·테스트를 위한 짧은 연결 파일입니다. 실제 구현은 `tools/`에만 있습니다.

## 웹 코드와의 경계

웹 화면 `code/`와 웹 서버 `backend/`는 기존 위치에 유지합니다.
`backend/platform/camera_configuration.py`는 Vercel API에서도 사용하므로 여기에 옮기지 않습니다.
배포 준비 도구가 이 공유 스키마를 CPU 서비스 컨텍스트로 복사합니다.
운영 서비스 주소·환경변수·저장된 사이트 설정은 이번 폴더 정리로 변경하지 않습니다.

이 폴더 전체는 Vercel 패키징에서 제외합니다. Git에는 코드·문서만 포함하고
큰 모델·가상환경·원본 ZIP·실행 생성물·비밀키는 제외합니다.
