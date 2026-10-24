"""Regression checks for the unified local application (no camera hardware required)."""
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import app, platform_backend, config
from backend.app.database import Base, get_db
from backend.platform.database import Base as PlatformBase
from backend.platform.routers import camera as camera_routes
from backend.platform.camera import CameraUnavailable


class UnifiedServerTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        self.sessions = sessionmaker(bind=self.engine)
        self.patches = [patch.object(platform_backend, 'engine', self.engine),
                        patch.object(platform_backend, 'SessionLocal', self.sessions),
                        patch.object(camera_routes, 'SessionLocal', self.sessions)]
        for item in self.patches:
            item.start()
        def db():
            with self.sessions() as session:
                yield session
        app.dependency_overrides[get_db] = db
        self.client = TestClient(app)
        self.client.__enter__()
        response = self.client.post('/api/auth/login', data={'username': config.ADMIN_ID, 'password': config.ADMIN_PW})
        self.assertEqual(response.status_code, 200)
        self.headers = {'Authorization': 'Bearer ' + response.json()['access_token']}

    def tearDown(self):
        self.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        for item in reversed(self.patches):
            item.stop()
        self.engine.dispose()

    def test_shared_database_and_routes(self):
        self.assertIs(Base, PlatformBase)
        for path in ['/api/auth/me', '/api/sites', '/api/status', '/api/config/judge',
                     '/api/mission/events', '/api/events', '/api/boat/command', '/dashboard.html']:
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, headers=self.headers).status_code, 200)
        paths = self.client.get('/api/openapi.json').json()['paths']
        self.assertIn('/api/ai/frame', paths)
        self.assertIn('/api/judgement/ai/frame', paths)

    def test_camera_analysis_authentication_validation_and_raw_verdict(self):
        from unittest.mock import AsyncMock
        from backend.platform.routers import camera_analysis
        path = '/api/camera/analyze'
        self.assertEqual(self.client.post(path, files={'image': ('frame.jpg', b'image', 'image/jpeg')}).status_code, 401)
        result = {'detections': [{'class': 'human_dummy', 'water_state': 'DROWNING',
                                  'confidence': 0.8, 'bbox': [1, 2, 30, 40]}],
                  'image_size': [640, 480]}
        with patch.object(camera_analysis.ai_client, 'detect', new_callable=AsyncMock, return_value=result) as detect:
            response = self.client.post(path, headers=self.headers,
                                        files={'image': ('frame.jpg', b'image', 'image/jpeg')}, data={'frame_id': '4'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), result)
            detect.assert_awaited_once_with(b'image', 'frame.jpg', 'image/jpeg', 4)
        for body, kind, status in [(b'', 'image/jpeg', 400), (b'x', 'text/plain', 415),
                                    (b'x' * (5*1024*1024+1), 'image/jpeg', 413)]:
            response = self.client.post(path, headers=self.headers, files={'image': ('frame', body, kind)})
            self.assertEqual(response.status_code, status)

    def test_camera_analysis_empty_detection_and_upstream_error(self):
        from unittest.mock import AsyncMock
        from backend.platform.routers import camera_analysis
        path = '/api/camera/analyze'
        with patch.object(camera_analysis.ai_client, 'detect', new_callable=AsyncMock, return_value={'detections': []}):
            response = self.client.post(path, headers=self.headers, files={'image': ('frame.jpg', b'image', 'image/jpeg')})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['detections'], [])
        with patch.object(camera_analysis.ai_client, 'detect', new_callable=AsyncMock,
                          side_effect=camera_analysis.ai_client.AIClientError('AI 서버 응답 시간 초과')):
            response = self.client.post(path, headers=self.headers, files={'image': ('frame.jpg', b'image', 'image/jpeg')})
            self.assertEqual(response.status_code, 502)

    def test_camera_requires_login_and_streams_jpeg(self):
        path = '/api/sites/chunjeon/camera/stream'
        self.assertEqual(self.client.get(path).status_code, 401)
        class FakeCamera:
            def start(self):
                pass
            async def next_frame(self, after=-1):
                if after == -1:
                    return 1, b'\xff\xd8test\xff\xd9'
                raise CameraUnavailable('test complete')
        with patch.object(camera_routes, 'camera', FakeCamera()):
            response = self.client.get(path, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn('multipart/x-mixed-replace', response.headers['content-type'])
        self.assertIn(b'\xff\xd8test\xff\xd9', response.content)

    def test_maintenance_route_keeps_admin_guard(self):
        self.assertEqual(self.client.post('/api/maintenance/reset').status_code, 401)
        self.assertEqual(self.client.post('/api/maintenance/reset', headers=self.headers).status_code, 200)


if __name__ == '__main__':
    unittest.main()
