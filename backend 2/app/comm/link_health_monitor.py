"""LinkHealthMonitor — class_srv.puml "comm" 패키지. 시뮬레이션 모드에서는 항상 정상."""
import datetime


class LinkHealthMonitor:
    def __init__(self, timeout_sec: float = 0.5):
        self.timeout_sec = timeout_sec
        self.last_seen = datetime.datetime.utcnow()

    def touch(self):
        self.last_seen = datetime.datetime.utcnow()

    def is_lost(self) -> bool:
        return (datetime.datetime.utcnow() - self.last_seen).total_seconds() > self.timeout_sec


link_health_monitor = LinkHealthMonitor()
