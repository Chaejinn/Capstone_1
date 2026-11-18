# AI 실행 도구

프로젝트 최상위 폴더에서 실행합니다.

| 파일 | 역할 |
| --- | --- |
| `local_ai.py` | 로컬 AI API와 웹을 함께 실행하는 통합 도구 |
| `model_stream.py` | 로컬 분석 이미지의 최신 프레임을 웹으로 중계 |
| `prepare-tracking.py` | 현재 추적 코드와 공유 설정을 로컬 Modal 빌드 준비본에 복사 |

```sh
python3 Ai파일/tools/local_ai.py --help
python3 Ai파일/tools/model_stream.py --help
python3 Ai파일/tools/prepare-tracking.py
```

`local_ai.py --check`는 모델·패키지·환경변수 준비 상태를 확인합니다.
현재 사용하려는 원본 저장소 버전에 따라 ONNX 출력과 모델 메타데이터를 추가 준비해야 할 수 있습니다.
준비 완료 여부와 실제 추론 성공은 별도로 확인합니다.

`prepare-tracking.py`는 로컬 파일만 갱신합니다. 운영 Modal 배포 명령은 자동 실행하지 않습니다.
기존 `scripts/`의 같은 이름 연결 파일은 제거했으므로 위 경로를 사용하세요.

영상 중계 검사: `python3 -m unittest discover -s Ai파일/tools/tests -q`
