import json
import unittest
from unittest.mock import AsyncMock, patch

import test_edge_receiver
from backend.platform import models
from backend.platform.deps import require_admin
from backend.platform.routers import camera_settings, vision
from backend.platform.camera_configuration import Homography, fit_homography


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

    def test_preview_validates_without_saving_configuration(self):
        path='/api/vision/configuration/homography/validate'+self.query
        self.assertEqual(self.client.post(path,json=self.homography).status_code,401)
        self.edge.authorize_reader()
        before=self.get().json()
        response=self.client.post(path,json=self.homography)
        self.assertEqual(response.status_code,200,response.text)
        report=response.json()
        self.assertTrue(report['valid']);self.assertFalse(report['saved']);self.assertFalse(report['command_issued'])
        self.assertEqual(report['homography_report']['point_count'],4)
        self.assertLess(report['homography_report']['max_error_m'],1e-8)
        invalid={**self.homography,'image_size':None}
        self.assertEqual(self.client.post(path,json=invalid).status_code,422)
        self.assertEqual(self.client.post(path.replace('site-a','other'),json=self.homography).status_code,403)
        self.assertEqual(self.get().json(),before)
        with self.edge.sessions() as db:
            self.assertEqual(db.query(models.CameraConfiguration).count(),0)

    def test_independent_check_point_projects_and_reports_measured_error(self):
        path='/api/vision/configuration/homography/check-point'+self.query
        body={'homography':self.homography,'image_point':{'x':50,'y':50},
              'measured_point':{'x':.43,'y':.44}}
        self.assertEqual(self.client.post(path,json=body).status_code,401)
        self.edge.authorize_reader();before=self.get().json()
        response=self.client.post(path,json=body)
        self.assertEqual(response.status_code,200,response.text);result=response.json()
        self.assertAlmostEqual(result['projected_point']['x'],.4)
        self.assertAlmostEqual(result['projected_point']['y'],.4)
        self.assertAlmostEqual(result['error_m'],.05)
        self.assertFalse(result['saved']);self.assertFalse(result['command_issued'])
        for point in ({'x':10,'y':10},{'x':2,'y':2}):
            self.assertEqual(self.client.post(path,json={**body,'image_point':point}).status_code,422)
        lower=self.client.post(path,json={**body,'image_point':{'x':50,'y':70}}).json()
        self.assertLess(lower['projected_point']['y'],result['projected_point']['y'])
        self.assertEqual(self.get().json(),before)

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

    def test_hundreds_of_points_persist_and_have_per_point_errors(self):
        self.admin()
        extra=[{'x':10+i*80/32,'y':10+j*80/32} for i in range(1,32) for j in range(1,32)]
        body={**self.homography,'image_points':self.homography['image_points']+extra,
              'world_points':[{'x':0,'y':.8},{'x':.8,'y':.8},{'x':.8,'y':0},{'x':0,'y':0}]
              +[{'x':(p['x']-10)/100,'y':(90-p['y'])/100} for p in extra]}
        response=self.put('homography',body)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['homography_report']['point_count'],965)
        self.assertEqual(len(response.json()['homography_report']['point_errors_m']),965)
        self.assertLess(response.json()['homography_report']['max_error_m'],1e-8)
        loaded=self.get().json();self.assertEqual(len(loaded['homography']['image_points']),965)
        self.assertEqual(len(loaded['homography']['world_points']),965)

    def test_added_correspondence_changes_fit_and_invalid_pairs_are_rejected(self):
        import numpy as np
        self.admin()
        body={**self.homography,'image_points':self.homography['image_points']+[{'x':50,'y':50}],
            'world_points':[{'x':0,'y':.8},{'x':.8,'y':.8},{'x':.8,'y':0},{'x':0,'y':0},{'x':.405,'y':.4}]}
        h=Homography.model_validate(body);matrix,report=fit_homography(h)
        projected=matrix@np.array([50,50,1]);self.assertGreater(projected[0]/projected[2],.4001)
        self.assertGreater(report['rms_error_m'],0)
        self.assertEqual(self.put('homography',body).status_code,200)
        self.assertEqual(self.put('homography',{**body,'world_points':None}).status_code,422)
        wrong={**body,'world_points':body['world_points'][:-1]+[{'x':.7,'y':.1}]}
        self.assertEqual(self.put('homography',wrong).status_code,422)
        outside={**body,'image_points':body['image_points'][:-1]+[{'x':99,'y':50}]}
        self.assertEqual(self.put('homography',outside).status_code,422)


if __name__=='__main__':unittest.main()
