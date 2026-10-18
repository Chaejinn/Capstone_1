"""
GuidanceController — class_srv.puml "dispatch" 패키지 (SD-03/04 흐름의 단순화 시뮬레이션).

실제로는 BoardLocator(ArUco)가 10~15Hz로 보드 위치를 주고 HeadingPID가 라즈베리파이에서
제어하지만, 하드웨어가 없는 지금은 SimulatedBoardLink가 물리적으로 그럴듯한 속도로
위치를 이동시키고 GuidanceController는 그 결과를 TELEM_HZ 주기로 WebSocket 'board' 토픽에
브로드캐스트한다. 인터페이스(start/stop)는 실제 구현으로 교체될 것을 가정해 그대로 둔다.
"""
import asyncio
import datetime
import math

from .. import config, models
from ..comm.board_link import board_link
from ..comm.command_bus import command_bus
from ..database import SessionLocal
from ..ws_hub import hub
from .track_loss_monitor import TrackLossMonitor
from .waypoint_planner import WaypointPlanner

TERMINAL_DIST_M = 3.0     # 이 거리 이내로 들어오면 종말 접근 단계로 전환
STOP_DIST_M = 0.4         # 정지거리 + 관성 활주 여유 (§1.3.1)
ALIGN_SEC = 1.5
DEPLOY_SEC = 1.0
TICK_SEC = 1.0 / config.TELEM_HZ


class GuidanceController:
    def __init__(self):
        self.planner = WaypointPlanner()
        self.loss_monitor = TrackLossMonitor()
        self._task: asyncio.Task | None = None
        self._cancel_requested = False
        self.active_mission_id: int | None = None

    def is_busy(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self, mission_id: int, target_x: float, target_y: float, board_start=(0.0, 0.0)):
        self._cancel_requested = False
        self.active_mission_id = mission_id
        board_link.reset(*board_start)
        self._task = asyncio.create_task(self._run(mission_id, target_x, target_y))

    def request_cancel(self):
        self._cancel_requested = True

    async def _broadcast_board(self):
        t = board_link.telemetry
        await hub.broadcast("board", {
            "board_id": config.BOARD_ID,
            "state": t.state,
            "prev_state": t.prev_state,
            "x": round(t.x, 2), "y": round(t.y, 2),
            "yaw_deg": round(t.yaw_deg, 1),
            "dist_cm": t.dist_cm,
            "battery_v": round(t.battery_v, 2),
            "pwm": t.pwm,
            "last_cmd_seq": t.last_cmd_seq,
        })

    async def _run(self, mission_id: int, target_x: float, target_y: float):
        db = SessionLocal()
        try:
            mission = db.query(models.Mission).filter(models.Mission.mission_id == mission_id).first()

            # ---- NAVIGATING ----
            mission.status = "NAVIGATING"
            db.commit()
            board_link.telemetry.state = "NAVIGATING"

            while True:
                if self._cancel_requested:
                    return await self._finish(db, mission, "CANCELLED", None)
                if board_link.telemetry.state == "ESTOP":
                    return  # SD-05: 비상정지 — 미션은 estop 해제/재개 처리에서 마무리

                remaining = board_link.step_toward(target_x, target_y, TICK_SEC)
                command_bus.submit_guide(heading_error_deg=0.0, speed=0.6)
                board_link.telemetry.dist_cm = remaining * 100
                await self._broadcast_board()
                await asyncio.sleep(TICK_SEC)

                if remaining <= TERMINAL_DIST_M:
                    break

            # ---- TERMINAL_APPROACH (SD-04) ----
            mission.status = "TERMINAL_APPROACH"
            db.commit()
            board_link.telemetry.state = "TERMINAL_APPROACH"
            while True:
                if self._cancel_requested:
                    return await self._finish(db, mission, "CANCELLED", None)
                if board_link.telemetry.state == "ESTOP":
                    return
                remaining = board_link.step_toward(target_x, target_y, TICK_SEC)
                board_link.telemetry.dist_cm = remaining * 100
                await self._broadcast_board()
                await asyncio.sleep(TICK_SEC)
                if remaining <= STOP_DIST_M:
                    command_bus.stop()
                    break

            # ---- ALIGNING (제자리 선회 불가 — 저속 전진+조향으로 정렬) ----
            mission.status = "ALIGNING"
            db.commit()
            board_link.telemetry.state = "ALIGNING"
            await self._broadcast_board()
            await asyncio.sleep(ALIGN_SEC)

            # ---- DEPLOYING ----
            mission.status = "DEPLOYING"
            db.commit()
            command_bus.submit_guide(0, 0)
            board_link.send_deploy()
            await self._broadcast_board()
            await asyncio.sleep(DEPLOY_SEC)

            # ---- HOLDING (완료) ----
            board_link.telemetry.state = "HOLDING"
            await self._broadcast_board()
            await self._finish(db, mission, "COMPLETED", "COMPLETED")
        finally:
            db.close()

    async def _finish(self, db, mission, mission_result: str, event_status: str | None):
        mission.result = mission_result
        mission.status = mission_result
        mission.ended_at = datetime.datetime.utcnow()
        if mission.event_id and event_status:
            event = db.query(models.DrowningEvent).filter(
                models.DrowningEvent.event_id == mission.event_id
            ).first()
            if event:
                event.status = event_status
        db.commit()
        if mission_result != "CANCELLED":
            board_link.idle()
        if mission.event_id:
            from .dispatch_manager import dispatch_manager  # 지연 임포트 — 순환참조 방지
            dispatch_manager.clear_active()


guidance_controller = GuidanceController()
