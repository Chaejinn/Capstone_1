"""Diagnose web authentication; optionally receive commands or test USB stop only."""
import base64
import argparse
import getpass
import json
import os
import re
import runpy
import sys
import time
from pathlib import Path

import requests


def normalize_token(value):
    token = value.strip()
    try:
        parsed = json.loads(token)
        if isinstance(parsed, dict):
            token = parsed.get("token", "")
        elif isinstance(parsed, str):
            token = parsed
    except ValueError:
        pass
    if not isinstance(token, str):
        return ""
    token = token.strip().strip("\"'")
    if token.startswith("Bearer "):
        token = token[7:].strip()
    return token


def stop_only_bridge(token):
    import serial

    url = "https://drown-guardian.vercel.app/api/test-control"
    headers = {"Authorization": "Bearer " + token}
    print("STOP-ONLY: COM3 / 9600. Only ESTOP is forwarded. Ctrl+C to exit.", flush=True)
    with serial.Serial("COM3", 9600, timeout=0.3, write_timeout=1) as board:
        def send_stop():
            board.write(b"S\n")
            board.flush()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                reply = board.readline().decode("ascii", errors="replace").strip()
                if reply:
                    print("BOARD: " + reply, flush=True)
                if reply == "OK S":
                    return True
            print("STOP ACK NOT RECEIVED", flush=True)
            return False

        try:
            time.sleep(4)
            board.reset_input_buffer()
            if not send_stop():
                return
            response = requests.get(url, headers=headers, params={"latest": "true"}, timeout=10)
            response.raise_for_status()
            cursor = response.json()["cursor"]
            print("WEB READY. Press ESTOP on the signal test page.", flush=True)
            while True:
                response = requests.get(url, headers=headers, params={"after_id": cursor}, timeout=5)
                response.raise_for_status()
                data = response.json()
                for packet in data["packets"]:
                    if packet["command"] == "ESTOP":
                        print("WEB ESTOP -> USB S", flush=True)
                        if not send_stop():
                            return
                    else:
                        print("WEB COMMAND BLOCKED (stop-only mode)", flush=True)
                cursor = data["cursor"]
                time.sleep(0.2)
        except KeyboardInterrupt:
            print("Stopping.", flush=True)
        except (requests.RequestException, ValueError, KeyError, serial.SerialException):
            print("CONNECTION_OR_RESPONSE_ERROR; ending stop-only bridge.", flush=True)
        finally:
            send_stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login", action="store_true", help="Log in directly without copying a token")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Stop automatic tests, then receive commands without opening a serial port")
    mode.add_argument("--stop-only", action="store_true", help="Forward only ESTOP to COM3 and verify OK S")
    args = parser.parse_args()
    token = normalize_token(os.environ.get("DG_BRIDGE_TOKEN", ""))
    if args.login:
        username = input("Web login ID: ").strip()
        password = getpass.getpass("Web password (hidden): ")
        try:
            response = requests.post(
                "https://drown-guardian.vercel.app/api/auth/login",
                data={"username": username, "password": password},
                timeout=20,
                allow_redirects=False,
            )
            print("LOGIN: HTTP " + str(response.status_code))
            if response.status_code != 200:
                return
            token = normalize_token(response.json().get("access_token", ""))
        except (requests.RequestException, ValueError, AttributeError):
            print("LOGIN_NETWORK_OR_RESPONSE_ERROR")
            return
        finally:
            password = None
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
        print("Copy the token in your browser, then paste it at the prompt below.")
        try:
            token = normalize_token(getpass.getpass("Token (hidden): "))
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", token):
        print("TOKEN_FORMAT_INVALID: token is missing, incomplete, or contains extra text.")
        return
    try:
        part = token.split(".")[1]
        payload = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
        expires = payload.get("exp")
        if not isinstance(expires, (int, float)):
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        print("TOKEN_PAYLOAD_INVALID")
        return
    # Decoding is diagnostic only; the server verifies the signature.
    print("TOKEN_EXPIRED" if expires <= time.time() else "TOKEN_NOT_EXPIRED_LOCALLY")
    for path in ("/auth/me", "/test-control?latest=true"):
        try:
            response = requests.get(
                "https://drown-guardian.vercel.app/api" + path,
                headers={"Authorization": "Bearer " + token},
                timeout=15,
                allow_redirects=False,
            )
            print(path.split("?")[0] + ": HTTP " + str(response.status_code))
            if response.status_code != 200:
                return
        except requests.RequestException:
            print(path.split("?")[0] + ": NETWORK_ERROR")
            return
    if args.dry_run or args.stop_only:
        headers = {"Authorization": "Bearer " + token}
        base = "https://drown-guardian.vercel.app/api/test-control/auto"
        try:
            stopped = requests.post(base + "/stop", headers=headers, timeout=15, allow_redirects=False)
            stopped.raise_for_status()
            status = requests.get(base, headers=headers, timeout=15, allow_redirects=False)
            status.raise_for_status()
            if status.json().get("running") is not False:
                print("AUTO_STOP_NOT_CONFIRMED; dry run not started.")
                return
        except (requests.RequestException, ValueError, AttributeError):
            print("AUTO_STOP_CHECK_FAILED; dry run not started.")
            return
        if args.stop_only:
            print("AUTO_STOP_CONFIRMED.")
            stop_only_bridge(token)
            return
        print("AUTO_STOP_CONFIRMED. DRY RUN ONLY; no serial connection. Ctrl+C to stop.")
        previous_token = os.environ.get("DG_BRIDGE_TOKEN")
        previous_argv = sys.argv
        try:
            os.environ["DG_BRIDGE_TOKEN"] = token
            sys.argv = ["signal_bridge.py", "--dry-run"]
            runpy.run_path(str(Path(__file__).resolve().parents[1] / "signal_bridge.py"), run_name="__main__")
        finally:
            sys.argv = previous_argv
            if previous_token is None:
                os.environ.pop("DG_BRIDGE_TOKEN", None)
            else:
                os.environ["DG_BRIDGE_TOKEN"] = previous_token


if __name__ == "__main__":
    main()
