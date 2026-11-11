"""Read-only readiness report; never opens a camera, writes calibration or sends data."""
import argparse
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def diagnose(config_path=None):
    report = {'dependencies': {}, 'checks': {}, 'ready_for_pose': False,
              'camera_tested': False, 'web_tested': False}
    for name in ('cv2', 'numpy', 'yaml', 'PIL', 'dotenv'):
        try:
            module = importlib.import_module(name)
            report['dependencies'][name] = getattr(module, '__version__', 'installed')
        except ImportError:
            report['dependencies'][name] = 'MISSING'
    if 'MISSING' in report['dependencies'].values():
        return report
    import cv2
    import yaml
    from src.homography.loader import load_homography
    from src.aruco.marker import load_aruco_settings
    from src.common.files import aruco_path, homography_path
    config_path = Path(config_path or ROOT/'configs/vision.yaml').resolve()
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    report['checks']['aruco_api'] = hasattr(cv2, 'aruco') and hasattr(cv2.aruco, 'ArucoDetector')
    report['checks']['gui_available'] = any(
        line.strip().startswith('GUI:') and line.partition(':')[2].strip().upper() not in ('', 'NONE')
        for line in cv2.getBuildInformation().splitlines())
    try:
        calibration = load_homography(homography_path(config_path.parent, config))
        report['checks']['calibration'] = calibration.reason
        report['checks']['calibration_valid'] = calibration.matrix is not None
        report['checks']['independent_check_points'] = len(calibration.check_points)
    except ValueError as exc:
        report['checks'].update(calibration=str(exc), calibration_valid=False)
    try:
        marker = load_aruco_settings(aruco_path(config_path.parent, config))
        report['checks'].update(marker_id=marker.board_marker_id, marker_profile=marker.profile,
            heading_offset_measured=marker.offset_measured)
    except (ValueError, RuntimeError) as exc:
        report['checks'].update(marker_error=str(exc), heading_offset_measured=False)
    report['ready_for_pose'] = bool(report['checks']['aruco_api']
        and report['checks']['calibration_valid'] and report['checks']['heading_offset_measured'])
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    args = parser.parse_args()
    try:
        result = diagnose(args.config)
    except (OSError, ValueError, KeyError) as exc:
        print(json.dumps({'configuration_error':str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result['ready_for_pose'] else 2)
