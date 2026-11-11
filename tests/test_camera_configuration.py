import json
import unittest
from unittest.mock import AsyncMock, patch

import test_edge_receiver
from backend.platform import models
from backend.platform.deps import require_admin
from backend.platform.routers import camera_settings, vision


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.edge=test_edge_receiver.EdgeTests();self.edge.setUp();self.addCleanup(self.edge.doCleanups)
        self.edge.app.include_router(camera_settings.router,prefix='/api');self.client=self.edge.client
        self.query='?site_id=site-a'
        self.homography={'enabled':True,'image_size':[1280,720],
            'image_points':[{'x':10,'y':10},{'x':90,'y':10},{'x':90,'y':90},{'x':10,'y':90}],
            'pool_width_m':.8,'pool_height_m':.8,'frame_id':'pool-01'}

    def tearDown(self):self.edge.tearDown()
    def admin(self):
        self.edge.authorize_reader()
        self.edge.app.dependency_overrides[require_admin]=lambda:type('Admin',(),{'username':'test-admin'})()
    def get(self):return self.client.get('/api/vision/configuration'+self.query)
    def put(self,part,body):return self.client.put('/api/vision/configuration/'+part+self.query,json=body)

    def test_auth_and_separate_write_permission(self):
        self.assertEqual(self.get().status_code,401)
        self.edge.authorize_reader()
        self.assertEqual(self.get().status_code,200)
        self.assertEqual(self.put('homography',self.homography).status_code,401)
        self.admin()
        self.assertEqual(self.client.get('/api/vision/configuration?site_id=other').status_code,403)

    def test_independent_settings_survive_new_requests_and_revision_increases(self):
        self.admin()
        initial=self.get().json();self.assertFalse(initial['homography']['enabled']);self.assertFalse(initial['aruco']['enabled'])
        saved=self.put('homography',self.homography)
        self.assertEqual(saved.status_code,200,saved.text);self.assertEqual(saved.json()['revision'],1)
        calibration_id=saved.json()['homography']['calibration_id']
        marker=self.put('aruco',{'enabled':True,'marker_id':3,'marker_size_m':.1})
        self.assertEqual(marker.status_code,200,marker.text)
        self.assertEqual(marker.json()['homography']['calibration_id'],calibration_id)
        self.assertTrue(marker.json()['homography']['enabled']);self.assertEqual(marker.json()['revision'],2)
        result=self.get().json();self.assertEqual(result['aruco']['marker_id'],3)
        self.assertFalse(result['aruco']['heading_measured'])
        self.put('homography',{'enabled':False})
        result=self.get().json();self.assertTrue(result['aruco']['enabled']);self.assertFalse(result['homography']['enabled'])
        with self.edge.sessions() as db:
            self.assertEqual(db.query(models.CameraConfiguration).count(),1)
            self.assertEqual(db.query(models.Event).count(),0)

    def test_invalid_geometry_and_marker_values_are_rejected(self):
        self.admin()
        for points in ([{'x':10,'y':10}]*4,list(reversed(self.homography['image_points'])),
                       [{'x':-1,'y':10},*self.homography['image_points'][1:]]):
            self.assertEqual(self.put('homography',{**self.homography,'image_points':points}).status_code,422)
        self.assertEqual(self.put('homography',{**self.homography,'pool_width_m':0}).status_code,422)
        for body in ({'marker_id':50},{'dictionary':'UNKNOWN'},{'heading_measured':True},
                     {'marker_size_m':0},{'heading_offset_deg':181}):
            self.assertEqual(self.put('aruco',body).status_code,422,body)

    def test_stream_gets_saved_settings_and_requires_revision_ack(self):
        self.admin();self.put('homography',self.homography)
        async def forward(path,method,identity,body=None,content_type=None):
            if method=='DELETE':return {'closed':True}
            sent=json.loads(body);self.assertTrue(sent['configuration']['homography']['enabled'])
            return {'stream_id':'test-stream','configuration_revision':1}
        with patch.object(vision,'forward',side_effect=forward):
            result=self.client.post('/api/vision/streams'+self.query)
            self.assertEqual(result.status_code,201,result.text)
        with patch.object(vision,'forward',new_callable=AsyncMock,return_value={'stream_id':'test-stream'}) as remote:
            self.assertEqual(self.client.post('/api/vision/streams'+self.query).status_code,502)
            self.assertEqual(remote.call_args.args[1],'DELETE')

    def test_marker_and_inspection_use_authenticated_proxy_and_saved_profile(self):
        self.admin();self.put('aruco',{'enabled':True,'marker_id':3})
        with patch.object(camera_settings,'forward',new_callable=AsyncMock,return_value={'configuration_revision':1}) as remote:
            result=self.client.post('/api/vision/configuration/inspect'+self.query,
                files={'image':('frame.jpg',b'jpeg','image/jpeg')})
            self.assertEqual(result.status_code,200)
            sent=json.loads(remote.call_args.args[3]);self.assertEqual(sent['configuration']['aruco']['marker_id'],3)
            self.assertEqual(remote.call_args.args[2][1],'site-a')
            result=self.client.post('/api/vision/aruco/marker'+self.query,json={'marker_id':4})
            self.assertEqual(result.status_code,200);self.assertIn('/v1/vision/marker',remote.call_args.args)
        self.assertEqual(self.client.post('/api/vision/configuration/inspect'+self.query,
            files={'image':('x',b'x','text/plain')}).status_code,415)


if __name__=='__main__':unittest.main()
