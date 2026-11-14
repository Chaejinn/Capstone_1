"""HTTP stream -> real ByteTrack -> strict gate; scripted scores, no model or board."""
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'Ai파일/local-model/modal-moondream2-deploy'))
import cv2
import numpy as np
from fastapi.testclient import TestClient
from src.browser_vision import create_browser_app
from src.camera_runtime import create_profile
from src.flow.detection.tracking import PersonTracker
from src.flow.sensing.coordinates import Calibration


class ScriptedPredictor:
    def __init__(self):
        self.score = .8
        self.visible = True

    def predict(self, frame):
        detection = {'class':'human_dummy','confidence':.99,'water_state':'DROWNING',
                     'drowning_score':self.score,'bbox':[100,100,200,300]}
        return {'frame_id':frame.frame_id,'image_size':[640,480],
                'detections':[detection] if self.visible else [],'inference_ms':1}


class JudgementPipelineTests(unittest.TestCase):
    def setUp(self):
        self.predictor = ScriptedPredictor()
        app = create_browser_app(self.predictor, Calibration({}), {'marker_id':0},
            api_key='k'*40, configuration_factory=create_profile,
            tracker_factory=lambda:PersonTracker(.3,.8,30))
        self.client = self.enterContext(TestClient(app))
        self.headers = {'Authorization':'Bearer '+'k'*40,'X-Vision-Owner':'test-owner','X-Vision-Site':'test-site'}
        _,image = cv2.imencode('.jpg',np.zeros((480,640,3),np.uint8))
        self.jpeg = image.tobytes()
        self.streams = []
        self.addCleanup(self.close_streams)

    def close_streams(self):
        for path in self.streams:
            self.client.delete(path,headers=self.headers)

    def open_stream(self):
        response = self.client.post('/v1/streams',headers=self.headers,json={
            'camera_id':'camera-01','configuration':{'homography':{'enabled':False},'aruco':{'enabled':False}}})
        self.assertEqual(response.status_code,201,response.text)
        path = '/v1/streams/'+response.json()['stream_id']
        self.streams.append(path)
        return path

    def upload(self,path,frame):
        return self.client.post(path+'/frames',headers=self.headers,
            files={'image':('frame.jpg',self.jpeg,'image/jpeg')},data={
                'frame_id':str(frame),'captured_at':datetime.now(timezone.utc).isoformat(),
                'image_width':'640','image_height':'480'})

    def analyzed(self,path,frame):
        response = self.upload(path,frame)
        self.assertEqual(response.status_code,200,response.text)
        for _ in range(200):
            packet = self.client.get(path+'/results',headers=self.headers).json()
            self.assertIsNone(packet['last_error'],packet)
            analysis = packet.get('analysis')
            if analysis and analysis['frame_id']==frame:
                self.assertFalse(analysis['control_commands_generated'])
                return analysis['detections']
            time.sleep(.005)
        self.fail('Scripted analysis did not finish')

    def test_fifteenth_frame_confirms_once_without_dispatch(self):
        path = self.open_stream()
        identities = set()
        for frame in range(1,17):
            detections = self.analyzed(path,frame)
            self.assertEqual(len(detections),1)
            item = detections[0];identities.add(item['track_id'])
            self.assertEqual(item['consecutive_frames'],min(frame,15))
            self.assertEqual(item['confirmed'],frame>=15)
            self.assertEqual(bool(item['event_id']),frame==15)
            self.assertFalse(item['dispatch_eligible']);self.assertFalse(item['command_issued'])
            if frame>=15:
                self.assertEqual(item['dispatch_status'],'BLOCKED_NO_CALIBRATION')
                confirmed=datetime.fromisoformat(item['confirmed_at'].replace('Z','+00:00'))
                deadline=datetime.fromisoformat(item['dispatch_deadline_at'].replace('Z','+00:00'))
                self.assertEqual((deadline-confirmed).total_seconds(),3)
        self.assertEqual(len(identities),1)

    def test_detection_confidence_cannot_replace_drowning_score(self):
        path = self.open_stream()
        for score in (None,.79):
            self.predictor.score = score
            for frame in range(1,17) if score is None else range(17,33):
                item = self.analyzed(path,frame)[0]
                self.assertFalse(item['confirmed']);self.assertEqual(item['consecutive_frames'],0)

    def test_low_score_and_missing_target_break_streak(self):
        path = self.open_stream()
        for frame in range(1,15):self.analyzed(path,frame)
        self.predictor.score = .79
        self.assertEqual(self.analyzed(path,15)[0]['consecutive_frames'],0)
        self.predictor.score = .8
        self.assertEqual(self.analyzed(path,16)[0]['consecutive_frames'],1)
        self.predictor.visible = False
        self.assertEqual(self.analyzed(path,17),[])
        self.predictor.visible = True
        self.assertEqual(self.analyzed(path,18)[0]['consecutive_frames'],1)

    def test_replay_rejected_and_reconnection_starts_from_one(self):
        first = self.open_stream()
        self.analyzed(first,1)
        self.assertEqual(self.upload(first,1).status_code,422)
        for frame in range(2,15):self.analyzed(first,frame)
        self.assertEqual(self.client.delete(first,headers=self.headers).status_code,200)
        self.streams.remove(first)
        second = self.open_stream()
        item = self.analyzed(second,1)[0]
        self.assertEqual(item['consecutive_frames'],1);self.assertFalse(item['confirmed'])


if __name__=='__main__':unittest.main()
