import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import config, models, security
from app.camera import Camera, CameraUnavailable, mjpeg_part
from app.database import Base
from app.routers import camera as routes


@pytest.fixture
def client(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add(models.User(username='viewer', password_hash='unused', name='Viewer', role='operator', active=True))
        db.add(models.Site(id='test', name='Test', meta='', status='운영중', enabled=True))
        db.add(models.Site(id='off', name='Off', meta='', status='준비중', enabled=False))
        db.add(models.Site(id='other', name='Other', meta='', status='운영중', enabled=True))
        db.commit()
    monkeypatch.setattr(routes, 'SessionLocal', sessions)
    monkeypatch.setattr(config, 'CAMERA_SITE_ID', 'test')
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        yield client
    engine.dispose()


def headers():
    return {'Authorization': 'Bearer ' + security.create_access_token({'sub': 'viewer'})}


class FakeCamera:
    def __init__(self, fail=False):
        self.started = False
        self.fail = fail

    def start(self):
        self.started = True

    async def next_frame(self, after=-1):
        if self.fail or after != -1:
            raise CameraUnavailable('camera disconnected')
        return 1, b'\xff\xd8test\xff\xd9'


def test_multipart_stream(client, monkeypatch):
    fake = FakeCamera()
    monkeypatch.setattr(routes, 'camera', fake)
    response = client.get('/sites/test/camera/stream', headers=headers())
    assert response.status_code == 200
    assert response.headers['content-type'] == 'multipart/x-mixed-replace; boundary=frame'
    assert response.headers['cache-control'] == 'no-store'
    assert response.content == mjpeg_part(b'\xff\xd8test\xff\xd9') + b'--frame--\r\n'
    assert fake.started


@pytest.mark.parametrize('site,auth,status', [('test',False,401), ('missing',True,404), ('off',True,403), ('other',True,404)])
def test_access_before_capture(client, monkeypatch, site, auth, status):
    fake = FakeCamera()
    monkeypatch.setattr(routes, 'camera', fake)
    response = client.get(f'/sites/{site}/camera/stream', headers=headers() if auth else {})
    assert response.status_code == status
    assert not fake.started


def test_unavailable_returns_503(client, monkeypatch):
    monkeypatch.setattr(routes, 'camera', FakeCamera(fail=True))
    response = client.get('/sites/test/camera/stream', headers=headers())
    assert response.status_code == 503
    assert response.json()['detail'] == 'camera disconnected'


def test_shared_capture_and_release(monkeypatch):
    import cv2
    import numpy as np

    captures = []

    class Capture:
        def __init__(self, source):
            captures.append(self)
            self.released = False

        def isOpened(self):
            return True

        def set(self, *args):
            pass

        def read(self):
            return True, np.zeros((16, 16, 3), dtype=np.uint8)

        def release(self):
            self.released = True

    monkeypatch.setattr(cv2, 'VideoCapture', Capture)
    camera = Camera()
    try:
        camera.start()
        camera.start()
        sequence, jpeg = asyncio.run(camera.next_frame())
        assert jpeg.startswith(b'\xff\xd8') and jpeg.endswith(b'\xff\xd9')
        assert asyncio.run(camera.next_frame())[0] >= sequence
        assert asyncio.run(camera.next_frame(sequence))[0] > sequence
        image_sequence, image = asyncio.run(camera.next_image())
        assert image.shape == (16, 16, 3)
        image[:] = 255
        assert not asyncio.run(camera.next_image())[1].any()
        assert asyncio.run(camera.next_image(image_sequence))[0] > image_sequence
        assert len(captures) == 1
    finally:
        camera.close()
    assert captures[0].released


def test_frame_timeout(monkeypatch):
    monkeypatch.setattr(config, 'CAMERA_TIMEOUT', 0.03)
    with pytest.raises(CameraUnavailable, match='초과'):
        asyncio.run(Camera().next_frame())
