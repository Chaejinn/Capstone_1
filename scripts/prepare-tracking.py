"""Stage the tracked web-camera contract into the existing CPU Modal build context."""
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
STAGE=ROOT/'local-model/modal-moondream2-deploy'
if not (STAGE/'src/flow/sensing/coordinates.py').is_file():
    raise SystemExit('기존 CPU 추적 서비스 빌드 컨텍스트가 없습니다. services/tracking/README.md를 확인하세요.')
for source,target in [
    ('services/tracking/browser_vision.py','src/browser_vision.py'),
    ('services/tracking/camera_runtime.py','src/camera_runtime.py'),
    ('backend/platform/camera_configuration.py','src/camera_configuration.py'),
    ('services/tracking/modal_app.py','tracking_app.py'),
]:
    destination=STAGE/target
    backup=destination.with_suffix(destination.suffix+'.before-web-configuration')
    if destination.exists() and not backup.exists():shutil.copy2(destination,backup)
    shutil.copy2(ROOT/source,destination)
    print(target)
