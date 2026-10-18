"""
ConfigService — class_srv.puml "api/monitor" 패키지.
ROI/판정 임계값/캘리브레이션 저장을 검증하고 config_snapshot 버전을 증가시킨다.
SD-07 흐름을 그대로 따른다: 꼭짓점 < 3 또는 재투영오차 초과 시 저장 거부, 직전 설정 유지.
"""
import json
from typing import List

from sqlalchemy.orm import Session

from .. import config, homography, models


class ConfigValidationError(Exception):
    pass


def get_active_config(db: Session) -> models.ConfigSnapshot:
    row = (
        db.query(models.ConfigSnapshot)
        .filter(models.ConfigSnapshot.is_active == True)  # noqa: E712
        .order_by(models.ConfigSnapshot.config_version.desc())
        .first()
    )
    if not row:
        row = models.ConfigSnapshot(
            saved_by="system",
            conf_threshold=config.DEFAULT_CONF_THRESHOLD,
            persist_frames=config.DEFAULT_PERSIST_FRAMES,
            window_n=config.DEFAULT_WINDOW_N,
            vlm_timeout_s=config.DEFAULT_VLM_TIMEOUT_S,
            is_active=True,
        )
        row.set_roi([])
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _new_version_from(db: Session, base: models.ConfigSnapshot) -> models.ConfigSnapshot:
    """설정이 바뀔 때마다 새 config_snapshot 행을 만들고 이전 것은 비활성화한다."""
    base.is_active = False
    new = models.ConfigSnapshot(
        saved_by=base.saved_by,
        roi_polygon=base.roi_polygon,
        conf_threshold=base.conf_threshold,
        persist_frames=base.persist_frames,
        window_n=base.window_n,
        vlm_timeout_s=base.vlm_timeout_s,
        is_active=True,
    )
    db.add(new)
    db.commit()
    db.refresh(new)
    return new


def save_roi(db: Session, points: List[dict], saved_by: str) -> models.ConfigSnapshot:
    if len(points) < config.ROI_MIN_POINTS:
        raise ConfigValidationError(f"ROI는 최소 {config.ROI_MIN_POINTS}개 꼭짓점이 필요합니다. (EX-15)")
    active = get_active_config(db)
    new = _new_version_from(db, active)
    new.set_roi(points)
    new.saved_by = saved_by
    db.commit()
    db.refresh(new)
    return new


def save_judge_config(db: Session, conf_threshold: float, persist_frames: int,
                       window_n: int, vlm_timeout_s: float, saved_by: str) -> models.ConfigSnapshot:
    active = get_active_config(db)
    new = _new_version_from(db, active)
    new.conf_threshold = conf_threshold
    new.persist_frames = persist_frames
    new.window_n = window_n
    new.vlm_timeout_s = vlm_timeout_s
    new.saved_by = saved_by
    db.commit()
    db.refresh(new)
    return new


def save_calibration(db: Session, img_points, world_points) -> models.Calibration:
    if len(img_points) < 4 or len(world_points) < 4:
        raise ConfigValidationError("기준점은 4점 이상 필요합니다. (EX-15)")

    H, reproj_error_m = homography.calibrate(img_points, world_points)
    accepted = reproj_error_m <= config.CALIB_MAX_REPROJ_ERROR_M

    if accepted:
        db.query(models.Calibration).filter(models.Calibration.is_active == True).update(  # noqa: E712
            {"is_active": False}
        )

    row = models.Calibration(
        img_points=json.dumps(img_points),
        world_points=json.dumps(world_points),
        h_matrix=json.dumps(H.tolist()),
        reproj_error_m=reproj_error_m,
        is_active=accepted,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    if not accepted:
        raise ConfigValidationError(
            f"변환 오차 {reproj_error_m:.3f}m가 허용치({config.CALIB_MAX_REPROJ_ERROR_M}m)를 초과했습니다. "
            "직전 캘리브레이션을 유지합니다. (EX-15)"
        )
    return row


def get_active_calibration(db: Session) -> models.Calibration | None:
    return (
        db.query(models.Calibration)
        .filter(models.Calibration.is_active == True)  # noqa: E712
        .order_by(models.Calibration.calib_id.desc())
        .first()
    )
