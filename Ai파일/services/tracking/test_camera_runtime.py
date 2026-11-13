"""CPU-only integration checks; fake classifier, real OpenCV and stream handling."""
import base64
import json
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'Ai파일/local-model/modal-moondream2-deploy'))
import cv2
import numpy as np
from fastapi.testclient import TestClient
from src.camera_configuration import CameraConfiguration
from src.camera_runtime import create_profile
from src.browser_vision import create_browser_app
from src.flow.sensing.coordinates import Calibration


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.settings={'revision':7,'homography':{'enabled':True,'image_size':[1280,720],
            'image_points':[{'x':10,'y':10},{'x':90,'y':10},{'x':90,'y':90},{'x':10,'y':90}],
            'pool_width_m':.8,'pool_height_m':.8,'calibration_id':'synthetic','frame_id':'pool-01'},
            'aruco':{'enabled':True,'dictionary':'DICT_4X4_50','marker_id':0,'marker_size_m':.05,
                      'heading_offset_deg':15,'heading_measured':True}}
        self.image=np.full((720,1280,3),255,dtype=np.uint8)
        marker=cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50),0,200)
        self.image[260:460,540:740]=cv2.cvtColor(marker,cv2.COLOR_GRAY2BGR)
        self.headers={'Authorization':'Bearer '+'k'*40,'X-Vision-Owner':'test-owner','X-Vision-Site':'test-site'}

    def test_scaled_upload_preserves_metres_and_heading(self):
        calibration,locator,revision=create_profile(self.settings)
        self.assertEqual(revision,7)
        full=locator.inspect(self.image);small=locator.inspect(cv2.resize(self.image,(640,360)))
        self.assertTrue(full['detected']);self.assertTrue(full['coordinate_valid'])
        self.assertAlmostEqual(full['x_m'],.4,delta=.002);self.assertAlmostEqual(full['y_m'],.4,delta=.002)
        self.assertAlmostEqual(full['heading_deg'],105,delta=.1)
        front,_=calibration.point(full['board_front_px'],[1280,720])
        import math
        direction=math.degrees(math.atan2(front['y']-full['y_m'],front['x']-full['x_m']))%360
        self.assertAlmostEqual(direction,full['heading_deg'],delta=.1)
        above,_=calibration.point([640,250],[1280,720])
        below,_=calibration.point([640,470],[1280,720])
        self.assertGreater(above['y'],below['y'])
        self.assertAlmostEqual(full['x_m'],small['x_m'],delta=.002)
        self.assertAlmostEqual(full['y_m'],small['y_m'],delta=.002)
        self.assertEqual(calibration.point([10,10],[720,1280])[1],'IMAGE_ASPECT_MISMATCH')

    def test_marker_only_and_unmeasured_heading_are_not_a_control_pose(self):
        settings=json.loads(json.dumps(self.settings));settings['homography']={'enabled':False}
        _,locator,_=create_profile(settings);result=locator.inspect(self.image)
        self.assertTrue(result['detected']);self.assertFalse(result['coordinate_valid']);self.assertIsNone(result['heading_deg'])
        settings=self.settings;settings['aruco']['heading_measured']=False;settings['aruco']['heading_offset_deg']=None
        _,locator,_=create_profile(settings)
        from src.rescue.frames import Frame
        frame=Frame(1,time.time(),time.monotonic(),self.image)
        self.assertFalse(locator.locate(frame)['tracking_valid'])
        self.assertTrue(locator.inspect(self.image)['coordinate_valid'])
        self.assertIsNone(locator.inspect(self.image)['heading_deg'])

    def test_more_than_four_points_are_used_with_resized_images(self):
        settings=self.settings;h=settings['homography']
        extra=[{'x':20+i*10,'y':20+j*10} for i in range(7) for j in range(7)]
        h['image_points']+=extra
        h['world_points']=[{'x':0,'y':.8},{'x':.8,'y':.8},{'x':.8,'y':0},{'x':0,'y':0}]
        h['world_points'] += [{'x':(p['x']-10)/100,'y':(90-p['y'])/100} for p in extra]
        calibration,locator,_=create_profile(settings)
        self.assertEqual(calibration.fit_report['point_count'],53)
        result=locator.inspect(cv2.resize(self.image,(640,360)))
        self.assertTrue(result['coordinate_valid']);self.assertAlmostEqual(result['x_m'],.4,delta=.002)
        self.assertAlmostEqual(result['heading_deg'],105,delta=.1)

    def test_full_stream_configuration_marker_render_and_diagnostic(self):
        class Predictor:
            def predict(self,frame):
                return {'frame_id':frame.frame_id,'image_size':[frame.image.shape[1],frame.image.shape[0]],
                        'detections':[],'inference_ms':1}
        app=create_browser_app(Predictor(),Calibration({}),{'marker_id':0},api_key='k'*40,
                               configuration_factory=create_profile)
        with TestClient(app) as client:
            self.assertEqual(client.post('/v1/streams',json={'camera_id':'camera-01'}).status_code,401)
            stream=client.post('/v1/streams',json={'camera_id':'camera-01','configuration':self.settings},headers=self.headers)
            self.assertEqual(stream.status_code,201,stream.text)
            self.assertEqual(stream.json()['configuration_revision'],7)
            url='/v1/streams/'+stream.json()['stream_id']
            ok,encoded=cv2.imencode('.jpg',self.image);self.assertTrue(ok)
            from datetime import datetime,timezone
            response=client.post(url+'/frames',headers=self.headers,
                files={'image':('frame.jpg',encoded.tobytes(),'image/jpeg')},
                data={'frame_id':'1','captured_at':datetime.now(timezone.utc).isoformat(),'image_width':'1280','image_height':'720'})
            self.assertEqual(response.status_code,200,response.text)
            analysis=None
            for _ in range(40):
                analysis=client.get(url+'/results',headers=self.headers).json().get('analysis')
                if analysis:break
                time.sleep(.02)
            self.assertIsNotNone(analysis);self.assertTrue(analysis['marker_observation']['detected'])
            self.assertEqual(analysis['configuration_revision'],7)
            self.assertFalse(analysis['control_commands_generated'])
            result=client.post('/v1/vision/inspect',headers=self.headers,
                json={'configuration':self.settings,'image_base64':base64.b64encode(encoded).decode()})
            self.assertEqual(result.status_code,200,result.text)
            self.assertTrue(result.json()['marker_observation']['coordinate_valid'])
            marker=client.post('/v1/vision/marker',headers=self.headers,json={'marker_id':0})
            self.assertEqual(marker.status_code,200,marker.text)
            rendered=cv2.imdecode(np.frombuffer(base64.b64decode(marker.json()['image_base64']),np.uint8),cv2.IMREAD_COLOR)
            _,locator,_=create_profile(self.settings)
            self.assertTrue(locator.inspect(rendered)['detected'])
            self.assertEqual(client.delete(url,headers=self.headers).status_code,200)


if __name__=='__main__':unittest.main()
