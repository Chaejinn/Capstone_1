# 실제 모델 파일

큰 모델 가중치를 모아 둔 곳입니다. 실행 코드·가상환경과 구분합니다.

로컬 전달 모델은 `received-2026-11-05/`에 있습니다.

| 내부 위치 | 내용 |
| --- | --- |
| `detector/rfdetr_fp32.onnx` | RF-DETR 탐지 모델 |
| `detector/export_manifest.json` | 탐지 모델 내보내기 정보 |
| `classifier/moondream2-lora/` | 추가 학습된 Moondream 어댑터·설정·학습 기록 |
| `classifier/moondream2-base/` | 어댑터와 함께 사용하는 기반 모델·토크나이저·필수 소스 |
| `classifier/model.json` | 전달받은 모델 메타데이터 |

약 3.7GB의 모델 묶음은 Git과 Vercel 배포에서 제외됩니다.
새 PC로 옮길 때 별도 복사해야 합니다. 파일 이름만 있는 README가 실제 모델을 대신하지 않습니다.
기반 모델 폴더의 README·라이선스·설정은 모델 구성의 일부이므로 유지합니다.

Modal 배포 준비본에도 실행에 필요한 모델 사본이 있습니다. 빌드에 쓰이는 복사본이므로
단순 중복으로 삭제하지 않았습니다. 이 모델 폴더만으로 600장 학습 원본·정답 라벨 전체가
확보됐다고 볼 수는 없습니다.
