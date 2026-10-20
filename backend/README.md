# Drown Guardian 통합 백엔드

저장소 루트에서 실행합니다.

```sh
python3 -m pip install -r requirements.txt
python3 -m pip install opencv-python
python3 -m uvicorn app:app --host 127.0.0.1 --port 8000
```

`app/main.py`가 인증·관리자·카메라(`platform/`)와 판단·미션·보트(`app/`)를
하나의 FastAPI 앱으로 제공합니다. DB 연결과 메타데이터도 공유합니다.
`backend(org)`는 참고 원본이며 런타임 의존성이 없습니다.

- 화면: http://127.0.0.1:8000/
- API 문서: http://127.0.0.1:8000/api/docs
- 상세 경로 및 배포: 저장소 루트의 `DEPLOYMENT.md`

카메라 영상 수신과 AI 추론은 별도 기능입니다. 외부 AI 서비스 설정이 없으면
로컬 영상은 볼 수 있지만 실제 AI 판정은 수행하지 않습니다.
판단 서버의 기본 보드 통신은 시뮬레이션이며 실제 보트 API는 `/api/boat`입니다.
