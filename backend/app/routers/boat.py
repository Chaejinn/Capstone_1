"""Single-process LAN boat control. Packet encoding belongs to the Windows bridge."""
import math
import time
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

router = APIRouter(prefix="/boat", tags=["boat"])


class Pose(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, extra="forbid")
    x: float
    y: float
    yaw_deg: float
    target_x: float
    target_y: float


class BoatControl:
    def __init__(self):
        self.estop = False
        self.reset()

    def reset(self):
        self.previous_error = None
        self.previous_time = None
        self.updated_at = None
        self.command = dict(throttle=0, rudder=0, net=None, estop=self.estop)

    def emergency_stop(self):
        self.estop = True
        self.reset()

    def clear_estop(self):
        self.estop = False
        self.reset()  # Require a fresh pose before moving again.

    def guidance(self, pose, now=None):
        now = time.monotonic() if now is None else now
        if self.estop:
            return self.read(now)
        dx, dy = pose.target_x - pose.x, pose.target_y - pose.y
        if math.hypot(dx, dy) <= 0.4:
            self.reset()
            self.command["net"] = 150
        else:
            error = (math.degrees(math.atan2(dy, dx)) - pose.yaw_deg + 180) % 360 - 180
            derivative = 0.0
            if self.previous_time is not None:
                dt = now - self.previous_time
                if 0 < dt <= 1.5:
                    derivative = ((error - self.previous_error + 180) % 360 - 180) / dt
            # PID with Ki=0: proportional + time-based derivative, bounded rudder.
            rudder = max(-35.0, min(35.0, 0.8 * error + 0.15 * derivative))
            self.command = dict(throttle=35, rudder=round(rudder, 2), net=None, estop=False)
            self.previous_error, self.previous_time = error, now
        self.updated_at = now
        return self.read(now)

    def read(self, now=None):
        now = time.monotonic() if now is None else now
        if self.estop:
            return dict(throttle=0, rudder=0, net=None, estop=True)
        if self.updated_at is None or now - self.updated_at > 1.5:
            return dict(throttle=0, rudder=0, net=None, estop=False)
        return self.command.copy()


boat_control = BoatControl()


@router.get("/command")
async def command():
    return boat_control.read()


@router.post("/pose")
async def pose(body: Pose):
    return boat_control.guidance(body)


@router.post("/estop")
async def estop():
    boat_control.emergency_stop()
    return boat_control.read()


@router.post("/estop/clear")
async def clear_estop():
    boat_control.clear_estop()
    return boat_control.read()
