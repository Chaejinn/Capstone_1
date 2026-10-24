"""Bridge HTTP -> durable packet -> phone polling contract, isolated from hardware."""
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.platform.database import Base, get_db
from backend.platform.deps import require_operator_or_admin
from backend.platform.routers.test_signals import router


class SignalReceiverTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        sessions = sessionmaker(bind=self.engine)
        self.app = FastAPI()
        self.app.include_router(router, prefix='/api')
        def db():
            with sessions() as session:
                yield session
        self.app.dependency_overrides[get_db] = db
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()

    def authorize(self):
        self.app.dependency_overrides[require_operator_or_admin] = lambda: object()

    def test_auth_required_for_send_and_receive(self):
        for response in [self.client.get('/api/test-signals'), self.client.post('/api/test-signals', json={})]:
            self.assertEqual(response.status_code, 401)

    def test_bridge_packet_reaches_phone_once_with_cursor(self):
        self.authorize()
        baseline = self.client.get('/api/test-signals?latest=true').json()
        self.assertEqual(baseline, {'signals': [], 'cursor': 0})
        packet = self.client.post('/api/test-signals', json={'source': 'bridge', 'message': '임의 신호'})
        self.assertEqual(packet.status_code, 201)
        received = self.client.get('/api/test-signals?after_id=0').json()
        self.assertEqual(received['signals'], [packet.json()])
        self.assertTrue(packet.json()['test'])
        self.assertTrue(packet.json()['created_at'].endswith('Z'))
        cursor = received['cursor']
        self.assertEqual(self.client.get(f'/api/test-signals?after_id={cursor}').json()['signals'], [])
        self.assertEqual(self.client.get('/api/test-signals?latest=true').json()['cursor'], cursor)

    def test_validation_and_ordered_backlog(self):
        self.authorize()
        for body in [{'message': '  '}, {'source': ''}, {'message': 'x' * 501}, {'unexpected': True}]:
            self.assertEqual(self.client.post('/api/test-signals', json=body).status_code, 422)
        self.assertEqual(self.client.get('/api/test-signals?after_id=-1').status_code, 422)
        for _ in range(102):
            self.client.post('/api/test-signals', json={})
        first = self.client.get('/api/test-signals').json()
        self.assertEqual([s['id'] for s in first['signals']], list(range(1, 101)))
        rest = self.client.get(f"/api/test-signals?after_id={first['cursor']}").json()
        self.assertEqual([s['id'] for s in rest['signals']], [101, 102])


if __name__ == '__main__':
    unittest.main()
