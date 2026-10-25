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
from backend.platform.routers.test_control import router as control_router


class SignalReceiverTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        sessions = sessionmaker(bind=self.engine)
        self.app = FastAPI()
        self.app.include_router(router, prefix='/api')
        self.app.include_router(control_router, prefix='/api')
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

    def test_simulated_control_sequence_and_phone_receipt(self):
        from backend.app.routers.boat import boat_control
        before = boat_control.read()
        self.authorize()
        self.assertEqual(self.client.get('/api/test-control?latest=true').json()['cursor'], 0)
        for command, expected in [('DISPATCH', 'DISPATCHED'), ('ESTOP', 'STOPPED')]:
            response = self.client.post('/api/test-control', json={'command': command, 'target_x': 12, 'target_y': 3})
            self.assertEqual(response.status_code, 201)
            self.assertEqual(response.json()['state']['status'], expected)
        for command in ['DISPATCH', 'RETURN', 'DEPLOY', 'COMPLETE', 'CANCEL']:
            self.assertEqual(self.client.post('/api/test-control', json={'command': command}).status_code, 409)
        cleared = self.client.post('/api/test-control', json={'command': 'CLEAR_ESTOP'}).json()
        self.assertEqual(cleared['state'], {'status': 'IDLE', 'estop': False, 'target': None})
        for command, status in [('DISPATCH', 'DISPATCHED'), ('CANCEL', 'CANCELLED'),
                                ('DISPATCH', 'DISPATCHED'), ('DEPLOY', 'DEPLOYING'),
                                ('RETURN', 'RETURNING'), ('COMPLETE', 'COMPLETED'), ('RESET', 'IDLE')]:
            self.assertEqual(self.client.post('/api/test-control', json={'command': command}).json()['state']['status'], status)
        received = self.client.get('/api/test-control').json()
        self.assertEqual(len(received['packets']), 10)
        self.assertEqual(received['packets'][0]['state']['target'], {'x': 12, 'y': 3})
        self.assertEqual(received['packets'][0]['command'], 'DISPATCH')
        self.assertEqual(self.client.get(f"/api/test-control?after_id={received['cursor']}").json()['packets'], [])
        self.assertEqual(len(self.client.get('/api/test-signals').json()['signals']), 10)
        self.assertEqual(boat_control.read(), before)

    def test_control_auth_and_validation(self):
        self.assertEqual(self.client.post('/api/test-control', json={'command': 'ESTOP'}).status_code, 401)
        self.assertEqual(self.client.get('/api/test-control').status_code, 401)
        self.authorize()
        for body in [{'command': 'UNKNOWN'}, {'command': 'DISPATCH', 'target_x': 'nan'},
                     {'command': 'ESTOP', 'unexpected': True}]:
            self.assertEqual(self.client.post('/api/test-control', json=body).status_code, 422)

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

    def test_dispatch_test_signal_reaches_receiver(self):
        self.authorize()
        body = {'source': 'dispatch-test', 'message': '[출동명령 테스트] 지정 위치로 출동 요청'}
        sent = self.client.post('/api/test-signals', json=body)
        self.assertEqual(sent.status_code, 201)
        signals = self.client.get('/api/test-signals?after_id=0').json()['signals']
        self.assertEqual(signals, [sent.json()])
        self.assertEqual(signals[0]['source'], body['source'])
        self.assertEqual(signals[0]['message'], body['message'])
        self.assertTrue(signals[0]['test'])


if __name__ == '__main__':
    unittest.main()
