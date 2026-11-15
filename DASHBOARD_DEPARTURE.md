# Windows USB departure from the deployed dashboard

This connects verified live browser-camera drowning confirmations to one bounded
departure on Arduino Uno, COM3 at 9600 baud, site `chunjeon`. It is a straight
departure demonstration: throttle 5%, rudder centered, at most 3 seconds. It does
not navigate to a target, deploy the net, return home, or complete a rescue.

After deploying this revision, close other programs using COM3 and run:

```powershell
.\.venv-bridge\Scripts\python.exe scripts/dashboard_departure_bridge.py
```

Enter the deployed web account ID and password locally. The password is hidden;
credentials and tokens are not saved. Wait for `BOARD: OK S` and `ARMED`.
Opening USB can reset the board and move servos to firmware startup positions.

In the deployed dashboard, select the same site and connect the camera. Save
real homography calibration first. The model must report a fresh confirmation,
drowning score >=0.8 for >=15 consecutive frames, with valid real coordinates.
The API fetches the model result itself and must receive confirmation within
3 seconds. A live bridge lease is required. There is one departure per local
arming session, with persistent deduplication per stream/generation/track.

Expected bridge output: `DEPARTURE`, `BOARD: OK M 5 0`, then
`DEPARTURE LIMIT: STOP` and `BOARD: OK S`. Observe physical movement separately.
The dashboard log means the server issued the command, not that motion was
observed or that rescue completed. There is no calibrated speed or distance.

Dashboard emergency stop, camera disconnect, or configuration reset sends a
latched stop. Ctrl+C, HTTP failure, serial failure, lease expiry, or departure
timeout stops motion. The independent local watchdog stops at the deadline even
if an HTTP request is pending; firmware also has a 1.5 second communication
failsafe. Restart the bridge locally to arm another departure. Do not restart
while stale confirmed targets remain visible: begin a new camera session.

The `/api/board-control` mailbox uses PostgreSQL-backed channel and receipt tables
created during startup. It is separate from `/api/test-control`; random/manual
signal-test commands never drive this bridge. The Arduino `S` command stops
propulsion and centers steering but does not stop net servos or latch firmware.
The software bridge supplies the stop latch. Full PID navigation remains separate.

## Explicit simulated confirmation

With the bridge armed, the dashboard button `모의 익수 판정 · 실제 보드 3초 출동`
issues one clearly marked simulated command through `/api/board-control/simulate`.
It does not require a camera or calibration, does not fabricate model scores,
and does not create a real AI judgement or rescue event. It does move the board
at 5% throttle for at most 3 seconds. The same lease, stop latch, one-departure
limit, and local watchdog apply. This verifies command delivery and motion,
not AI accuracy, real drowning detection, steering, or rescue completion.
