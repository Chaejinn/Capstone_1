"""
CommandBus — class_srv.puml "comm" 패키지.
비상정지는 우선순위 0으로 큐를 비우고 즉시 전송한다 (SD-05).
시뮬레이션 환경이라 실제 우선순위 큐잉 대신 즉시 처리하되, 인터페이스는 동일하게 유지한다.
"""
from .board_link import board_link


class CommandBus:
    def submit_guide(self, heading_error_deg: float, speed: float):
        board_link.send_guide(heading_error_deg, speed)

    def emergency_stop(self, source: str):
        from ..routers.boat import boat_control
        boat_control.emergency_stop()
        board_link.estop()

    def stop(self):
        board_link.send_stop()

    def resume(self):
        from ..routers.boat import boat_control
        boat_control.clear_estop()
        board_link.resume()

    def idle(self):
        board_link.idle()


command_bus = CommandBus()
