"""WaypointPlanner — class_srv.puml "dispatch" 패키지."""
import math


class WaypointPlanner:
    APPROACH_OFFSET_M = 0.3  # 종말 접근 정지 거리 + 관성 활주 여유 (§1.3.1 추진 구조 제약)

    def plan(self, target: tuple[float, float], board: tuple[float, float]):
        """단순화: 접근 오프셋을 적용한 최종 접근점 하나만 반환 (제자리 선회 불가 제약 반영은
        GuidanceController의 저속 전진 로직에서 처리)."""
        tx, ty = target
        bx, by = board
        dx, dy = tx - bx, ty - by
        dist = math.hypot(dx, dy)
        if dist < 1e-6:
            return [target]
        ux, uy = dx / dist, dy / dist
        final_point = (tx - ux * self.APPROACH_OFFSET_M, ty - uy * self.APPROACH_OFFSET_M)
        return [final_point, target]
