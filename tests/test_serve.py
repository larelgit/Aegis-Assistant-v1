"""Smoke tests for serve_model.py endpoints (requires model file)."""
import pytest
import sys
from pathlib import Path

# Only run if model exists
MODEL_PATH = Path("data/models/aegis_lgbm_v3.pkl")
pytestmark = pytest.mark.skipif(
    not MODEL_PATH.exists(),
    reason=f"Model not found at {MODEL_PATH}"
)


@pytest.fixture(scope="module")
def client():
    from serve_model import app, load_model
    import serve_model
    serve_model.MODEL, serve_model.ENCODER, serve_model.FEATURE_LIST, serve_model.CLASS_LABELS = \
        load_model(MODEL_PATH)

    from fastapi.testclient import TestClient
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["model_loaded"] is True


def test_meta(client):
    r = client.get("/meta")
    assert r.status_code == 200
    data = r.json()
    assert len(data["features"]) >= 4
    assert len(data["classes"]) >= 2


def test_predict_defaults(client):
    r = client.post("/predict", json={})
    assert r.status_code == 200
    data = r.json()
    assert "action" in data
    assert "confidence" in data
    assert 0 <= data["confidence"] <= 1


def test_predict_with_values(client):
    r = client.post("/predict", json={
        "gold_adv": 5000,
        "our_alive": 5,
        "enemy_alive": 3,
        "enemy_dead_tot": 2,
    })
    assert r.status_code == 200
    assert r.json()["action"] in [
        "FARM", "STACK", "GANK", "PUSH", "DEFEND",
        "TEAMFIGHT", "TAKE_ROSHAN", "CONTEST_ROSHAN", "SIEGE",
    ]
