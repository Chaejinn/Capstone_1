# 기능 검사

실제 보드나 카메라를 연결하지 않고 코드의 주요 동작을 검사하는 파일입니다.
삭제해도 되는 캐시가 아니라, 수정 후 오류를 확인하는 개발 자료입니다.

| 파일 이름 | 확인하는 부분 |
| --- | --- |
| `test-auth.mjs`, `test_deployment.py` | 인증·웹/API 연결 |
| `test-camera.mjs`, `test-roi-camera.mjs`, `test-vision-settings.mjs` | 카메라·ROI·보정 설정 |
| `test-live-aruco*.mjs` | 실시간 마커·좌표·거리 |
| `test-dashboard-signal-test.mjs`, `test_dashboard_departure.py` | 관제 신호 패널·USB 출동 명령 |
| `test_edge*.py`, `test-edge-camera.mjs` | 로컬 AI 결과 수신 |
| `test_drowning_gate.py`, `test_monitoring_roi.py` | 판정 누적·ROI 제한 |
| 나머지 `test_*.py` | 서버·미션·진단·기존 API 호환 |

JavaScript 검사는 Node.js, Python 검사는 해당 Python 패키지가 필요합니다.
USB 브릿지를 가져오는 검사는 `hardware/requirements.txt`의 패키지도 필요합니다.
ArUco 합성 이미지 검사 전에 `python tests/build_live_aruco_fixtures.py`를 실행합니다.
