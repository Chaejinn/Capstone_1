# 관리 도구

모든 명령은 저장소 최상위 폴더에서 실행합니다.

| 파일 | 역할 |
| --- | --- |
| `build-vercel.py` | `code/`의 배포 파일을 `public/`으로 복사 |
| `build_aruco_dictionaries.py` | 브라우저용 ArUco 사전 생성 |
| `auto-git-sync.sh` | main 브랜치 변경을 두 GitHub 원격에 자동 커밋·푸시 |
| `local_ai.py`, `model_stream.py`, `prepare-tracking.py` | AI 담당 폴더의 도구를 실행하는 기존 호환 진입점 |

실제 보드 연결 프로그램은 [hardware/bridges/](../hardware/README.md)에 있습니다.
일회성 인증 점검·로컬 USB 추진 테스트 스크립트는 정리했습니다.
