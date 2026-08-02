"""End-to-end flow through the API using FastAPI's TestClient.

Covers: login -> real-name -> ingest+match -> gate drop -> offer -> accept
-> deliver -> settlement ledger & reputation.
"""
import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel


@pytest.fixture()
def client(monkeypatch):
    # isolated sqlite file per test run
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "e2e.db")
    monkeypatch.setenv("ANTDASH_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTDASH_MEDIA_DIR", os.path.join(tmp, "media"))

    # reset cached settings & engine so env vars take effect
    import app.config as config

    config.get_settings.cache_clear()
    import importlib
    import app.database as database

    importlib.reload(database)
    import app.main as main

    importlib.reload(main)
    SQLModel.metadata.create_all(database.engine)
    with TestClient(main.app) as c:
        yield c


def _auth_header(token: str):
    return {"Authorization": f"Bearer {token}"}


def test_full_flow(client):
    # rider login
    r = client.post("/auth/login/phone", json={"phone": "13900000002", "otp": "1234", "role": "rider"})
    assert r.status_code == 200, r.text
    rider = r.json()

    # anter login + real name
    r = client.post("/auth/login/phone", json={"phone": "13800000001", "otp": "1234", "role": "anter"})
    anter = r.json()
    r = client.post("/auth/real-name", headers=_auth_header(anter["token"]),
                    json={"name": "王小蚂", "id_card": "11010119900307051X"})
    assert r.status_code == 200, r.text
    assert r.json()["verified"] is True

    # ingest & match
    r = client.post("/orders/ingest?limit=10")
    assert r.status_code == 200, r.text

    # force-close windows by matching again is not enough (window not elapsed);
    # grab any ready bundle, else mark an open one at gate directly is disallowed,
    # so we drive a bundle to gate through the ready ones.
    bundles = client.get("/bundles").json()
    assert bundles, "expected at least one bundle"

    # Bundles auto-advance to at_gate (offerable) on match; if none yet, seal more.
    offerable = [b for b in bundles if b["status"] in ("ready", "at_gate")]
    if not offerable:
        for _ in range(6):
            client.post("/orders/ingest?limit=10")
        offerable = [b for b in client.get("/bundles").json()
                     if b["status"] in ("ready", "at_gate")]
    assert offerable, "expected an offerable bundle after ingesting enough orders"
    bundle = offerable[0]

    # rider drops at gate (idempotent if already advanced)
    r = client.post(f"/dispatch/bundles/{bundle['id']}/at-gate")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "at_gate"

    # anter sees offer & accepts
    offers = client.get("/dispatch/offers", headers=_auth_header(anter["token"])).json()
    assert any(b["id"] == bundle["id"] for b in offers)
    r = client.post(f"/dispatch/bundles/{bundle['id']}/accept", headers=_auth_header(anter["token"]))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"

    # each sub-order must be photographed individually before settlement
    detail = client.get(f"/bundles/{bundle['id']}").json()
    for o in detail["orders"]:
        rp = client.post(
            f"/proof/orders/{o['id']}/delivery",
            headers=_auth_header(anter["token"]),
            files={"file": ("p.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")},
        )
        assert rp.status_code == 200, rp.text

    # anter delivers -> settled
    r = client.post(f"/dispatch/bundles/{bundle['id']}/deliver", headers=_auth_header(anter["token"]))
    assert r.status_code == 200, r.text
    settled = r.json()
    assert settled["status"] == "settled"
    # dynamic pricing: errand fee == frozen quoted price P (not total×X%)
    assert settled["quoted_price_cents"] > 0
    assert settled["errand_fee_cents"] == settled["quoted_price_cents"]
    assert settled["platform_fee_cents"] == round(settled["errand_fee_cents"] * settled["y_rate"] / 100)
    assert settled["anter_net_cents"] == settled["errand_fee_cents"] - settled["platform_fee_cents"]
    # rider charge + platform subsidy fund the whole errand fee
    assert settled["rider_charge_cents"] + settled["subsidy_cents"] == settled["errand_fee_cents"]

    # anter balance increased & reputation rewarded
    me = client.get("/auth/me", headers=_auth_header(anter["token"])).json()
    assert me["balance_cents"] == settled["anter_net_cents"]
    assert me["reputation_score"] > 60.0

    # ledger recorded for the anter
    ledger = client.get("/wallet/ledger", headers=_auth_header(anter["token"])).json()
    assert any(e["type"] == "anter_credit" for e in ledger)
