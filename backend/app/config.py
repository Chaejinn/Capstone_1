"""
설정값 — 환경변수로 덮어쓸 수 있음.
NFR-ARC-001(외부 인터넷 없이 로컬 Wi-Fi AP 안에서 전 구간 동작)에 맞춰
기본값만으로 완전히 로컬에서 기동 가능하게 한다.

설계명세서 v0.2 §1.3.2 지연 예산: 익수 성립→출동 명령 3.0초
(스크리닝 0.8s + VLM 1.5s + 누적판정/이벤트생성 0.2s + 프레임획득 0.1s + 예비 0.4s)
"""
import os

from backend.platform.config import DATABASE_URL, IS_VERCEL

# FR-JDG-004 판정 임계값 기본값 (config_snapshot 최초 시드값)
DEFAULT_CONF_THRESHOLD = 0.90
DEFAULT_PERSIST_FRAMES = 15
DEFAULT_WINDOW_N = 8
DEFAULT_VLM_TIMEOUT_S = 1.5

# 규모 제약: 카메라 1대 · 보드 1대 (§1.3.1 "규모" 제약사항)
BOARD_ID = "BOARD-01"

# 통신 사양 (§2.4.1)
GUIDE_HZ = 12.0                 # 서버 → 보드 유도 명령 주기 (10~15Hz)
TELEM_HZ = 3.0                  # 보드 → 서버 텔레메트리 주기 (2~5Hz)
LINK_TIMEOUT_SEC = 0.5          # 0.5초 미수신 시 페일세이프 (EX-01)
LINK_LOST_HARD_SEC = 2.0        # 2초 이상 소실 시 TRACK_LOST (EX-03)

# 안전
ESTOP_TARGET_LATENCY_SEC = 0.5  # NF-P-02: 입력→추진정지 0.5초 이내
CANCEL_GRACE_SEC = 3.0          # 출동 발행 후 3초 이내 취소 가능 (EX-12)

# 데이터 보관 (§2.1)
RETENTION_DAYS = 30
RETENTION_MAX_GB = 20

# ROI 유효성 (EX-15)
ROI_MIN_POINTS = 3
CALIB_MAX_REPROJ_ERROR_M = 0.15
