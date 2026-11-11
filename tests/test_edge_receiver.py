"""External observations stay durable and cannot become dispatch commands."""
import os
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.platform import models
from backend.platform.database import Base, get_db
from backend.platform.deps import require_operator_or_admin
from backend.platform.routers.edge import router
from backend.platform.routers import vision


class EdgeTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"DG_EDGE_INGEST_KEY": "k" * 40,
            "DG_EDGE_SITE_ID": "site-a", "DG_EDGE_CAMERA_ID": "camera-01"})
        self.env.start(); self.addCleanup(self.env.stop)
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine)
        with self.sessions() as db:
            db.add(models.Site(id='site-a', name='A', enabled=True)); db.commit()
        self.app = FastAPI(); self.app.include_router(router, prefix='/api')
        self.app.include_router(vision.router, prefix='/api')
        def database():
            with self.sessions() as db:
                yield db
        self.app.dependency_overrides[get_db] = database
        self.client = TestClient(self.app)
        self.headers = {'Authorization': 'Bearer ' + 'k' * 40}
        self.body = {'event_id': 'event-1', 'track_id': 7, 'site_id': 'site-a',
                     'camera_id': 'camera-01', 'state': 'DROWNING', 'confidence': 1,
                     'confidence_source': 'vote_ratio',
                     'captured_at': datetime.now(timezone.utc).isoformat()}

    def tearDown(self):
        self.client.close(); self.engine.dispose()

    def send(self, body=None, headers=None):
        return self.client.post('/api/edge/classification', json=body or self.body,
                                headers=self.headers if headers is None else headers)

    def authorize_reader(self):
        self.app.dependency_overrides[require_operator_or_admin] = lambda: type('User', (), {'id': 1})()

    def test_service_and_reader_auth_are_separate(self):
        self.assertEqual(self.send(headers={}).status_code, 401)
        self.assertEqual(self.client.get('/api/edge/latest?site_id=site-a&camera_id=camera-01', headers=self.headers).status_code, 401)
        self.assertEqual(self.send({**self.body, 'site_id':'other'}).status_code, 403)
        self.assertEqual(self.send({**self.body, 'camera_id':'other'}).status_code, 403)

    def test_observation_is_durable_idempotent_and_never_dispatches(self):
        first = self.send(); self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self.send().json()['observation_id'], first.json()['observation_id'])
        self.authorize_reader()
        # Each HTTP request opens a separate database session, with no memory counter.
        result = self.client.get('/api/edge/latest?site_id=site-a&camera_id=camera-01')
        self.assertEqual(result.headers['cache-control'], 'no-store')
        self.assertFalse(result.json()['command_issued'])
        self.assertFalse(result.json()['judgement_verified'])
        self.assertIsNone(result.json()['observation']['drowning_score'])
        self.assertFalse(result.json()['expired'])
        with self.sessions() as db:
            self.assertEqual(db.query(models.EdgeJudgement).count(), 1)
            self.assertEqual(db.query(models.Event).count(), 0)
        self.assertEqual(self.send({**self.body, 'state':'SWIMMING'}).status_code, 409)

    def test_legacy_labels_missing_time_and_conflicting_labels(self):
        legacy = {k:v for k,v in self.body.items() if k not in ('event_id','state','captured_at')}
        response = self.send({**legacy, 'request_id':'legacy', 'classification':'drowning'})
        self.assertEqual(response.status_code, 200, response.text)
        self.authorize_reader()
        self.assertTrue(self.client.get('/api/edge/latest?site_id=site-a&camera_id=camera-01').json()['expired'])
        self.assertEqual(self.send({**self.body, 'classification':'normal_swimming'}).status_code, 422)

    def test_future_stale_naive_and_oversize_requests(self):
        for delta in (1.5, -31):
            timestamp = (datetime.now(timezone.utc)+timedelta(seconds=delta)).isoformat()
            response = self.send({**self.body, 'captured_at':timestamp})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()['detail']['code'], 'INVALID_TIMESTAMP')
        self.assertEqual(self.send({**self.body, 'captured_at':'2026-11-11T10:00:00'}).status_code, 422)
        response = self.client.post('/api/edge/classification', content='x'*65537, headers=self.headers)
        self.assertEqual(response.status_code, 413)

    def test_disabled_site_and_unconfigured_service(self):
        with self.sessions() as db:
            db.query(models.Site).update({'enabled':False}); db.commit()
        self.assertEqual(self.send().status_code, 403)
        with patch.dict(os.environ, {'DG_EDGE_INGEST_KEY':''}):
            self.assertEqual(self.send().status_code, 503)

    def test_hybrid_proxy_uses_authenticated_scope_and_has_no_cache(self):
        url = '/api/vision/edge/camera-01?site_id=site-a'
        self.assertEqual(self.client.get(url).status_code, 401)
        self.authorize_reader()
        with patch.object(vision, 'forward', new_callable=AsyncMock, return_value={'analysis':None}) as forward:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers['cache-control'], 'no-store')
            args = forward.call_args.args
            self.assertEqual(args[:2], ('/v1/edge/camera-01','GET'))
            self.assertEqual(args[2][1], 'site-a')
            self.assertNotEqual(args[2][0], '1')
            frame = self.client.get('/api/vision/edge/camera-01/frames/1?site_id=site-a&session_id=bad')
            self.assertEqual(frame.status_code, 422)


if __name__ == '__main__':
    unittest.main()
