"""Geo-locate + 1km WebSocket notification tests."""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

from app.services.notifications import haversine_km


@pytest.fixture()
def client(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("ANTDASH_DATABASE_URL", f"sqlite:///{os.path.join(tmp, 'notif.db')}")
    monkeypatch.setenv("ANTDASH_MEDIA_DIR", os.path.join(tmp, "media"))
    import app.config as config

    config.get_settings.cache_clear()
    import importlib
    import app.database as database

    importlib.reload(database)
    import app.main as main

    importlib.reload(main)
    SQLModel.metadata.create_all(database.engine)
    # ensure the hub starts empty for this app instance
    from app.services.notifications import get_hub

    get_hub()._clients.clear()
    with TestClient(main.app) as c:
        yield c


def _auth(c, phone):
    r = c.post("/auth/login/phone", json={"phone": phone, "otp": "1234", "role": "anter"})
    tok = r.json()["token"]
    c.post("/auth/real-name", headers={"Authorization": f"Bearer {tok}"},
           json={"name": "王小蚂", "id_card": "11010119900307051X"})
    return tok


def test_haversine_km_sanity():
    # ~1.1km apart in latitude (0.01 deg ~ 1.11km)
    d = haversine_km(31.2304, 121.4737, 31.2404, 121.4737)
    assert 1.0 < d < 1.3
    assert haversine_km(31.23, 121.47, 31.23, 121.47) == 0.0


def test_geo_locate_is_ip_derived_and_persisted(client):
    tok = _auth(client, "13800000001")
    r = client.get("/geo/locate", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["city"]  # non-empty (fallback 上海市 for loopback)
    assert body["editable"] is False  # non-tamperable
    assert "lat" in body and "lng" in body


def test_nearby_anter_gets_new_bundle_push(client):
    tok = _auth(client, "13800000001")
    # resolve + persist location (near the 万科 demo community by default)
    client.get("/geo/locate", headers={"Authorization": f"Bearer {tok}"})

    with client.websocket_connect(f"/ws/notifications?token={tok}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "connected"
        # generate enough orders in one community so a building cluster seals nearby
        resp = client.post("/orders/simulate?count=40&communities=1&seed=1")
        assert resp.status_code == 200, resp.text
        assert resp.json()["bundles_ready_this_round"] >= 1

        evt = ws.receive_json()
        assert evt["type"] == "new_bundle"
        assert evt["order_count"] >= 1
        assert evt["distance_km"] <= 1.0
