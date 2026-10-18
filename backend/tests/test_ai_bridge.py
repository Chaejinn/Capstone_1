import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import ai_client, config, models
from app.database import Base, get_db
from app.routers import ai_bridge, events


@pytest.fixture
def client(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        db.add(models.Site(id='test', name='Test', meta='', status='운영중', enabled=True))
        db.add(models.GlobalSettings(id=1, thresh_conf=0.9, thresh_frames=2))
        db.commit()
    monkeypatch.setattr(config, 'CAMERA_SITE_ID', 'test')
    monkeypatch.setattr(config, 'IS_VERCEL', False)
    events._consecutive_drowning.clear()
    app = FastAPI()
    app.include_router(ai_bridge.router)

    def database():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = database
    with TestClient(app) as test_client:
        yield test_client, sessions
    events._consecutive_drowning.clear()
    engine.dispose()


def upload(client, path='/frame', body=b'image'):
    return client.post('/api/ai' + path, files={'image': ('test.jpg', body, 'image/jpeg')}, data={'frame_id': '7'})


def test_frame_accumulation_dispatch_and_no_duplicate(client, monkeypatch):
    test_client, sessions = client

    async def detect(body, filename, content_type, frame_id):
        assert (body, filename, content_type, frame_id) == (b'image', 'test.jpg', 'image/jpeg', 7)
        return {'detections': [{'track_id': 42, 'label': 'drowning', 'confidence': 0.97, 'bbox': [10, 20, 30, 40]}]}

    monkeypatch.setattr(ai_client, 'detect', detect)
    first = upload(test_client)
    assert first.status_code == 200
    assert first.json()['dispatched'] is False
    assert first.json()['judgement']['img_x'] == 20
    second = upload(test_client)
    assert second.status_code == 200
    assert second.json()['dispatched'] is True
    assert second.json()['event_id'] is not None
    assert upload(test_client).json()['dispatched'] is False
    with sessions() as db:
        event = db.query(models.Event).one()
        assert event.track_id == '42'
        assert event.site_id == 'test'
        assert event.real_x_m is None and event.real_y_m is None


def test_mapping_failure_defers_without_event(client, monkeypatch):
    test_client, sessions = client

    async def detect(*args):
        return {'unexpected': 'response'}

    monkeypatch.setattr(ai_client, 'detect', detect)
    response = upload(test_client)
    assert response.status_code == 422
    assert response.json()['detail']['raw'] == {'unexpected': 'response'}
    with sessions() as db:
        assert db.query(models.Event).count() == 0


def test_upload_validation_and_upstream_failure(client, monkeypatch):
    test_client, _ = client

    async def detect(*args):
        raise ai_client.AIClientError('upstream unavailable')

    monkeypatch.setattr(ai_client, 'detect', detect)
    assert upload(test_client, body=b'').status_code == 400
    assert upload(test_client, body=b'x' * (5 * 1024 * 1024 + 1)).status_code == 413
    assert upload(test_client, '/detect-raw').status_code == 502


def test_ai_client_multipart_auth_and_response(monkeypatch):
    import asyncio
    import httpx

    monkeypatch.setenv('DG_AI_URL', 'https://ai.example/')
    monkeypatch.setenv('DG_AI_KEY', 'test-key')
    original_client = httpx.AsyncClient

    def handle(request):
        assert str(request.url) == 'https://ai.example/detect'
        assert request.headers['authorization'] == 'Bearer test-key'
        assert b'name="image"' in request.content
        assert b'name="frame_id"' in request.content
        return httpx.Response(200, json={'label': 'drowning', 'score': 0.95})

    monkeypatch.setattr(ai_client.httpx, 'AsyncClient', lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs))
    assert asyncio.run(ai_client.detect(b'image', 'frame.jpg', 'image/jpeg', 7))['score'] == 0.95


@pytest.mark.parametrize('status,payload,message', [
    (401, {'error': 'unauthorized'}, '인증 실패'),
    (500, {'error': 'unavailable'}, 'AI 서버 오류 500'),
    (200, None, 'JSON이 아닙니다'),
])
def test_ai_client_upstream_errors(monkeypatch, status, payload, message):
    import asyncio
    import httpx

    monkeypatch.setenv('DG_AI_URL', 'https://ai.example')
    monkeypatch.setenv('DG_AI_KEY', 'test-key')
    original_client = httpx.AsyncClient

    def handle(request):
        return httpx.Response(status, json=payload) if payload else httpx.Response(status, text='not json')

    monkeypatch.setattr(ai_client.httpx, 'AsyncClient', lambda **kwargs: original_client(transport=httpx.MockTransport(handle), **kwargs))
    with pytest.raises(ai_client.AIClientError, match=message):
        asyncio.run(ai_client.detect(b'image', 'frame.jpg', 'image/jpeg'))


def test_health_missing_configuration(client, monkeypatch):
    test_client, _ = client
    monkeypatch.delenv('DG_AI_URL', raising=False)
    monkeypatch.delenv('DG_AI_KEY', raising=False)
    response = test_client.post('/api/ai/health')
    assert response.status_code == 502
    assert '환경변수' in response.json()['detail']
