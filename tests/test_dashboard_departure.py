import time
import unittest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.platform.database import Base, get_db
from backend.platform.routers import board_control as control
from scripts.dashboard_departure_bridge import Departure


class DepartureTests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.sessions=sessionmaker(bind=self.engine)
        app=FastAPI()
        app.include_router(control.router)
        def db():
            with self.sessions() as session:
                yield session
        app.dependency_overrides[get_db]=db
        app.dependency_overrides[control.scope]=lambda: ('owner','site',{})
        self.client=TestClient(app)
        self.bridge={'bridge_id':str(uuid4())}
        self.evidence={'stream_id':str(uuid4()),'frame_id':22}
        self.analysis=dict(expired=False,frame_id=22,detections=[dict(
            confirmed=True,coordinate_valid=True,track_id=3,track_generation=1,
            confirmed_at=datetime.now(timezone.utc).isoformat(),consecutive_frames=15,
            drowning_score=.9,target_x_m=1.2,target_y_m=2.4)])
        self.forward=patch.object(control,'forward',new_callable=AsyncMock).start()
        self.forward.return_value={'analysis':self.analysis}

    def tearDown(self):
        patch.stopall()
        self.client.close()
        self.engine.dispose()

    def connect(self):
        self.assertEqual(self.client.post('/board-control/connect',json=self.bridge).status_code,200)

    def dispatch(self):
        return self.client.post('/board-control/dispatch',json=self.evidence)

    def test_no_bridge_blocks_and_server_fetches_its_own_evidence(self):
        self.assertEqual(self.dispatch().status_code,409)
        self.forward.assert_awaited_once()

    def test_confirmed_departure_is_bounded_and_never_reissued(self):
        self.connect()
        self.assertEqual(self.dispatch().json()['status'],'ISSUED')
        packet=self.client.post('/board-control/poll',json=self.bridge).json()
        self.assertEqual((packet['command'],packet['throttle'],packet['max_seconds']),('DISPATCH',5,3))
        revision=packet['revision']
        self.assertEqual(self.dispatch().json()['status'],'ALREADY_ISSUED')
        self.assertEqual(self.client.post('/board-control/poll',json=self.bridge).json()['revision'],revision)
        self.connect()
        self.assertEqual(self.dispatch().json()['status'],'ALREADY_ISSUED')

    def test_estop_latches_and_blocks_later_dispatch(self):
        self.connect()
        self.client.post('/board-control/stop')
        self.assertEqual(self.dispatch().status_code,409)
        self.assertEqual(self.client.post('/board-control/poll',json=self.bridge).json()['command'],'ESTOP')

    def test_rejects_stale_unconfirmed_missing_coordinates_and_wrong_frame(self):
        self.connect()
        item=self.analysis['detections'][0]
        for key,value in [('confirmed',False),('coordinate_valid',False),('consecutive_frames',14),
                          ('drowning_score',.79),('target_x_m',float('nan')),
                          ('confirmed_at','2000-01-01T00:00:00+00:00')]:
            old=item[key]
            item[key]=value
            self.assertEqual(self.dispatch().status_code,409,key)
            item[key]=old
        self.analysis['expired']=True
        self.assertEqual(self.dispatch().status_code,409)
        self.analysis['expired']=False
        self.analysis['frame_id']=21
        self.assertEqual(self.dispatch().status_code,409)

    def test_expired_lease_stops_and_other_bridge_cannot_poll(self):
        self.connect()
        other={'bridge_id':str(uuid4())}
        self.assertEqual(self.client.post('/board-control/connect',json=other).status_code,409)
        self.assertEqual(self.client.post('/board-control/poll',json=other).status_code,409)
        with self.sessions() as db:
            row=db.get(control.Channel,'site')
            row.lease_until=0
            db.commit()
        self.assertEqual(self.dispatch().status_code,409)
        self.assertEqual(self.client.post('/board-control/poll',json=self.bridge).json()['command'],'ESTOP')

    def test_watchdog_stops_without_network_and_hard_limits_remote_values(self):
        class Board:
            def __init__(self): self.lines=[]
            def write(self,line): self.lines.append(line)
            def flush(self): pass
        board=Board()
        drive=Departure(board)
        drive.start(dict(max_seconds=100,expires_at=time.time()+100,throttle=5))
        self.assertLessEqual(drive.until-time.monotonic(),3)
        drive.until=time.monotonic()-1
        class Tick:
            calls=0
            def wait(self,_):
                self.calls+=1
                return self.calls>1
            def set(self): pass
        drive.watchdog(Tick())
        self.assertEqual(board.lines[-1],b'S\n')
        self.assertEqual(drive.until,0)
        count=len(board.lines)
        drive.start(dict(max_seconds=3,expires_at=time.time()-1,throttle=5))
        self.assertEqual(len(board.lines),count)


if __name__=='__main__':
    unittest.main()
