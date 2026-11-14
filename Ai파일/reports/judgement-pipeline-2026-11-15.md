# 보드 없는 익수 판정 통합 검증

2026-11-15, 보드 연결 없이 수행했습니다.

## 추가한 자동 시험

[시험 코드](../services/tracking/test_judgement_pipeline.py)는 FastAPI의 실제 스트림 생성·이미지 업로드·결과 조회·종료 API, 실제 OpenCV JPEG 디코딩, 실제 PersonTracker/ByteTrack, 운영 BrowserStream/DrowningGate를 사용합니다. RF-DETR·Moondream 응답만 고정한 합성 응답입니다. 운영 서버나 하드웨어에는 요청하지 않습니다.

1. 동일 대상의 익수 점수 0.8 이상은 15번째 연속 분석 프레임에서 확정됩니다. 최초 확정 이벤트는 한 번만 생성됩니다.
2. 탐지 신뢰도 0.99라도 익수 점수가 없거나 0.79이면 확정되지 않습니다.
3. 점수 미달이나 대상 소실 후 새 관측은 1프레임부터 시작합니다.
4. 분석 오류 후 이전 누적 증거가 남지 않습니다.
5. 중복 프레임은 422로 거부되고 재연결한 스트림의 누적은 1부터 시작합니다.

확정 시 명령은 발행되지 않으며, 좌표 미보정 상태의 출동 차단도 확인했습니다. `dispatch_deadline_at` 메타데이터는 확정 시각 +3초입니다. 실제 3초 내 출동은 검증한 것이 아닙니다.

## 실행

프로젝트 루트에서:

```sh
Ai파일/local-model/.venv-tracking/bin/python -m unittest discover -s Ai파일/services/tracking -p test_judgement_pipeline.py -v
```

결과: 5개 통과. 이 테스트는 기존 CPU 추적 서비스 빌드 컨텍스트가 필요합니다. 준비 방법은 `Ai파일/services/tracking/README.md`를 참고하세요.

## 남은 현장 확인

실제 모델 정확도, 다양한 사람·대상의 이동·가림·교차, 장시간 네트워크 연결, 실제 보정 정확도는 이 합성 응답 시험으로 입증되지 않습니다. 보드 통신·추진·복귀는 포함하지 않았습니다. 제품 동작이나 운영 설정을 변경하지 않고 회귀 검증 코드를 추가한 작업입니다.
