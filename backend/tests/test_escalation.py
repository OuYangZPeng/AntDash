"""Escalation / rescue: pure helpers + a DB-backed rescue-settlement flow."""
import os
import tempfile
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel, Session, select

from app.config import get_settings
from app.services.escalation import (
    escalation_stage,
    is_rescue,
    push_radius_km,
    urgency_fee_cents,
)

S = get_settings()


# --- pure helpers ---
def test_escalation_stage_thresholds():
    assert escalation_stage(60, S) == 0
    assert escalation_stage(S.urgency_start_minutes - 0.1, S) == 1   # <20min
    assert escalation_stage(S.rescue_threshold_minutes - 0.1, S) == 2  # <15min -> rescue
    assert escalation_stage(3, S) == 3
    assert escalation_stage(-1, S) == 4


def test_is_rescue():
    assert not is_rescue(20, S)
    assert is_rescue(15, S)
    assert is_rescue(5, S)


def test_urgency_fee_ramps_and_caps():
    assert urgency_fee_cents(1000, 60, S) == 0                 # plenty of time
    mid = urgency_fee_cents(1000, S.urgency_start_minutes / 2, S)
    assert 0 < mid < int(1000 * S.urgency_fee_max_ratio)
    # at/after timeout -> capped at base × max_ratio
    assert urgency_fee_cents(1000, 0, S) == int(round(1000 * S.urgency_fee_max_ratio))
    assert urgency_fee_cents(1000, -5, S) == int(round(1000 * S.urgency_fee_max_ratio))


def test_push_radius_grows_with_stage():
    assert push_radius_km(1, S) == S.notify_radius_km
    assert push_radius_km(2, S) > push_radius_km(1, S)
    assert push_radius_km(9, S) <= S.escalation_radius_max_km


# --- DB-backed rescue settlement ---
@pytest.fixture()
def client(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("ANTDASH_DATABASE_URL", f"sqlite:///{os.path.join(tmp, 'esc.db')}")
    monkeypatch.setenv("ANTDASH_MEDIA_DIR", os.path.join(tmp, "media"))
    import app.config as config

    config.get_settings.cache_clear()
    import importlib
    import app.database as database

    importlib.reload(database)
    import app.main as main

    importlib.reload(main)
    SQLModel.metadata.create_all(database.engine)
    with TestClient(main.app) as c:
        yield c, database


def _auth(c, phone, role="anter"):
    tok = c.post("/auth/login/phone", json={"phone": phone, "otp": "1234", "role": role}).json()["token"]
    c.post("/auth/real-name", headers={"Authorization": f"Bearer {tok}"},
           json={"name": "王小蚂", "id_card": "11010119900307051X"})
    return tok


def test_rider_rescue_earns_bonus_and_reputation(client):
    c, database = client
    # a 外卖骑手 acting as rescuer (role=rider), and generate a bundle
    tok = _auth(c, "13700000009", role="rider")
    me0 = c.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert c.post("/orders/simulate?count=40&communities=1&seed=2").status_code == 200

    from app.models import Bundle, BundleStatus, Order
    from app.services.escalation import sweep_once

    # push the soonest order into the rescue window, then sweep
    with Session(database.engine) as s:
        bundle = s.exec(select(Bundle).where(Bundle.status == BundleStatus.at_gate)).first()
        assert bundle is not None
        for o in s.exec(select(Order).where(Order.bundle_id == bundle.id)).all():
            o.sla_deadline = datetime.utcnow() + timedelta(minutes=10)  # <15min
            s.add(o)
        s.commit()
        sweep_once(s, get_settings())
        s.refresh(bundle)
        assert bundle.rescue is True
        assert bundle.urgency_fee_cents > 0
        bid = bundle.id

    settings = get_settings()
    hdr = {"Authorization": f"Bearer {tok}"}
    assert c.post(f"/dispatch/bundles/{bid}/accept", headers=hdr).status_code == 200
    detail = c.get(f"/bundles/{bid}").json()
    for o in detail["orders"]:
        c.post(f"/proof/orders/{o['id']}/delivery", headers=hdr,
               files={"file": ("p.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")})
    settled = c.post(f"/dispatch/bundles/{bid}/deliver", headers=hdr).json()
    assert settled["status"] == "settled"
    assert settled["rescue"] is True

    me1 = c.get("/auth/me", headers=hdr).json()
    # rescuer got the bonus (balance >= bonus) and a rescue count + reputation bump
    assert me1["balance_cents"] >= settings.rider_rescue_bonus_cents
    assert me1["rescue_count"] == me0["rescue_count"] + 1
    assert me1["reputation_score"] > me0["reputation_score"]


def test_rider_gate_dropoff_earliness_discount(client):
    c, database = client
    rtok = _auth(c, "13900000002", role="rider")
    hdr = {"Authorization": f"Bearer {rtok}"}
    rider_id = c.get("/auth/me", headers=hdr).json()["id"]

    assert c.post("/orders/simulate?count=40&communities=1&seed=4").status_code == 200

    from app.models import Bundle, BundleStatus, Order

    # attribute the bundle's orders to this rider with generous SLA slack
    with Session(database.engine) as s:
        bundle = s.exec(select(Bundle).where(Bundle.status == BundleStatus.at_gate)).first()
        assert bundle is not None
        bid = bundle.id
        oids = []
        for o in s.exec(select(Order).where(Order.bundle_id == bid)).all():
            o.rider_id = rider_id
            o.sla_deadline = datetime.utcnow() + timedelta(minutes=45)  # lots of slack
            s.add(o)
            oids.append((o.id, o.rider_charge_cents))
        s.commit()

    # rider sees their orders grouped under the bundle
    mine = c.get("/orders/mine", headers=hdr).json()
    assert any(g["bundle_id"] == bid and len(g["my_orders"]) == len(oids) for g in mine)

    # drop the first order at the gate early -> earns a discount
    oid, charge_before = oids[0]
    r = c.post(f"/proof/orders/{oid}/gate", headers=hdr,
               files={"file": ("g.jpg", b"\xff\xd8\xff\xd9", "image/jpeg")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["discount_cents"] > 0

    with Session(database.engine) as s:
        o = s.get(Order, oid)
        assert o.gate_dropoff_at is not None
        assert o.gate_discount_cents == body["discount_cents"]
        assert o.rider_charge_cents == charge_before - body["discount_cents"]
