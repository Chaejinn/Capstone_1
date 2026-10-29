"""웹 test-control → HC-06 → 보드. 새 명령만 전달한다.

설치: python -m pip install requests pyserial
환경변수: DG_BRIDGE_TOKEN (JWT 또는 Bearer JWT), DG_BRIDGE_PORT (기본 COM4)
테스트: python signal_bridge.py --dry-run
RETURN은 현재 정지만 수행한다. CLEAR_ESTOP의 보드 해제 동작은 펌웨어 확인 필요.
"""
import argparse
import os
import threading
import time

import requests

CONTROL_URL = "https://drown-guardian.vercel.app/api/test-control"
PORT = os.environ.get("DG_BRIDGE_PORT", "COM4")
DISPATCH_THROTTLE = 20
NET_DEPLOY_ANGLE = 90
NET_RESET_ANGLE = 50
KEEPALIVE_SEC = 0.5
POLL_SEC = 0.2


class Board:
    def __init__(self, serial_port):
        self.serial = serial_port
        self.lock = threading.Lock()
        self.driving = False
        self.failure = None

    def _write(self, line):
        if self.serial is not None:
            self.serial.write((line + "\n").encode("ascii"))

    def command(self, cmd):
        with self.lock:
            self.driving = False
            if cmd == "DISPATCH":
                lines = [f"M,{DISPATCH_THROTTLE},0"]
            elif cmd == "ESTOP":
                lines = ["S"]
            elif cmd == "DEPLOY":
                lines = ["M,0,0", f"F,{NET_DEPLOY_ANGLE}"]
            elif cmd == "RESET":
                lines = ["M,0,0", f"F,{NET_RESET_ANGLE}"]
            elif cmd in ("CLEAR_ESTOP", "CANCEL", "RETURN", "COMPLETE"):
                lines = ["M,0,0"]
            else:
                raise ValueError(f"알 수 없는 명령: {cmd}")
            for line in lines:
                print(f"   → {line}")
                self._write(line)
            self.driving = cmd == "DISPATCH"

    def stop(self):
        with self.lock:
            self.driving = False
            self._write("M,0,0")

    def keepalive(self, shutdown):
        while not shutdown.wait(KEEPALIVE_SEC):
            with self.lock:
                if not self.driving:
                    continue
                try:
                    self._write(f"M,{DISPATCH_THROTTLE},0")
                except Exception as exc:
                    self.driving = False
                    self.failure = exc
                    shutdown.set()
                    return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("DG_BRIDGE_TOKEN", "").strip()
    if not token:
        parser.error("DG_BRIDGE_TOKEN 환경변수에 토큰을 설정하세요.")
    auth = token if token.startswith("Bearer ") else f"Bearer {token}"

    serial_port = None
    board = None
    worker = None
    shutdown = threading.Event()
    http = requests.Session()
    http.headers["Authorization"] = auth
    try:
        if not args.dry_run:
            import serial
            serial_port = serial.Serial(PORT, 9600, timeout=0.2, write_timeout=0.5)
            time.sleep(2)
        board = Board(serial_port)
        board.stop()
        worker = threading.Thread(target=board.keepalive, args=(shutdown,), daemon=True)
        worker.start()
        cursor = None
        print(f"시작: {CONTROL_URL}  DRY_RUN={args.dry_run}")
        while not shutdown.is_set():
            try:
                params = {"latest": "true"} if cursor is None else {"after_id": cursor}
                response = http.get(CONTROL_URL, params=params, timeout=2)
                response.raise_for_status()
                data = response.json()
            except (requests.RequestException, ValueError) as exc:
                board.stop()
                print(f"조회 실패 (주행 정지): {exc}")
                if isinstance(exc, requests.HTTPError) and exc.response.status_code in (401, 403):
                    print("토큰 또는 계정 권한을 확인한 후 다시 실행하세요.")
                    break
                # 연결 복구 시 끊긴 동안의 명령은 실행하지 않는다.
                cursor = None
                shutdown.wait(1)
                continue

            if shutdown.is_set():
                break
            if cursor is None:
                cursor = data["cursor"]
                print(f"지난 기록 건너뜀 (cursor={cursor}). 버튼 대기 중")
            else:
                for item in data["packets"]:
                    print(f"새 명령 #{item['command_id']}: {item['command']}")
                    board.command(item["command"])
                cursor = data["cursor"]
            shutdown.wait(POLL_SEC)
        if board.failure is not None:
            raise RuntimeError("블루투스 전송 실패") from board.failure
    except KeyboardInterrupt:
        print("종료")
    finally:
        shutdown.set()
        if worker is not None:
            worker.join()
        try:
            if board is not None:
                board.command("ESTOP")
        finally:
            if serial_port is not None:
                serial_port.close()
            http.close()


if __name__ == "__main__":
    main()
