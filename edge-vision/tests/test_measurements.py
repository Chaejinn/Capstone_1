import importlib.util
import io
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import unittest
from urllib.error import HTTPError

import cv2
import numpy as np
import yaml

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.aruco.board import BoardLocator
from src.aruco.marker import load_aruco_settings, MarkerDetector
from src.capture.frames import Frame, LatestFrames
from src.homography.edit import HomographyEditState, save_homography
from src.homography.loader import load_homography, HomographyConfigError
from src.web.client import PoseClient, WebError


class MeasurementTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        data=yaml.safe_load((ROOT/'calibration/homography.yaml').read_text())
        data.update(calibration_id='synthetic-calibration',image_points=[[100,100],[400,100],[400,550],[100,550]],
                    image_size=[640,720])
        self.path=self.folder/'homography.yaml';self.path.write_text(yaml.safe_dump(data))
        self.calibration=load_homography(self.path)
        marker=yaml.safe_load((ROOT/'configs/aruco.yaml').read_text())
        marker['profiles']['standin'].update(heading_offset_deg=0,session={
            'measured_at':'2026-11-12T00:00:00Z','camera_resolution':[640,720],
            'image_session':'synthetic-test','method':'synthetic'})
        self.marker_path=self.folder/'aruco.yaml';self.marker_path.write_text(yaml.safe_dump(marker))
        self.settings=load_aruco_settings(self.marker_path)
        self.image=np.full((720,640,3),255,dtype=np.uint8)
        dictionary=cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        mark=cv2.aruco.generateImageMarker(dictionary,0,100)
        self.image[300:400,200:300]=cv2.cvtColor(mark,cv2.COLOR_GRAY2BGR)

    def frame(self):
        return Frame(1,time.time(),time.monotonic(),self.image)

    def test_handoff_bad_quad_is_rejected_and_template_stays_uncalibrated(self):
        with self.assertRaises(HomographyConfigError):
            load_homography(ROOT/'reference/calibration/homography.yaml')
        template=load_homography(ROOT/'calibration/homography.yaml')
        self.assertIsNone(template.matrix);self.assertEqual(template.reason,'UNCALIBRATED')

    def test_synthetic_marker_projects_to_metres_with_correct_bow_heading(self):
        locator=BoardLocator(self.calibration,self.settings)
        pose=locator.locate(self.frame())
        self.assertTrue(pose['tracking_valid'])
        self.assertAlmostEqual(pose['x'],.1495,delta=.002)
        self.assertAlmostEqual(pose['y'],.2005,delta=.002)
        self.assertAlmostEqual(pose['heading'],90,delta=.1)
        self.assertEqual(pose['unit'],'m')
        missing=Frame(2,time.time(),time.monotonic(),np.full_like(self.image,255))
        self.assertFalse(locator.locate(missing)['tracking_valid'])
        stale=Frame(3,time.time()-1,time.monotonic()-1,self.image)
        self.assertEqual(locator.locate(stale)['status'],'stale_frame')

    def test_unmeasured_offset_cannot_be_published_as_a_valid_pose(self):
        marker=load_aruco_settings(ROOT/'configs/aruco.yaml')
        locator=BoardLocator(self.calibration,marker,allow_unmeasured_offset=True)
        self.assertIsNotNone(locator.measure(self.frame())['heading'])
        pose=locator.locate(self.frame())
        self.assertFalse(pose['tracking_valid']);self.assertIsNone(pose['heading'])
        self.assertEqual(pose['status'],'unmeasured_heading')

    def test_save_reload_and_independent_check_point(self):
        state=HomographyEditState([[100,100],[400,100],[400,550],[100,550]],.3,.45,[640,720],
                                  frame_id='pool-01',calibration_id='draft')
        state.add_check([250,325],[.15,.225])
        metadata=save_homography(self.path,state)
        calibration=load_homography(self.path)
        self.assertEqual(calibration.homography_hash,metadata['homography_hash'])
        from src.homography.loader import check_point_errors
        self.assertLess(check_point_errors(calibration,calibration.check_points)[0]['error_cm'],.001)

    def test_latest_frame_owns_immutable_pixels_and_detects_ambiguity(self):
        frames=LatestFrames();frames.publish(self.image)
        self.image[:]=0
        self.assertFalse(frames.latest.image.flags.writeable)
        self.assertGreater(frames.latest.image.sum(),0)
        two=frames.latest.image.copy();two[300:400,450:550]=two[300:400,200:300]
        corners,count=MarkerDetector(self.settings).find(two)
        self.assertIsNone(corners);self.assertEqual(count,2)

    def test_marker_print_output_is_detectable(self):
        spec=importlib.util.spec_from_file_location('marker_print',ROOT/'scripts/aruco/make_aruco_marker.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        page,_=module.render('DICT_4X4_50',0,5,dpi=100)
        image=cv2.cvtColor(np.array(page),cv2.COLOR_GRAY2BGR)
        corners,count=MarkerDetector(self.settings).find(image)
        self.assertIsNotNone(corners);self.assertEqual(count,1)

    def test_http_errors_include_safe_status_and_clock_reason_without_keys(self):
        secret='secret-key-'*4
        class Opener:
            def open(self,request,timeout):
                raw=json.dumps({'detail':{'code':'INVALID_TIMESTAMP','observed_age_seconds':-1.5,
                                          'untrusted':secret}}).encode()
                raise HTTPError(request.full_url,422,'bad',{},io.BytesIO(raw))
        client=PoseClient('https://example.test',secret,opener=Opener())
        with self.assertRaises(WebError) as caught:client.send({'pose':{}})
        self.assertIn('HTTP 422',str(caught.exception));self.assertIn('-1.5',str(caught.exception))
        self.assertNotIn(secret,str(caught.exception))
        with self.assertRaises(ValueError):PoseClient('https://user:password@example.test')
        with self.assertRaises(ValueError):PoseClient('http://example.test')

    def test_video_launcher_produces_measured_packets_without_camera_or_network(self):
        video=self.folder/'marker.avi'
        writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),30,(640,720))
        self.assertTrue(writer.isOpened())
        for _ in range(60):writer.write(self.image)
        writer.release()
        config={'camera':{'camera_index':0,'width':640,'height':720,'fps':30},
            'homography_config':str(self.path),'aruco_config':str(self.marker_path),
            'pose':{'use_homography':True,'heading_mode':'world'}}
        config_path=self.folder/'vision.yaml';config_path.write_text(yaml.safe_dump(config))
        env=self.folder/'.env';env.write_text('WEB_SITE_ID=synthetic-test\n')
        result=subprocess.run([sys.executable,str(ROOT/'run.py'),'publish-pose','--config',str(config_path),
            '--video',str(video),'--env-file',str(env),'--dry-run','--max-frames','2','--interval','0.5'],
            cwd=self.folder,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        packets=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([p['sequence'] for p in packets],[1,2])
        self.assertGreater(packets[1]['pose']['frame_id'],packets[0]['pose']['frame_id'])
        self.assertTrue(all(p['pose']['tracking_valid'] for p in packets))
        self.assertTrue(all(p['pose']['unit']=='m' for p in packets))


if __name__=='__main__':unittest.main()
