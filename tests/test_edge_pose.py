import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
import unittest
from uuid import uuid4

import test_edge_receiver
from backend.platform import models
from backend.platform.routers.edge_pose import router


class PoseReceiverTests(unittest.TestCase):
    def setUp(self):
        self.edge = test_edge_receiver.EdgeTests(); self.edge.setUp()
        self.addCleanup(self.edge.doCleanups)
        self.edge.app.include_router(router, prefix='/api')
        self.client = self.edge.client
        self.body = {'site_id':'site-a','camera_id':'camera-01','session_id':str(uuid4()),'sequence':1,
            'pose':{'timestamp':datetime.now(timezone.utc).isoformat(),'frame_id':1,
              'tracking_valid':True,'heading_offset_measured':True,'x':0.15,'y':0.2,'heading':90,
              'unit':'m','coordinate_frame':'pool-01','calibration_id':'measured-test','status':'tracked'}}

    def tearDown(self):
        self.edge.tearDown()

    def send(self, body=None):
        return self.client.post('/api/edge/pose',json=body or self.body,headers=self.edge.headers)

    def test_auth_scope_and_public_clock(self):
        self.assertEqual(self.client.post('/api/edge/pose',json=self.body).status_code,401)
        self.assertEqual(self.client.get('/api/edge/pose?site_id=site-a&camera_id=camera-01').status_code,401)
        self.assertEqual(self.send({**self.body,'camera_id':'other'}).status_code,403)
        clock=self.client.get('/api/edge/time')
        self.assertEqual(clock.status_code,200)
        self.assertEqual(clock.headers['cache-control'],'no-store')
        self.assertIsNotNone(datetime.fromisoformat(clock.json()['server_time']).utcoffset())

    def test_latest_snapshot_is_bounded_and_duplicates_do_not_advance(self):
        self.assertEqual(self.send().status_code,200)
        self.assertEqual(self.send().status_code,200)
        newer=copy.deepcopy(self.body);newer['sequence']=2;newer['pose']['frame_id']=2
        newer['pose']['timestamp']=datetime.now(timezone.utc).isoformat()
        self.assertEqual(self.send(newer).status_code,200)
        self.assertEqual(self.send().status_code,409)
        self.edge.authorize_reader()
        result=self.client.get('/api/edge/pose?site_id=site-a&camera_id=camera-01')
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.json()['sequence'],2)
        self.assertFalse(result.json()['command_issued'])
        with self.edge.sessions() as db:
            self.assertEqual(db.query(models.EdgePose).count(),1)
            self.assertEqual(db.query(models.Event).count(),0)

    def test_invalid_units_heading_provenance_and_false_validity(self):
        for change in ({'unit':'normalized'},{'heading_offset_measured':False},
                       {'x':None},{'heading':360},{'tracking_valid':False},
                       {'frame_id':True},{'x':-1}):
            body=copy.deepcopy(self.body);body['pose'].update(change)
            self.assertEqual(self.send(body).status_code,422,change)

    def test_old_measurement_is_never_a_valid_guidance_pose(self):
        body=copy.deepcopy(self.body)
        body['pose']['timestamp']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        self.assertEqual(self.send(body).status_code,200)
        self.edge.authorize_reader()
        result=self.client.get('/api/edge/pose?site_id=site-a&camera_id=camera-01').json()
        self.assertTrue(result['expired'])
        self.assertFalse(result['pose']['tracking_valid'])
        self.assertIsNone(result['pose']['x']);self.assertIsNone(result['pose']['heading'])
        self.assertEqual(result['pose']['status'],'stale_frame')
        body['pose']['timestamp']=(datetime.now(timezone.utc)+timedelta(seconds=2)).isoformat()
        self.assertEqual(self.send(body).status_code,422)

    def test_active_session_cannot_be_replaced_and_frame_order_matters(self):
        self.assertEqual(self.send().status_code,200)
        other={**self.body,'session_id':str(uuid4())}
        self.assertEqual(self.send(other).status_code,409)
        self.assertEqual(self.send({**self.body,'sequence':2}).status_code,409)

    def test_camera_client_packet_roundtrips_through_real_web_contract(self):
        root=Path(__file__).resolve().parents[1]/'edge-vision'
        sys.path.insert(0,str(root));self.addCleanup(lambda:sys.path.remove(str(root)))
        from src.web.client import PoseClient
        spec=importlib.util.spec_from_file_location('publish_pose_contract',root/'scripts/publish_pose.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        calibration=type('Calibration',(),{'config':{'frame_id':'pool-01','calibration_id':'test'}})()
        pose={'timestamp':datetime.now(timezone.utc).timestamp(),'frame_id':1,'tracking_valid':True,
              'x':.15,'y':.2,'heading':90,'status':'tracked'}
        packet=module.packet(pose,site='site-a',camera='camera-01',session=str(uuid4()),
                             sequence=1,calibration=calibration,offset_measured=True)
        backend=self.client
        class Opener:
            def open(self,request,timeout):
                response=backend.post('/api/edge/pose',content=request.data,headers=dict(request.header_items()))
                if response.status_code!=200:raise AssertionError(response.text)
                return io.BytesIO(response.content)
        receipt=PoseClient('https://example.test','k'*40,opener=Opener()).send(packet)
        self.assertFalse(receipt['command_issued']);self.assertEqual(receipt['accepted_sequence'],1)
        with self.edge.sessions() as db:
            stored=json.loads(db.query(models.EdgePose).one().payload_json)
            self.assertEqual(stored['pose']['heading'],90)


if __name__=='__main__':unittest.main()
