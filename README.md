# Drown Guardian · 관제 플랫폼

캡스톤디자인 「Drown Guardian」요구사항정의서(SRS v1.0)를 기반으로 만든,
**실제로 동작하는** 관제 플랫폼 프론트엔드입니다. 백엔드 없이 브라우저의
`localStorage`만으로 로그인 세션·계정·사이트·설정·감사 로그를 실제로
저장/공유하므로, 여러 페이지를 오가며 상태가 실제로 유지됩니다.

## 폴더 구조 (분야별 코드 분리)
```
drown-guardian-platform/
├── index.html            운영자 · 게스트 로그인
├── admin-login.html       관리자 전용 로그인
├── site-select.html       사이트 선택
├── dashboard.html         관제 대시보드 (시뮬레이션)
├── admin.html             관리자 패널
├── css/
│   ├── common.css         공통 토큰 · 상단바 · 사이드바 · 버튼 등
│   ├── login.css          로그인 · 사이트 선택 화면
│   ├── dashboard.css      관제 대시보드 전용 스타일
│   └── admin.css          관리자 패널 전용 스타일
└── js/
    ├── auth.js             세션 · 계정 · 사이트 · 설정 · 감사로그 공통 저장소
    ├── login.js             운영자/게스트 로그인 로직
    ├── admin-login.js       관리자 로그인 로직
    ├── site-select.js       사이트 선택 로직
    ├── dashboard.js         관제 시뮬레이션 로직 (감지→판단→개입)
    └── admin.js              관리자 패널 로직 (계정/사이트/설정/로그)
```

## 참고

- 본 프로젝트는 SRS의 FR/NFR 요구사항 ID를 UI 곳곳에 태그로 표기하여
  문서와 화면을 상호 대조할 수 있게 했습니다.
- 로그인·권한 분리는 프론트엔드 시연용이며, 실제 서비스에서는 반드시
  서버 측 인증(해시된 비밀번호, 세션/토큰, HTTPS 등)으로 대체해야 합니다.
