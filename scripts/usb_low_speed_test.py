"""One bounded USB steering/throttle test; no web command polling."""
import time

import serial


def main():
    print("Close the previous stop-only bridge with Ctrl+C. Waiting for COM3...", flush=True)
    deadline = time.monotonic() + 120
    while True:
        try:
            board = serial.Serial("COM3", 9600, timeout=0.1, write_timeout=0.3)
            break
        except serial.SerialException:
            if time.monotonic() >= deadline:
                print("COM3 unavailable. No test performed.")
                return
            time.sleep(1)

    def command(line, expected):
        board.write((line + "\n").encode("ascii"))
        board.flush()
        end = time.monotonic() + 1
        while time.monotonic() < end:
            reply = board.readline().decode("ascii", errors="replace").strip()
            if reply:
                print("BOARD: " + reply, flush=True)
            if reply == expected:
                return
        raise RuntimeError("Expected acknowledgement not received; stopping test.")

    try:
        time.sleep(4)
        board.reset_input_buffer()
        command("S", "OK S")
        print("RUDDER +5, throttle 0", flush=True)
        command("M,0,5", "OK M 0 5")
        time.sleep(1)
        print("RUDDER -5, throttle 0", flush=True)
        command("M,0,-5", "OK M 0 -5")
        time.sleep(1)
        command("S", "OK S")
        print("THROTTLE 5% for at most 0.5s; rudder centered", flush=True)
        # Do not wait for an acknowledgement before ending the bounded pulse.
        board.write(b"M,5,0\n")
        board.flush()
        time.sleep(0.5)
        command("S", "OK S")
        print("TEST COMPLETE. Verify physical movement separately.", flush=True)
    except KeyboardInterrupt:
        print("Interrupted; stopping.", flush=True)
    except (serial.SerialException, RuntimeError) as exc:
        print(type(exc).__name__ + ": test aborted.", flush=True)
    finally:
        try:
            command("S", "OK S")
        except (serial.SerialException, RuntimeError):
            print("STOP ACK MISSING: check the board physically.", flush=True)
        finally:
            board.close()


if __name__ == "__main__":
    main()
