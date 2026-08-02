"""Order matching / bundling engine (撮合引擎).

Strategy
--------
1. Group ingested orders by community (小区).
2. A bundle stays *open* for a dynamic time window T; new same-community orders
   join it until either T elapses or the bundle reaches N_max orders.
3. T adapts to order density: sparse arrivals widen the window (wait to
   aggregate more), busy periods or tight SLAs shrink it (seal sooner).
4. Candidate groupings are scored; the best grouping is sealed.

The pure helpers below are unit-tested independently of the database.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlmodel import Session, select

from ..config import Settings, get_settings
from ..models import Bundle, BundleStatus, Order, OrderStatus


def dynamic_window_minutes(arrival_rate_per_min: float, settings: Settings) -> float:
    """Compute the matching window T from recent order arrival rate.

    T = T_base * (target_bundle_size / max(arrival_rate, epsilon)),
    clamped to [T_min, T_max]. Low rate -> larger T; high rate -> smaller T.
    """
    eps = 1e-6
    raw = settings.match_window_base_minutes * (
        settings.match_target_bundle_size / max(arrival_rate_per_min, eps)
    )
    return float(min(max(raw, settings.match_window_min_minutes), settings.match_window_max_minutes))


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


@dataclass
class Candidate:
    order_id: str
    community_id: str
    lat: float
    lng: float
    income_cents: int
    sla_deadline: datetime


def score_group(candidates: List[Candidate], now: datetime, settings: Settings) -> float:
    """Score a proposed group (0..1-ish). Higher is a better bundle."""
    if not candidates:
        return 0.0

    # same-community fraction
    community_ids = {c.community_id for c in candidates}
    same_community = 1.0 if len(community_ids) == 1 else 0.0

    # proximity: 1 when tightly clustered, decaying with mean pairwise distance
    if len(candidates) > 1:
        dists = []
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                dists.append(
                    _haversine_km(
                        candidates[i].lat, candidates[i].lng,
                        candidates[j].lat, candidates[j].lng,
                    )
                )
        mean_dist = sum(dists) / len(dists)
        proximity = 1.0 / (1.0 + mean_dist)  # 1km -> 0.5
    else:
        proximity = 1.0

    # time slack: how much SLA headroom the tightest order has (minutes -> 0..1)
    slack_minutes = min((c.sla_deadline - now).total_seconds() / 60.0 for c in candidates)
    time_slack = 1.0 / (1.0 + math.exp(-(slack_minutes - 10) / 5.0))  # sigmoid around 10 min

    # bundle efficiency: closer to target size is better, capped at max size
    size = len(candidates)
    target = settings.match_target_bundle_size
    efficiency = min(size, settings.match_max_bundle_size) / max(target, 1)
    efficiency = min(efficiency, 1.0)

    return (
        settings.w_same_community * same_community
        + settings.w_proximity * proximity
        + settings.w_time_slack * time_slack
        + settings.w_bundle_efficiency * efficiency
    )


def group_by_community(candidates: List[Candidate]) -> Dict[str, List[Candidate]]:
    groups: Dict[str, List[Candidate]] = {}
    for c in candidates:
        groups.setdefault(c.community_id, []).append(c)
    return groups


# --------------------------------------------------------------------------- #
# Database-integrated service
# --------------------------------------------------------------------------- #

def _recent_arrival_rate(session: Session, minutes: int = 10) -> float:
    since = datetime.utcnow() - timedelta(minutes=minutes)
    rows = session.exec(select(Order).where(Order.created_at >= since)).all()
    return len(rows) / float(minutes)


def run_matching(session: Session, settings: Optional[Settings] = None) -> List[Bundle]:
    """Assign ingested orders into open bundles and seal ready ones.

    Returns the bundles that became `ready` during this run.
    """
    settings = settings or get_settings()
    now = datetime.utcnow()
    window = dynamic_window_minutes(_recent_arrival_rate(session), settings)

    ingested = session.exec(
        select(Order).where(Order.status == OrderStatus.ingested)
    ).all()

    # Index open bundles per community; a bundle only aggregates orders in the
    # same or *adjacent* building and holds at most `cap` orders.
    cap = settings.match_max_bundle_size_adjacent
    adj = settings.building_adjacency
    open_bundles = session.exec(
        select(Bundle).where(Bundle.status == BundleStatus.open)
    ).all()
    by_community: Dict[str, List[Bundle]] = {}
    buildings: Dict[str, List[int]] = {}
    for b in open_bundles:
        by_community.setdefault(b.community_id, []).append(b)
        buildings[b.id] = [
            o.building_no
            for o in session.exec(select(Order).where(Order.bundle_id == b.id)).all()
        ]

    for order in ingested:
        candidates = by_community.get(order.community_id, [])
        bundle = None
        for b in candidates:
            if b.order_count >= cap:
                continue
            bnos = buildings.get(b.id, [])
            if not bnos or any(abs(order.building_no - bn) <= adj for bn in bnos):
                bundle = b
                break
        if bundle is None:
            bundle = Bundle(
                community_id=order.community_id,
                community_name=order.community_name,
                status=BundleStatus.open,
                x_rate=settings.errand_fee_pct_X,
                y_rate=settings.platform_fee_pct_Y,
                window_deadline=now + timedelta(minutes=window),
            )
            session.add(bundle)
            session.flush()  # obtain bundle.id
            by_community.setdefault(order.community_id, []).append(bundle)
            buildings[bundle.id] = []

        order.bundle_id = bundle.id
        order.status = OrderStatus.matched
        bundle.order_count += 1
        bundle.total_income_cents += order.rider_income_cents
        buildings[bundle.id].append(order.building_no)
        session.add(order)
        session.add(bundle)

    # seal bundles that are full or whose window has elapsed
    ready: List[Bundle] = []
    for bundle in session.exec(select(Bundle).where(Bundle.status == BundleStatus.open)).all():
        if bundle.order_count == 0:
            continue
        if bundle.order_count >= settings.match_max_bundle_size_adjacent or now >= bundle.window_deadline:
            bundle.status = BundleStatus.ready
            session.add(bundle)
            ready.append(bundle)

    # freeze a dynamic-pricing snapshot onto each newly-sealed bundle
    if settings.pricing_enabled:
        from . import pricing

        for bundle in ready:
            breakdown = pricing.compute_bundle_quote(session, bundle, settings, now=now)
            pricing.freeze_quote_onto_bundle(session, bundle, breakdown)

    session.commit()
    for b in ready:
        session.refresh(b)
    return ready
