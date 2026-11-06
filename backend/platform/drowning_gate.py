"""Consecutive independent model observations; detection scores are never verdict scores."""
from dataclasses import dataclass
import math


@dataclass
class Evidence:
    last_frame: int = -1
    last_capture: float = -math.inf
    count: int = 0
    active: bool = False
    confirmed_at: float | None = None


class DrowningGate:
    def __init__(self, threshold=0.8, frames=15, max_gap_seconds=15.0):
        if not 0 < threshold <= 1 or frames < 1 or max_gap_seconds <= 0:
            raise ValueError('invalid judgement settings')
        self.threshold, self.frames, self.max_gap = threshold, frames, max_gap_seconds
        self.tracks = {}

    def observe(self, track, frame_id, captured_at, state, drowning_score, decided_at=None):
        if track is None or not math.isfinite(captured_at):
            return None
        evidence = self.tracks.setdefault(track, Evidence())
        if frame_id <= evidence.last_frame or captured_at <= evidence.last_capture:
            return None
        if captured_at - evidence.last_capture > self.max_gap:
            evidence.count = 0
            evidence.active = False
        evidence.last_frame, evidence.last_capture = frame_id, captured_at
        valid = (state == 'DROWNING' and isinstance(drowning_score, (float, int))
                 and not isinstance(drowning_score, bool) and math.isfinite(drowning_score)
                 and self.threshold <= drowning_score <= 1)
        evidence.count = min(self.frames, evidence.count + 1) if valid else 0
        confirmed = evidence.count >= self.frames
        first = confirmed and not evidence.active
        if first:
            evidence.confirmed_at = captured_at if decided_at is None else decided_at
        elif not confirmed:
            evidence.confirmed_at = None
        evidence.active = confirmed
        return {'confirmed_at':evidence.confirmed_at,'confirmed':confirmed,'new_confirmation':first,'consecutive_frames':evidence.count,
                'required_frames':self.frames,'score_threshold':self.threshold,
                'decision':'DROWNING_CONFIRMED' if confirmed else 'OBSERVING'}

    def retain(self, visible_tracks):
        # A frame without the target breaks consecutive evidence.
        self.tracks = {key:value for key,value in self.tracks.items() if key in visible_tracks}
