# 임의 패킷 / 휴대폰 수신 테스트

브릿지는 별도 담당자가 제작합니다. 이 저장소는 JSON 신호를 받아 저장하는 HTTP API와,
화면을 열어 둔 휴대폰에서 1초 간격으로 신호를 조회하는 테스트 페이지를 제공합니다.
실제 구조 이벤트 생성, 보트 출동, SMS, 잠금 화면 푸시는 수행하지 않습니다.

## 담당 범위와 완료 기준

- 브릿지 담당자: 장비 패킷을 받아 아래 HTTP API로 JSON을 전송하는 프로그램 제작.
- 이 저장소: 신호 수신 API, 웹에서 임의 신호를 보내는 버튼, 휴대폰 수신 화면 제공.
- 확인 순서: PC 웹 버튼으로 먼저 검증한 뒤, 브릿지 POST로 동일한 수신 경로 검증.
- 완료 기준: 실제 휴대폰 화면에 전송한 신호 번호와 메시지가 나타나고, 소리를 켠 상태에서 알림음을 확인.

API 테스트 통과만으로 실제 휴대폰 알람 수신이 확인된 것은 아닙니다.
아래 절차로 휴대폰에서 확인한 뒤 차유비 담당자에게 결과를 전달하세요.

## 실행과 확인

Python 3.10 이상이 필요합니다. 이 저장소의 기존 `.venv`는 Python 3.9일 수 있으므로
실행할 Python의 버전을 먼저 확인하세요 (`python3 --version`).

1. 저장소 루트에서 `python3 -m uvicorn app:app --host 0.0.0.0 --port 8000` 실행.
2. PC에서 `http://127.0.0.1:8000/signal-test.html` 접속 후 기존 운영자/관리자 계정으로 로그인.
3. 같은 Wi-Fi의 휴대폰에서 `http://<PC의 LAN IP>:8000/signal-test.html` 접속 후 로그인.
   방화벽에서 8000 포트 접근을 허용해야 합니다. 휴대폰의 localhost는 휴대폰 자신입니다.
4. 휴대폰에서 '알림 소리 켜기'를 누르고 화면을 유지합니다.
5. PC에서 테스트 신호 전송. 휴대폰 수신 기록에 같은 번호/메시지가 나타나는지 확인합니다.
6. 브릿지에서 아래 POST를 호출해 같은 방법으로 확인합니다.

### 하드웨어·VLM 없이 제어 명령 테스트

서버를 재시작한 뒤 PC와 휴대폰에서 `/signal-test.html`에 로그인합니다.
PC에서 목표 X/Y(m)를 입력하고 제어 버튼을 누르면, 휴대폰에 명령 수신 기록과
마지막 제어 패킷, 서버 모의 상태가 표시됩니다. 휴대폰에서 소리를 켜 두면 알림음도 확인할 수 있습니다.
카메라·VLM·브릿지·보트는 필요하지 않습니다.

| 버튼 | 명령 | 모의 상태 |
| --- | --- | --- |
| 임의 출동명령 전송 | DISPATCH | DISPATCHED, 입력 목표 좌표 저장 |
| 비상정지 | ESTOP | STOPPED, 비상정지 유지 |
| 비상정지 해제 | CLEAR_ESTOP | IDLE, 새 출동명령 필요 |
| 출동 취소 | CANCEL | CANCELLED |
| 복귀 | RETURN | RETURNING |
| 구조망 전개 | DEPLOY | DEPLOYING |
| 구조 완료 | COMPLETE | COMPLETED |
| 테스트 초기화 | RESET | IDLE, 목표와 비상정지 초기화 |

비상정지 중에는 해제·초기화·비상정지 이외의 명령을 HTTP 409로 거부합니다.
나머지 명령은 각 상태를 독립적으로 확인할 수 있도록 자유롭게 주입할 수 있습니다.
자율 항해나 시간 경과에 따른 자동 상태 전이는 수행하지 않습니다.
초기화해도 기록은 보존됩니다. 이 모의 상태는 테스트 페이지 사용자들이 공유합니다.
동시 명령 순서를 보장하도록 로컬 서버는 기본값인 단일 프로세스(`--workers 1`)로 실행하세요.

같은 운영자/관리자 Bearer 인증으로 호출할 수 있습니다.

```http
POST /api/test-control
Authorization: Bearer <access_token>
Content-Type: application/json

{"command":"DISPATCH","target_x":5,"target_y":0}
```

비상정지는 `{"command":"ESTOP"}`, 해제는 `{"command":"CLEAR_ESTOP"}`을 전송합니다.
응답은 HTTP 201이며 `id`(신호 번호), `command_id`(제어 기록 번호), `command`,
`state`, `test:true`를 포함합니다. 좌표는 생략 시 X=5, Y=0이며 유한한 숫자여야 합니다.
알 수 없는 명령은 HTTP 422입니다.

`GET /api/test-control?latest=true`는 현재 상태와 최초 cursor를 반환합니다.
이후 `GET /api/test-control?after_id=<cursor>`를 반복하면 `packets`, `cursor`, `state`를 받습니다.
최대 100건씩 반환하며 cursor에는 **command_id**가 사용됩니다.
`/api/test-signals`에는 동일 명령의 사람이 읽을 수 있는 알림도 남습니다.
POST 성공은 서버 저장 완료이며, 실제 기기 실행이나 휴대폰 수신 확인 응답은 아닙니다.

테스트 명령은 실제 `/api/boat/command`와 분리되어 실제 보트를 구동하거나 정지시키지 않습니다.
브릿지 담당자는 `test:true` 패킷을 실제 구동에 연결하지 않고 수신 검증에 사용하면 됩니다.

소리는 브라우저·기기의 무음/음량 설정에 영향을 받습니다. 수신 기록으로 최종 확인하세요.
새로 로그인하거나 페이지를 다시 열면 기존 기록을 건너뛰고 그 이후 신호부터 받습니다.
연결이 잠시 끊긴 동안의 신호는 같은 화면에서 재연결하면 이어서 조회합니다.
각 조회는 최대 100건이며, 화면은 최근 100건을 표시합니다. 서버에는 테스트 기록이 계속 쌓입니다.

## 브릿지 담당자에게 전달할 계약

서버의 `/api/auth/login`에 `application/x-www-form-urlencoded` 형식의
`username`, `password`를 POST하면 응답의 `access_token`을 받을 수 있습니다.
토큰 만료 시 다시 로그인하세요. 운영자/관리자 계정이 필요합니다.

```http
POST /api/test-signals
Authorization: Bearer <access_token>
Content-Type: application/json

{"source":"bridge","message":"익수 감지 임의 패킷 테스트"}
```

성공: HTTP 201, 예시:

```json
{"id":1,"source":"bridge","message":"익수 감지 임의 패킷 테스트","created_at":"2026-10-24T08:00:00Z","test":true}
```

`source`는 1~80자(생략 시 bridge), `message`는 1~500자(생략 시 기본 테스트 문구).
401은 로그인 필요, 403은 권한 부족, 422는 입력 오류입니다.
POST 성공은 서버 저장 완료이며 휴대폰 수신 확인 응답은 아닙니다.
재전송 시 별도의 신호 번호가 생성됩니다.

휴대폰: `GET /api/test-signals?latest=true`로 최초 cursor를 얻은 뒤
`GET /api/test-signals?after_id=<cursor>`를 반복합니다. 두 API 모두 Bearer 토큰이 필요합니다.
응답의 `signals`를 처리하고 `cursor`를 다음 요청에 사용합니다.
HTTP 방식이므로 브릿지에서 WebSocket 구현은 필요 없습니다.
배포 환경은 영속 DB가 필요하며, 로컬에서는 기존 SQLite DB를 사용합니다.

실제 휴대폰에서 확인한 후 담당자에게 전달할 문구:
“웹 신호 수신 테스트 완료. 휴대폰에서 signal-test.html을 열어 둔 상태로
브릿지 POST 신호 번호와 메시지 수신을 확인했습니다. 잠금 화면 푸시는 별도 구현입니다.”
