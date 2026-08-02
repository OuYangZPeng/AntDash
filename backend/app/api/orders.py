"""Order ingestion & bundle listing endpoints."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from ..adapters import get_platform_adapters
from ..config import get_settings
from ..database import get_session
from ..models import Bundle, BundleStatus, Order, Platform, Role, User
from ..schemas import BundleOut, OrderOut
from ..services.matching import run_matching
from ..services.notifications import get_hub
from .deps import get_current_user

router = APIRouter(tags=["orders"])


def _advance_and_notify(session: Session, ready: List[Bundle]) -> int:
    """Optionally advance sealed bundles to `at_gate` (so they're offerable in
    the hall), then push them to online Anters within notify_radius_km.
    """
    from ..services import dispatch as dispatch_service

    settings = get_settings()
    if settings.auto_gate_on_match:
        for b in ready:
            try:
                dispatch_service.mark_bundle_at_gate(session, b, settings)
            except dispatch_service.DispatchError:
                pass
    return _notify_nearby_anters(session, ready)


def _notify_nearby_anters(session: Session, ready: List[Bundle]) -> int:
    """Push newly-formed bundles to online Anters within notify_radius_km."""
    settings = get_settings()
    hub = get_hub()
    total = 0
    for b in ready:
        orders = session.exec(select(Order).where(Order.bundle_id == b.id)).all()
        if not orders:
            continue
        clat = sum(o.lat for o in orders) / len(orders)
        clng = sum(o.lng for o in orders) / len(orders)
        event = {
            "type": "new_bundle",
            "bundle_id": b.id,
            "community_name": b.community_name,
            "order_count": b.order_count,
            "quoted_price_cents": b.quoted_price_cents,
            "anter_net_cents": b.anter_net_cents,
        }
        total += hub.publish_new_bundle(event, clat, clng, settings.notify_radius_km)
    return total


def _order_out(o: Order, viewer_role: Optional[Role] = None) -> OrderOut:
    # Rider sees "本单扣款"; anter/admin do not need per-order rider charge.
    rider_charge = o.rider_charge_cents if viewer_role == Role.rider else None
    return OrderOut(
        id=o.id,
        platform=o.platform.value if hasattr(o.platform, "value") else o.platform,
        external_id=o.external_id,
        community_name=o.community_name,
        address=o.address,
        rider_income_cents=o.rider_income_cents,
        status=o.status.value if hasattr(o.status, "value") else o.status,
        sla_deadline=o.sla_deadline,
        floor=o.floor,
        has_elevator=o.has_elevator,
        category=o.category,
        proof_uploaded=o.proof_uploaded,
        gate_dropoff_at=o.gate_dropoff_at,
        gate_discount_cents=o.gate_discount_cents,
        rider_charge_cents=rider_charge,
    )


def bundle_out(session: Session, b: Bundle, viewer_role: Optional[Role] = None) -> BundleOut:
    """Serialize a bundle with role-scoped pricing visibility.

    - rider: sees only the aggregate/per-order deduction (rider_charge); anter
      economics and surge details are hidden.
    - anter / admin (None): full dynamic-pricing breakdown.
    - C-end customers have no bundle endpoint, so price stays invisible to them.
    """
    orders = session.exec(select(Order).where(Order.bundle_id == b.id)).all()
    is_rider = viewer_role == Role.rider

    out = BundleOut(
        id=b.id,
        community_name=b.community_name,
        status=b.status.value if hasattr(b.status, "value") else b.status,
        anter_id=b.anter_id,
        order_count=b.order_count,
        total_income_cents=b.total_income_cents,
        errand_fee_cents=0 if is_rider else b.errand_fee_cents,
        platform_fee_cents=0 if is_rider else b.platform_fee_cents,
        anter_net_cents=0 if is_rider else b.anter_net_cents,
        x_rate=b.x_rate,
        y_rate=b.y_rate,
        window_deadline=b.window_deadline,
        delivery_deadline=b.delivery_deadline,
        orders=[_order_out(o, viewer_role) for o in orders],
        rider_charge_cents=b.rider_charge_cents,
        weather_condition=b.weather_condition,
        urgency_fee_cents=b.urgency_fee_cents,
        escalation_stage=b.escalation_stage,
        rescue=b.rescue,
    )
    if not is_rider:
        out.base_price_cents = b.base_price_cents
        out.quoted_price_cents = b.quoted_price_cents
        out.subsidy_cents = b.subsidy_cents
        out.surge_multiplier = b.surge_multiplier
        out.time_multiplier = b.time_multiplier
        out.weather_multiplier = b.weather_multiplier
        out.pricing_breakdown = b.pricing_breakdown or None
    return out


@router.post("/orders/ingest")
def ingest_orders(limit: int = Query(20, ge=1, le=100), session: Session = Depends(get_session)):
    """Pull fresh orders from every platform adapter, then run matching."""
    adapters = get_platform_adapters()
    ingested = 0
    for key, adapter in adapters.items():
        for eo in adapter.fetch_orders(limit=limit):
            order = Order(
                platform=Platform(eo.platform),
                external_id=eo.external_id,
                community_id=eo.community_id,
                community_name=eo.community_name,
                address=eo.address,
                lat=eo.lat,
                lng=eo.lng,
                rider_income_cents=eo.rider_income_cents,
                sla_deadline=eo.sla_deadline,
                floor=eo.floor,
                has_elevator=eo.has_elevator,
                weight_grams=eo.weight_grams,
                category=eo.category,
                building_no=eo.building_no,
            )
            session.add(order)
            ingested += 1
    session.commit()
    ready = run_matching(session)
    notified = _advance_and_notify(session, ready)
    return {"ingested": ingested, "bundles_ready": len(ready), "anters_notified": notified}


@router.post("/orders/match")
def trigger_match(session: Session = Depends(get_session)):
    ready = run_matching(session)
    notified = _advance_and_notify(session, ready)
    return {
        "bundles_ready": len(ready),
        "ready_ids": [b.id for b in ready],
        "anters_notified": notified,
    }


def _aggregation_stats(session: Session) -> dict:
    """Snapshot of how well orders are aggregating into bundles."""
    from collections import Counter

    bundles = session.exec(select(Bundle)).all()
    orders = session.exec(select(Order)).all()
    sizes = [b.order_count for b in bundles if b.order_count > 0]
    orders_in_multi = sum(s for s in sizes if s >= 2)
    total_matched = sum(sizes)
    by_status = Counter(
        (b.status.value if hasattr(b.status, "value") else b.status) for b in bundles
    )
    per_community = Counter(b.community_name for b in bundles if b.order_count > 0)
    return {
        "total_orders": len(orders),
        "total_bundles": len([b for b in bundles if b.order_count > 0]),
        "bundles_by_status": dict(by_status),
        "avg_bundle_size": round(total_matched / len(sizes), 2) if sizes else 0,
        "max_bundle_size": max(sizes) if sizes else 0,
        # share of matched orders that actually got aggregated (bundle size >= 2)
        "aggregated_order_rate": round(orders_in_multi / total_matched, 3) if total_matched else 0,
        "orders_per_community": dict(per_community),
    }


@router.post("/orders/simulate")
def simulate_orders(
    count: int = Query(20, ge=1, le=500),
    communities: int = Query(5, ge=1, le=5),
    seed: Optional[int] = Query(None),
    session: Session = Depends(get_session),
):
    """Testing tool: generate `count` random orders spread across `communities`
    distinct communities (fewer => denser aggregation), match, and report stats.
    """
    from ..adapters.platform_mock import COMMUNITIES, generate_external_orders

    community_ids = [c[0] for c in COMMUNITIES[:communities]]
    ext = generate_external_orders(count, community_ids=community_ids, seed=seed)
    for eo in ext:
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
                sla_deadline=eo.sla_deadline,
                floor=eo.floor,
                has_elevator=eo.has_elevator,
                weight_grams=eo.weight_grams,
                category=eo.category,
                building_no=eo.building_no,
            )
        )
    session.commit()
    ready = run_matching(session)
    notified = _advance_and_notify(session, ready)
    return {
        "generated": count,
        "communities_used": communities,
        "bundles_ready_this_round": len(ready),
        "anters_notified": notified,
        "stats": _aggregation_stats(session),
    }


@router.post("/orders/generate-for-me")
def generate_for_me(
    count: int = Query(6, ge=1, le=60),
    communities: int = Query(1, ge=1, le=5),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Test helper: generate `count` orders assigned to the CURRENT rider, match
    them into bundles, seal/price/advance to the hall, and push nearby.

    Lets a logged-in rider instantly populate their 我的配送 + the接单大厅.
    """
    from ..adapters.platform_mock import COMMUNITIES, generate_external_orders

    community_ids = [c[0] for c in COMMUNITIES[:communities]]
    ext = generate_external_orders(count, community_ids=community_ids)
    for eo in ext:
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
                rider_id=user.id,
                sla_deadline=eo.sla_deadline,
                floor=eo.floor,
                has_elevator=eo.has_elevator,
                weight_grams=eo.weight_grams,
                category=eo.category,
                building_no=eo.building_no,
            )
        )
    session.commit()
    ready = run_matching(session)
    notified = _advance_and_notify(session, ready)
    return {
        "generated": count,
        "assigned_to": user.id,
        "bundles_ready": len(ready),
        "anters_notified": notified,
    }


@router.get("/orders/mine")
def my_orders(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    """Rider view: their first-leg orders grouped by the bundle they belong to,
    so a 外卖骑手 can see which aggregate each order joined and hand it off.
    """
    orders = session.exec(
        select(Order).where(Order.rider_id == user.id).order_by(Order.created_at.desc())
    ).all()
    groups: dict = {}
    for o in orders:
        key = o.bundle_id or f"_unbundled_{o.id}"
        if key not in groups:
            b = session.get(Bundle, o.bundle_id) if o.bundle_id else None
            groups[key] = {
                "bundle_id": o.bundle_id,
                "community_name": o.community_name,
                "bundle_status": (b.status.value if b and hasattr(b.status, "value") else (b.status if b else "open")),
                "order_count": (b.order_count if b else 1),
                "gate_deadline": None,
                "my_orders": [],
            }
        groups[key]["my_orders"].append(_order_out(o, Role.rider))
    # earliest SLA within each group -> a gate hand-off countdown target
    for g in groups.values():
        slas = [o.sla_deadline for o in g["my_orders"]]
        g["gate_deadline"] = min(slas).isoformat() if slas else None
    return list(groups.values())


@router.get("/bundles", response_model=List[BundleOut])
def list_bundles(
    status: Optional[BundleStatus] = None,
    session: Session = Depends(get_session),
):
    stmt = select(Bundle)
    if status is not None:
        stmt = stmt.where(Bundle.status == status)
    bundles = session.exec(stmt.order_by(Bundle.created_at.desc())).all()
    return [bundle_out(session, b) for b in bundles]


@router.get("/bundles/{bundle_id}", response_model=BundleOut)
def get_bundle(bundle_id: str, session: Session = Depends(get_session)):
    b = session.get(Bundle, bundle_id)
    if not b:
        from fastapi import HTTPException

        raise HTTPException(404, "bundle not found")
    return bundle_out(session, b)
