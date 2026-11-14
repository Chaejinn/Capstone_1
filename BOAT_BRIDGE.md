# 실제 보트 LAN 연결

단일 프로세스로 실행합니다. 메모리 명령 상태를 공유해야 하므로 --workers를 늘리지 마세요.

```sh
python -m pip install -r requirements.txt numpy
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

Windows CMD:

```bat
set DG_CMD_URL=http://<Mac Wi-Fi IP>:8000/api/boat/command
python bridge.py
```

- GET `/api/boat/command`: `{"throttle":35,"rudder":0,"net":null,"estop":false}` (인증 없는 로컬 Wi-Fi 장치 API)
- POST `/api/boat/pose`: `{"x":0,"y":0,"yaw_deg":0,"target_x":5,"target_y":0}`
- 좌표는 호모그래피 변환 후 미터, yaw_deg는 +X 기준 +Y 방향으로 증가하는 각도입니다. 카메라 파트에서 동일 좌표계로 변환합니다.
- PID: Kp=0.8, Ki=0, Kd=0.15; 적분항 누적·제한과 조향 포화 시 누적 방지(anti-windup)를 지원합니다. Ki 기본값은 기존의 0을 유지하며 실측 튜닝 전 임의로 활성화하지 않습니다. 실제 수신 간격으로 미분하며 방향 오차는 ±180도로 정규화합니다. 방향타는 ±35도, 추진은 35입니다. 부호는 실물 테스트로 확정합니다.
- 목표 0.4m 이내: 추진/방향타 0, net=150. 위치가 1.5초 이상 갱신되지 않으면 일반 정지합니다.
- 비상정지는 래치됩니다. 해제 전 pose가 들어와도 estop=true이고 추진/방향타 0, net=null입니다. 해제 후 새 pose가 필요합니다.
- 브릿지가 10Hz 조회하고 $D/$N/$S 변환, XOR, seq 0~9999 순환, 3회 반복, HC-06 38400bps를 담당합니다. 서버는 JSON만 제공합니다.
- 상태를 유지하는 로컬 서버용입니다. Vercel 다중 인스턴스에 실제 보트 제어를 연결하지 마세요.
- POST `/api/boat/estop`, `/api/boat/estop/clear`: 대시보드 STOP/해제 연동.


## HC-06 웹 신호 브릿지 (signal_bridge.py)

위 LAN PID 브릿지와 별개로 웹 `/api/test-control` 버튼을 읽어 HC-06에 전달합니다.
현재 RETURN은 정지 명령이며 좌표 기반 복귀·PID 조향을 수행하지 않습니다.

macOS에서 준비:

```sh
python3 -m venv .venv-bridge
.venv-bridge/bin/python -m pip install requests pyserial
.venv-bridge/bin/python signal_bridge.py --list-ports
```

기존 PC 연결을 종료하고 Mac Bluetooth에서 HC-06을 페어링한 뒤 나타나는
`/dev/cu.…` 송신 포트를 사용합니다. Bluetooth-Incoming-Port는 HC-06 전용 포트가 아닙니다.
발급받은 현재 로그인 토큰은 `DG_BRIDGE_TOKEN` 환경변수에만 설정하며 소스에 저장하지 않습니다.

```sh
.venv-bridge/bin/python signal_bridge.py --check-web
.venv-bridge/bin/python signal_bridge.py --port /dev/cu.HC-06-DevB --baud 9600
```

포트 이름은 예시입니다. 실제 `--list-ports` 결과를 사용합니다. `--check-web`은 장치를 열거나
명령을 생성하지 않습니다. 실제 실행은 처음 정지 명령을 전송하고 이전 웹 명령은 건너뜁니다.
웹 인증 실패·통신 단절·종료 시 정지하도록 구현되어 있습니다. 실제 보드 수신·정지 여부는 현장 검증이 필요합니다.
