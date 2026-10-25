# Drown Guardian · 관제 플랫폼 (프론트엔드 프로토타입)

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

- 관리자 로그인 페이지(`admin-login.html`)는 일반 로그인 화면(`index.html`)에
  **링크로 노출되지 않습니다.** 가입하지 않은 방문자·게스트는 이 페이지의 존재를
  UI 상에서 알 수 없고, 설령 URL로 직접 접근하거나 `admin.html`을 열더라도
  `js/auth.js`의 `dgRequireRole(['admin'])` 가드에 의해 실제 관리자 계정으로
  로그인하지 않으면 즉시 로그인 페이지로 리다이렉트됩니다.
- 관리자 패널의 **계정 관리**에서 새 운영자 계정을 추가하면,
  즉시 `index.html`에서 그 계정으로 로그인할 수 있습니다 (실제 연동).
- 실제 배포 시에는 `js/auth.js`의 `DG.ADMIN` 하드코딩 값을 서버 측 인증으로
  반드시 교체하세요 (프론트엔드 코드에 있는 값은 브라우저에서 열람 가능합니다).

## 코드 수정 포인트

- **디자인 토큰(색상/폰트)**: `css/common.css` 상단 `:root` 변수
- **시뮬레이션 속도/로직**: `js/dashboard.js`의 `tick()` 함수
- **판정 임계값 기본값**: 관리자 패널(`admin.html` → 설정) 또는 `js/auth.js`의 `dgSeed()`
- **사이트 목록**: `js/auth.js`의 `dgSeed()` 내 `DG.KEYS.sites` 초기값, 또는 관리자 패널에서 직접 추가

## 참고

### GitHub 자동 반영

VS Code에서 이 폴더를 열면 `scripts/auto-git-sync.sh`가 변경을 감시하고
약 5~10초 후 커밋하여 아래 두 저장소의 `main`에 각각 푸시합니다.

- `origin`: https://github.com/Chaejinn/Capstone_1.git
- `drownguardian`: https://github.com/DrownGuardian/Web-Platform.git

새로 복제한 환경에서는 `git remote -v`를 확인하고, 없는 원격을 위 이름과 URL로
`git remote add <이름> <URL>`로 등록하세요. 두 저장소의 쓰기 권한이 필요합니다.
한쪽 푸시가 실패해도 다른 쪽은 처리하며, 실패한 쪽은 다음 주기에 재시도합니다.
원격의 다른 변경을 자동으로 pull하거나 강제 푸시하지 않으므로 이력이 갈라지면 수동 병합이 필요합니다.
병합·리베이스 중이거나 `main` 이외의 브랜치에서는 자동 반영을 멈춥니다.
VS Code 작업을 종료하면 감시도 종료됩니다.

- 본 프로젝트는 SRS의 FR/NFR 요구사항 ID를 UI 곳곳에 태그로 표기하여
  문서와 화면을 상호 대조할 수 있게 했습니다.
- 로그인·권한 분리는 프론트엔드 시연용이며, 실제 서비스에서는 반드시
  서버 측 인증(해시된 비밀번호, 세션/토큰, HTTPS 등)으로 대체해야 합니다.
