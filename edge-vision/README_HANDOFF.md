# Drown Guardian 호모그래피 · ArUco 도구 (전달용)

만든 날짜: 2026-11-11 15:44 / 저장소 커밋: 3cb525d

## 설치 (Python 3.12 이상)
    pip install opencv-python numpy pyyaml pillow

## 실행 (이 폴더에서)
    python scripts/homography/calibration_editor.py homography   # 호모그래피 편집기
    python scripts/aruco/aruco_check.py                          # 마커 검출·헤딩 점검
    python scripts/aruco/pose_check.py                           # 마커 + 호모그래피 위치 점검
    python scripts/aruco/make_aruco_marker.py                    # 인쇄용 마커(A4, 5/10 cm)
카메라 번호가 0이 아니면 --camera-index 1 처럼 붙인다. 다른 프로그램이 카메라를 쓰고 있으면 열리지 않는다.

## 편집기 키
1~4 점 선택 / 드래그·방향키 이동 / g 격자 / b 보드 위치 찍기 / d 익수자 위치 찍기 / x 측정점 지우기
s 저장 / Esc 취소 / h 도움말

## 좌표 규약 (웹과 동일)
- 단위 m, 원점 = 수조 왼쪽 아래, +X 오른쪽, +Y 위. 수조 0.30 x 0.45 m (calibration/homography.yaml).
- 화면 격자 0~1000 은 표시용(X 1000 = 가로, Y 1000 = 세로). 계산·전송 값은 m.
- 헤딩: 0도 = +X, 반시계 증가. 마커 위쪽 변 = 보드 선수 방향.
- 마커: DICT_4X4_50, ID 0, 크기 5 cm(standin) / 10 cm(boat) (configs/aruco.yaml).

## 주의 (이 묶음 기준 상태)
- calibration/homography.yaml 의 4점은 아직 재보정 전 값이다(편집기가 "시계 방향 아님", "비율 불일치"로 표시).
  편집기에서 4점을 맞추고 s 로 저장해야 올바른 행렬이 된다.
- configs/aruco.yaml 의 heading_offset_deg 는 아직 null(미측정)이다. aruco_check.py --write 로 측정한다.
- 이 도구들은 측정만 한다. 보트 제어 명령을 만들거나 웹으로 보내지 않는다.
