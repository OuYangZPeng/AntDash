"""Seed the database with demo users (a verified Anter, a rider) and ingest
mock orders so the app has data to show on first launch.

Usage:  python seed.py
"""
from __future__ import annotations

from sqlmodel import Session, select

from app.database import engine, init_db
from app.models import Bundle, BundleStatus, Platform, Role, User
from app.services import auth as auth_service
from app.adapters import get_platform_adapters
from app.models import Order
from app.services import pricing as pricing_service
from app.services.matching import run_matching


def ensure_user(session: Session, *, phone: str, role: Role, name: str, id_card: str) -> User:
    user = session.exec(select(User).where(User.phone == phone)).first()
    if user is None:
        user = auth_service.login_phone(session, phone, role=role)
    if not user.verified:
        auth_service.verify_real_name(session, user, name, id_card)
    return user


def main() -> None:
    init_db()
    with Session(engine) as session:
        anter = ensure_user(session, phone="13800000001", role=Role.anter, name="王小蚂", id_card="11010119900307051X")
        rider = ensure_user(session, phone="13900000002", role=Role.rider, name="李骑手", id_card="310101199001011234")
        print(f"anter:  {anter.id}  token={auth_service.create_token(anter)}")
        print(f"rider:  {rider.id}  token={auth_service.create_token(rider)}")

        adapters = get_platform_adapters()
        n = 0
        for adapter in adapters.values():
            for eo in adapter.fetch_orders(limit=8):
                session.add(
                    Order(
                        platform=Platform(eo.platform),
                        external_id=eo.external_id,
                        community_id=eo.community_id,
                        community_name=eo.community_name,
                        address=eo.address,
                        lat=eo.lat,
                        lng=eo.lng,
                        rider_income_cents=eo.rider_income_cents,
                        rider_id=rider.id,
                        sla_deadline=eo.sla_deadline,
                        floor=eo.floor,
                        has_elevator=eo.has_elevator,
                        weight_grams=eo.weight_grams,
                        category=eo.category,
                        building_no=eo.building_no,
                    )
                )
                n += 1
        session.commit()
        ready = run_matching(session)
        # Force-seal any still-open bundles and freeze a price snapshot so demo
        # data has rider_charge populated (needed for the gate-dropoff discount).
        for b in session.exec(select(Bundle).where(Bundle.status == BundleStatus.open)).all():
            if b.order_count:
                b.status = BundleStatus.ready
                session.add(b)
                bd = pricing_service.compute_bundle_quote(session, b)
                pricing_service.freeze_quote_onto_bundle(session, b, bd)
        session.commit()
        sealed = session.exec(select(Bundle).where(Bundle.status == BundleStatus.ready)).all()
        print(f"ingested {n} orders -> {len(sealed)} bundles ready & priced")


if __name__ == "__main__":
    main()
