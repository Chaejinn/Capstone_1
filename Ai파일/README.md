# AI 파일 안내

AI 담당자에게 받은 자료와 이후 수정한 AI 코드를 모은 폴더입니다.
**웹 화면은 `code/`, 웹 서버는 `backend/`, AI 관련 자료는 이 폴더**에서 관리합니다.

## 무엇을 찾으시나요?

| 하고 싶은 일 | 열어 볼 곳 |
| --- | --- |
| 실제 모델 파일 확인 | [models/](models/README.md) |
| RF-DETR·Moondream 원본 소스 확인 | [local-model/](local-model/README.md) |
| 카메라 보정·ArUco 도구 실행 | [edge-vision/](edge-vision/README.md) |
| Modal 추적 서버 수정 | [services/tracking/](services/tracking/README.md) |
| 로컬 AI·영상 중계·배포 준비 실행 | [tools/](tools/README.md) |
| 연결 방법·성능·검증 기록 확인 | [docs/](docs/README.md) |
| 모델 최적화 변경점 확인 | [patches/](patches/README.md) |

## 빠르게 시작하기

아래 명령은 프로젝트 최상위 폴더에서 실행합니다.

```sh
# 도움말만 확인합니다. 모델·카메라를 실행하지 않습니다.
python3 Ai파일/tools/local_ai.py --help
python3 Ai파일/tools/model_stream.py --help

# CPU 추적 서비스의 로컬 배포 준비본을 갱신합니다. 운영 배포는 하지 않습니다.
python3 Ai파일/tools/prepare-tracking.py
```

보정 도구 설치·실행은 [카메라 PC 안내](edge-vision/README.md)를 참고하세요.
로컬 AI 패키지는 `Ai파일/requirements-local-ai.txt`에 있습니다.
웹과 AI를 함께 실행하는 로컬 통합 도구여서 웹 패키지 목록도 참조합니다.

## Git과 배포

- Git에 포함: 개발 코드, 설정 형식, 테스트, 설명서, 패치
- Git에서 제외: 큰 모델, 별도 원본 저장소, 배포 준비본, 가상환경, 비밀키, 실행 생성물
- `models/`와 `local-model/`은 새 PC에 Git만 받아서는 채워지지 않습니다. 필요한 파일을 별도로 전달해야 합니다.
- 이 폴더 전체는 Vercel 웹 배포에서 제외합니다. Modal AI 배포는 별도로 진행합니다.
- 웹·AI가 함께 쓰는 설정 규약은 `backend/platform/camera_configuration.py`에 있습니다. 배포 준비 도구가 AI 빌드에 복사합니다.

정리 과정에서 모델 가중치나 측정된 보정값은 삭제하지 않았습니다.
삭제·이동 내역은 [AI 파일 정리 내역](docs/파일정리.md)에 있습니다.
