"""Single camera/video owner -> measured board pose -> web display receiver."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def packet(pose, *, site, camera, session, sequence, calibration, offset_measured):
    return {'site_id':site,'camera_id':camera,'session_id':session,'sequence':sequence,
        'pose':{name:pose.get(name) for name in ('frame_id','tracking_valid','x','y','heading','status')}
        | {'timestamp':datetime.fromtimestamp(pose['timestamp'],timezone.utc).isoformat(),
           'unit':'m','coordinate_frame':calibration.config['frame_id'],
           'calibration_id':calibration.config['calibration_id'],
           'heading_offset_measured':offset_measured}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=ROOT/'configs/vision.yaml')
    parser.add_argument('--env-file',type=Path,default=ROOT/'.env')
    parser.add_argument('--camera-index',type=int)
    parser.add_argument('--camera-id',default='camera-01')
    parser.add_argument('--video',type=Path)
    parser.add_argument('--max-frames',type=int,default=0)
    parser.add_argument('--interval',type=float,default=1.0,help='web display interval, at least 0.5 seconds')
    parser.add_argument('--dry-run',action='store_true',help='read camera/video and print packets without HTTP')
    parser.add_argument('--check-web',action='store_true',help='check web API and clock only; no camera or POST')
    args=parser.parse_args()
    if args.interval<0.5 or args.max_frames<0:
        parser.error('interval must be >= 0.5 and max-frames >= 0')
    from dotenv import load_dotenv
    load_dotenv(args.env_file)
    from src.web.client import PoseClient, WebError
    try:
        client=None
        if not args.dry_run or args.check_web:
            client=PoseClient(os.getenv('WEB_BACKEND_URL',''),os.getenv('WEB_BACKEND_TOKEN',''))
        if args.check_web:
            print(json.dumps(client.check_clock(),ensure_ascii=False))
            return 0
        site=os.getenv('WEB_SITE_ID','')
        if not site:
            raise ValueError('Set WEB_SITE_ID in the chosen env file')
        if not args.dry_run and len(client.token)<32:
            raise ValueError('WEB_BACKEND_TOKEN is missing or too short')
        import yaml
        import cv2
        from src.aruco.board import load_pose_inputs, BoardLocator
        from src.capture.frames import LatestFrames, CaptureWorker
        config_path=args.config.resolve()
        config=yaml.safe_load(config_path.read_text(encoding='utf-8'))
        calibration, settings, options=load_pose_inputs(config_path,config,require_calibrated=True)
        if calibration.config.get('unit')!='m':
            raise ValueError('Web pose requires measured metres; normalized coordinates are not metres')
        if not settings.offset_measured:
            raise ValueError('Measure heading offset first: run.py marker --world --write')
        locator=BoardLocator(calibration,settings,**options)
        # CaptureWorker owns the input and keeps only the latest immutable frame.
        # HTTP runs independently of acquisition and cannot build a stale frame queue.
        if args.video:
            source=cv2.VideoCapture(str(args.video.resolve()))
            if not source.isOpened():
                source.release();raise ValueError('Cannot open video file')
            fps=source.get(cv2.CAP_PROP_FPS) or 30
        else:
            from src.capture.camera import Camera
            camera=config['camera']
            source=Camera(camera_index=args.camera_index if args.camera_index is not None else camera.get('camera_index',0),
                width=camera.get('width',1280),height=camera.get('height',720),fps=camera.get('fps',30))
            source.open();fps=None
        frames=LatestFrames();capture=CaptureWorker(source,frames,video_fps=fps)
        capture.start();session=str(uuid4());sequence=0;last=-1;failures=0
        try:
            while True:
                frame=frames.get(after=last,timeout=2)
                if frame is None:
                    if frames.closed:break
                    raise ValueError('Camera produced no fresh frames within 2 seconds')
                last=frame.frame_id
                pose=locator.locate(frame)
                sequence+=1
                body=packet(pose,site=site,camera=args.camera_id,session=session,sequence=sequence,
                            calibration=calibration,offset_measured=settings.offset_measured)
                if args.dry_run:
                    print(json.dumps(body,allow_nan=False))
                else:
                    try:
                        receipt=client.send(body)
                        print(json.dumps({'accepted_sequence':receipt.get('accepted_sequence'),
                                          'status':pose['status'],'command_issued':False}))
                    except WebError as exc:
                        failures+=1;print(str(exc),file=sys.stderr)
                if args.max_frames and sequence>=args.max_frames:break
                time.sleep(args.interval)
        finally:
            capture.close()
        return 1 if failures else 0
    except (ValueError,OSError,RuntimeError,KeyError) as exc:
        print(f'오류: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':
    try:raise SystemExit(main())
    except KeyboardInterrupt:raise SystemExit(130)
