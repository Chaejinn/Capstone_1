import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import app
from backend.app import main
from backend.app import config, models
from backend.app.database import Base, get_db


@pytest.fixture
def client(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    sessions = sessionmaker(bind=engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessions)

    def db():
        with sessions() as session:
            yield session

    main.app.dependency_overrides[get_db] = db
    with TestClient(app) as client:
        yield client
    main.app.dependency_overrides.clear()
    engine.dispose()


def auth(client, username="capstone1", password="20262026"):
    response = client.post("/api/auth/login", data={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_api_mount_and_health(client):
    assert client.get("/", follow_redirects=False).headers["location"] == "/index.html"
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/index.html").status_code == 200
    assert client.get("/js/bootstrap.js").status_code == 200
    assert client.get("/api/sites").status_code == 401


def test_signup_permissions_and_account_management(client):
    response = client.post("/api/auth/signup", json={"username": "operator01", "password": "test-password", "name": "운영자"})
    assert response.status_code == 200
    viewer = {"Authorization": "Bearer " + response.json()["access_token"]}
    assert client.get("/api/sites", headers=viewer).status_code == 200
    assert client.get("/api/users", headers=viewer).status_code == 403
    assert client.put("/api/settings", headers=viewer, json={"thresh_conf": .91, "thresh_frames": 16}).status_code == 403
    admin = auth(client)
    users = client.get("/api/users", headers=admin).json()
    user = next(row for row in users if row["username"] == "operator01")
    assert "password_hash" not in user
    assert client.patch(f'/api/users/{user["id"]}/active', headers=admin, json={"active": False}).status_code == 200
    assert client.get("/api/sites", headers=viewer).status_code == 401
    assert client.post("/api/auth/login", data={"username": "operator01", "password": "test-password"}).status_code == 403


def test_persistent_settings_roi_and_reset(client):
    admin = auth(client)
    assert client.put("/api/settings", headers=admin, json={"thresh_conf": .93, "thresh_frames": 18}).status_code == 200
    assert client.get("/api/settings", headers=admin).json()["thresh_conf"] == .93
    roi = {"points": [{"x": 10, "y": 10}, {"x": 80, "y": 10}, {"x": 50, "y": 80}]}
    assert client.put("/api/sites/chunjeon/roi", headers=admin, json=roi).status_code == 200
    assert client.get("/api/sites/chunjeon/roi", headers=admin).json() == roi
    assert client.post("/api/maintenance/reset").status_code == 401
    assert client.post("/api/maintenance/reset", headers=admin).status_code == 200
    assert client.get("/api/settings", headers=admin).json()["thresh_conf"] == .9
    assert client.get("/api/sites/chunjeon/roi", headers=admin).json() == {"points": []}


def test_vlm_requires_admin(client):
    body = {"request_id": "test", "track_id": "test", "site_id": "chunjeon", "classification": "drowning", "confidence": .95}
    assert client.post("/api/vlm/classification", json=body).status_code == 401


def test_seed_preserves_existing_admin_after_config_change(client, monkeypatch):
    monkeypatch.setattr(config, "ADMIN_ID", "Guardian")
    monkeypatch.setattr(config, "ADMIN_PW", "new-test-password")
    main.seed_db()
    with main.SessionLocal() as db:
        admins = db.query(models.User).filter(models.User.role == "admin").all()
        assert len(admins) == 1
        assert admins[0].username == "capstone1"
