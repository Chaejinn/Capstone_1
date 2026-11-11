"""Single launcher; can be called from any working directory."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
TOOLS = {
    'diagnose': ('diagnose.py',),
    'calibrate': ('scripts/homography/calibration_editor.py', 'homography'),
    'marker': ('scripts/aruco/aruco_check.py',),
    'pose': ('scripts/aruco/pose_check.py',),
    'print-marker': ('scripts/aruco/make_aruco_marker.py',),
    'publish-pose': ('scripts/publish_pose.py',),
}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='호모그래피·ArUco 도구 (카메라는 한 프로그램만 사용)')
    parser.add_argument('tool', choices=TOOLS)
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    script, *fixed = TOOLS[args.tool]
    arguments = list(args.arguments)
    path_options = {'--config','--homography-file','--video','--env-file','--out'}
    for i, value in enumerate(arguments):
        if value in path_options and i+1 < len(arguments):
            arguments[i+1] = str(Path(arguments[i+1]).resolve())
        elif '=' in value and value.partition('=')[0] in path_options:
            name, _, path = value.partition('=')
            arguments[i] = name+'='+str(Path(path).resolve())
    raise SystemExit(subprocess.call([sys.executable, str(ROOT/script), *fixed, *arguments], cwd=ROOT))
