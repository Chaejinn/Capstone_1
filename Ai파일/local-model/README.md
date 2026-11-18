# 이 Mac의 AI 실행 환경

모델 가중치는 [../models/](../models/README.md)에 분리했습니다.
이 폴더에는 실행·배포에 필요한 원본 소스와 로컬 환경이 있습니다.

| 위치 | 용도 |
| --- | --- |
| `Detective-model/` | AI 담당자 GitHub 저장소의 별도 체크아웃. 이력과 내부 파일 구조 유지 |
| `modal-moondream2-deploy/` | 실제 Modal 배포에 사용한 소스·필수 모델·의존 코드의 빌드 준비본 |
| `.venv-modal/` | 이 Mac의 Modal CLI 환경 |
| `.venv-tracking/` | 이 Mac의 CPU 추적 검사 환경 |

이름이 `local-model`인 경로는 기존 배포·검사와 가상환경의 실행 경로를 유지하기 위한 것입니다.
가상환경을 그대로 다른 PC로 복사하지 말고 해당 운영체제에서 다시 설치하세요.

개발 원본은 `services/tracking/`이며 `tools/prepare-tracking.py`로 배포 준비본을 갱신합니다.
준비본에는 별도 원본 저장소의 과거 리비전과 GPU 추론 코드도 필요하므로 통째로 지우지 않았습니다.
배포 준비본은 현재 원본 체크아웃과 완전히 같은 사본이라고 간주하면 안 됩니다.

큰 실행 폴더와 가상환경은 Git에 포함하지 않습니다. 이 안내서만 Git으로 공유합니다.
