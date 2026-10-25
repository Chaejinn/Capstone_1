"""Random server runs and real Web Push encryption, without external delivery."""
import asyncio
import base64
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.platform.database import Base, get_db
from backend.platform.deps import require_operator_or_admin
from backend.platform.models import User
from backend.platform.routers import test_push
from backend.platform.test_automation import Automation, random_command


def sessions():
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine, sessionmaker(bind=engine)


class AutomaticSignalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine, self.sessions = sessions()
        self.patches = [patch('backend.platform.test_automation.SessionLocal', self.sessions),
                        patch('backend.platform.test_automation.test_push.deliver'),
                        patch('backend.platform.test_automation.config.IS_VERCEL', False)]
        for item in self.patches:
            item.start()
        self.auto = Automation()

    async def asyncTearDown(self):
        await self.auto.stop()
        for item in reversed(self.patches):
            item.stop()
        self.engine.dispose()

    async def test_single_run_survives_without_browser_and_stops(self):
        with patch('backend.platform.test_automation.random.uniform', return_value=0.001):
            self.auto.start()
            task = self.auto.task
            deadline = self.auto.ends_at
            self.auto.start()
            self.assertIs(self.auto.task, task)
            self.assertEqual(deadline, self.auto.ends_at)
            for _ in range(100):
                if self.auto.generated >= 3:
                    break
                await asyncio.sleep(0.005)
            self.assertGreaterEqual(self.auto.generated, 3)
            await self.auto.stop()
            count = self.auto.generated
            await asyncio.sleep(0.01)
            self.assertEqual(self.auto.generated, count)
            self.assertFalse(self.auto.status()['running'])
            from backend.platform.routers.test_control import TestCommand
            with self.sessions() as db:
                self.assertEqual(db.query(TestCommand).count(), count)

    async def test_run_expires_without_emitting_more_commands(self):
        self.auto.start()
        self.auto.ends_at = time.monotonic() - 1
        await self.auto.task
        self.assertFalse(self.auto.status()['running'])
        self.assertEqual(self.auto.generated, 0)

    async def test_vercel_rejects_background_run(self):
        with patch('backend.platform.test_automation.config.IS_VERCEL', True):
            with self.assertRaises(HTTPException) as error:
                self.auto.start()
        self.assertEqual(error.exception.status_code, 409)

    async def test_estop_requires_release_before_random_dispatch(self):
        self.assertEqual(random_command({'estop': True, 'status': 'STOPPED'}), 'CLEAR_ESTOP')
        self.assertEqual(random_command({'estop': False, 'status': 'IDLE'}), 'DISPATCH')


@unittest.skipIf(test_push.webpush is None, 'Install pywebpush to verify push encryption')
class PushSignalTests(unittest.TestCase):
    def setUp(self):
        self.engine, self.sessions = sessions()
        with self.sessions() as db:
            db.add(User(username='operator', password_hash='unused', name='test', role='operator', active=True))
            db.commit()
        self.app = FastAPI()
        self.app.include_router(test_push.router, prefix='/api')
        def db():
            with self.sessions() as session:
                yield session
        self.app.dependency_overrides[get_db] = db
        self.client = TestClient(self.app)
        self.owner = SimpleNamespace(username='operator')
        self.app.dependency_overrides[require_operator_or_admin] = lambda: self.owner
        public = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.subscription = {'endpoint': 'https://fcm.googleapis.com/fcm/send/test-device',
                             'keys': {'p256dh': base64.urlsafe_b64encode(public).decode().rstrip('='),
                                      'auth': base64.urlsafe_b64encode(b'0123456789abcdef').decode().rstrip('=')}}
        self.session_patch = patch.object(test_push, 'SessionLocal', self.sessions)
        self.session_patch.start()

    def tearDown(self):
        self.session_patch.stop()
        self.client.close()
        self.engine.dispose()

    def test_key_persistence_subscription_and_real_encrypted_delivery(self):
        key = self.client.get('/api/test-push').json()['public_key']
        self.assertEqual(self.client.get('/api/test-push').json()['public_key'], key)
        for _ in range(2):
            self.assertEqual(self.client.post('/api/test-push', json=self.subscription).status_code, 201)
        response = Mock(status_code=201)
        with patch('pywebpush.requests.post', return_value=response) as post:
            test_push.deliver({'id': 1, 'message': '[제어 테스트] 출동'})
        self.assertEqual(post.call_count, 1)
        self.assertIsInstance(post.call_args.kwargs['data'], bytes)
        self.assertNotIn('출동'.encode(), post.call_args.kwargs['data'])
        self.assertIn('authorization', {name.lower() for name in post.call_args.kwargs['headers']})
        self.assertEqual(self.client.get('/api/test-push').json()['devices'][0]['status'], 'accepted')
        self.assertEqual(self.client.request('DELETE', '/api/test-push', json=self.subscription).status_code, 200)
        self.assertEqual(self.client.get('/api/test-push').json()['devices'], [])

    def test_expired_subscription_removed_and_transient_failure_recorded(self):
        self.client.post('/api/test-push', json=self.subscription)
        for status in (503, 410):
            error = test_push.WebPushException('mock delivery failure', response=Mock(status_code=status))
            with patch.object(test_push, 'webpush', side_effect=error):
                test_push.deliver({'id': 1, 'message': 'test'})
            devices = self.client.get('/api/test-push').json()['devices']
            if status == 503:
                self.assertEqual(devices[0]['status'], 'failed:503')
            else:
                self.assertEqual(devices, [])

    def test_push_requires_auth_and_rejects_arbitrary_targets(self):
        self.app.dependency_overrides.clear()
        self.assertEqual(self.client.get('/api/test-push').status_code, 401)
        self.app.dependency_overrides[require_operator_or_admin] = lambda: self.owner
        for endpoint in ('http://127.0.0.1/private', 'https://example.com/push', 'https://fcm.googleapis.com:8080/push'):
            self.assertEqual(self.client.post('/api/test-push', json={**self.subscription, 'endpoint': endpoint}).status_code, 422)
