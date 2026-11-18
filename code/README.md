# 웹 화면

브라우저에 보이는 화면의 원본입니다. HTML은 화면 구성, CSS는 모양, JS는 동작을 담당합니다.

| 파일·폴더 | 역할 |
| --- | --- |
| `index.html` | 기본 로그인 화면 |
| `admin-login.html`, `admin.html` | 관리자 로그인·관리 화면 |
| `signup.html`, `site-select.html` | 회원가입·사이트 선택 |
| `dashboard.html` | 관제·카메라·보정 설정·보드 상태 |
| `camera-ai.html` | 같은 관제로 연결하는 기존 호환 경로 |
| `signal-test.html` | 기존 별도 신호 페이지 호환 경로. 현재 조작부는 관제에 포함 |
| `css/` | 화면별 스타일 |
| `js/` | 로그인·카메라·ROI·호모그래피·ArUco·신호 조작 |
| `js/vendor/` | 외부 라이브러리와 필수 라이선스 |
| `signal-sw.js`, `signal-test.webmanifest` | 기존 별도 신호 페이지의 설치·캐시 지원 |

로그인·권한·저장은 서버 API를 사용합니다. HTML만 직접 열거나 Live Server로 열면 API 연동이 완성되지 않습니다.
저장소 최상위에서 실행하는 방법은 [웹 실행 안내](../docs/운영배포.md)를 참고하세요.
