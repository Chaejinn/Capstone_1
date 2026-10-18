"""
BoardLink — class_srv.puml "comm" 패키지.
실제 배치에서는 UDP :5005(유도)/:5006(텔레메트리)로 라즈베리파이 board_agent와 통신한다
(§2.4.1). 하드웨어가 없는 개발 단계에서는 시뮬레이션으로 대체하되, 인터페이스는 동일하게 둬서
실제 BoardLink로 교체할 때 GuidanceController/CommandBus 쪽 코드는 손대지 않아도 되게 한다.
"""
import math
from dataclasses import dataclass


@dataclass
class BoardTelemetry:
    state: str = "IDLE"          # IDLE|NAVIGATING|TERMINAL_APPROACH|ALIGNING|DEPLOYING|HOLDING|ESTOP|FAILSAFE
    prev_state: str = "IDLE"
    x: float = 0.0
    y: float = 0.0
    yaw_deg: float = 0.0
    dist_cm: float | None = None
    battery_v: float = 7.9
    pwm: int = 0
    last_cmd_seq: int = 0
    faults: list | None = None


class SimulatedBoardLink:
    """실제 UDP 소켓 대신, 물리적으로 그럴듯한 속도로 보드 위치를 시뮬레이션한다."""

    SPEED_MPS = 1.2  # 시뮬레이션 이동 속도

    def __init__(self):
        self.seq = 0
        self.telemetry = BoardTelemetry()

    def reset(self, x: float = 0.0, y: float = 0.0):
        self.telemetry = BoardTelemetry(x=x, y=y)
        self.seq = 0

    def send_guide(self, heading_error_deg: float, speed: float):
        self.seq += 1
        self.telemetry.yaw_deg = (self.telemetry.yaw_deg + heading_error_deg * 0.3) % 360
        self.telemetry.pwm = int(speed * 255)
        self.telemetry.last_cmd_seq = self.seq
        if self.telemetry.state not in ("ESTOP", "FAILSAFE"):
            self.telemetry.state = "NAVIGATING"

    def step_toward(self, target_x: float, target_y: float, dt: float) -> float:
        """dt초 동안 목표를 향해 이동시키고 남은 거리(m)를 반환."""
        dx, dy = target_x - self.telemetry.x, target_y - self.telemetry.y
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return 0.0
        step = min(dist, self.SPEED_MPS * dt)
        self.telemetry.x += dx / dist * step
        self.telemetry.y += dy / dist * step
        self.telemetry.yaw_deg = math.degrees(math.atan2(dy, dx)) % 360
        return dist - step

    def send_stop(self):
        self.telemetry.pwm = 0

    def send_deploy(self):
        self.telemetry.state = "DEPLOYING"

    def estop(self):
        self.telemetry.prev_state = self.telemetry.state
        self.telemetry.state = "ESTOP"
        self.telemetry.pwm = 0

    def failsafe(self):
        self.telemetry.prev_state = self.telemetry.state
        self.telemetry.state = "FAILSAFE"
        self.telemetry.pwm = 0

    def resume(self):
        self.telemetry.state = self.telemetry.prev_state or "NAVIGATING"

    def idle(self):
        self.telemetry.state = "IDLE"
        self.telemetry.pwm = 0


board_link = SimulatedBoardLink()
