"""TrackLossMonitor — class_srv.puml "dispatch" 패키지. (SD-03 EX-01~03)"""
import datetime


class TrackLossMonitor:
    def __init__(self):
        self.lost_since: datetime.datetime | None = None

    def evaluate(self, pose_seen: bool) -> str:
        now = datetime.datetime.utcnow()
        if pose_seen:
            self.lost_since = None
            return "OK"
        if self.lost_since is None:
            self.lost_since = now
        elapsed = (now - self.lost_since).total_seconds()
        if elapsed < 0.5:
            return "OK"          # EX-01: 마지막 명령 유지
        if elapsed < 2.0:
            return "UNSTABLE"    # EX-02: 정지 + '추적 불안정'
        return "LOST"            # EX-03: TRACK_LOST
