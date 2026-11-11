"""Persistent per-camera ByteTrack service for the Vercel web proxy."""
from pathlib import Path
import os
import modal

ROOT = Path(__file__).resolve().parent
app = modal.App('drown-guardian-web-tracking')
image = (modal.Image.debian_slim(python_version='3.12')
         .pip_install(*[s.strip() for s in (ROOT/'requirements-browser-vision.txt').read_text().splitlines()
                        if s.strip() and not s.lstrip().startswith('#')])
         .add_local_python_source('src')
         .add_local_file(str(ROOT/'requirements-browser-vision.txt'), '/root/requirements-browser-vision.txt')
         .add_local_file(str(ROOT/'client_example.py'), '/root/client_example.py'))

@app.function(image=image, cpu=2, memory=2048, max_containers=1,
              timeout=120, scaledown_window=300,
              secrets=[modal.Secret.from_name('drown-guardian-secrets'),
                       modal.Secret.from_dict({'VISION_INGEST_API_KEY':os.environ['VISION_INGEST_API_KEY']})])
@modal.asgi_app()
def browser_app():
    import os
    import logging
    logging.basicConfig(level=logging.INFO)
    from src.browser_vision import create_browser_app, ModalGateway
    from src.flow.sensing.coordinates import Calibration
    from src.flow.detection.tracking import PersonTracker
    from src.camera_runtime import create_profile
    return create_browser_app(
        ModalGateway('https://kbkr504--drown-guardian-api-fastapi-app.us-east.modal.run',
                     os.environ['DROWN_GUARDIAN_API_KEY'],timeout=60),
        Calibration({}),
        {'dictionary':'DICT_4X4_50','marker_id':0,'marker_size_m':0.10,
         'forward_offset_deg':0,'tracking_timeout_seconds':0.5,'max_frame_age_seconds':0.2},
        api_key=os.environ['VISION_INGEST_API_KEY'], camera_id='camera-01',
        configuration_factory=create_profile,
        tracker_factory=lambda:PersonTracker(track_thresh=0.3,match_thresh=0.8,track_buffer=30),
    )
