"""Dynamic pricing engine for aggregated bundles (聚合单动态定价).

Meituan-style structure: an *additive*, effort-based base package per order,
scaled by aggregation size, then multiplied by *volatile* factors (time-of-day,
weather, per-community supply-demand surge), clamped by a floor & cap.

Funding split (C-end never sees price):
    P            = clamp(P_base * M_time * M_weather * M_surge, floor, cap)   # errand fee
    rider_charge = min(P_base * M_time^rider, P)     # rider pays deterministic effort (capped peak)
    subsidy      = P - rider_charge                  # platform funds surge/weather premium
    platform_fee = P * Y%
    anter_net    = P - platform_fee

The pure helpers below are DB-free and unit-tested; the DB-integrated
`compute_bundle_quote` gathers inputs (map distance, weather, surge) and freezes
a snapshot onto the bundle at seal time.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlmodel import Session, select

from ..config import Settings, get_settings
from ..models import Bundle, BundleStatus, Order, Role, User


# --------------------------------------------------------------------------- #
# Pure inputs / outputs
# --------------------------------------------------------------------------- #
@dataclass
class OrderPriceInput:
    order_id: str
    distance_m: float          # centroid/gate -> door walking distance
    floor: int
    has_elevator: bool
    weight_grams: int
    category: str
    sla_minutes: float         # remaining SLA headroom
    rider_income_cents: int


@dataclass
class PriceBreakdown:
    base_price_cents: int              # P_base (after aggregation discount)
    sum_base_cents: int                # Σ 子单基础包(未打折)
    aggregation_discount_ratio: float
    pool_contribution_cents: int       # 投入应急奖金池的 5%
    time_multiplier: float
    weather_multiplier: float
    surge_multiplier: float
    full_multiplier: float
    weather_condition: str
    demand: int
    supply: int
    surge_scope: str
    floor_cents: int
    cap_cents: int
    quoted_price_cents: int            # P == errand fee
    rider_charge_cents: int
    subsidy_cents: int
    platform_fee_cents: int
    anter_net_cents: int
    order_base_cents: Dict[str, int] = field(default_factory=dict)
    order_rider_charge_cents: Dict[str, int] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "base_price_cents": self.base_price_cents,
                "sum_base_cents": self.sum_base_cents,
                "aggregation_discount_ratio": round(self.aggregation_discount_ratio, 4),
                "pool_contribution_cents": self.pool_contribution_cents,
                "time_multiplier": round(self.time_multiplier, 4),
                "weather_multiplier": round(self.weather_multiplier, 4),
                "surge_multiplier": round(self.surge_multiplier, 4),
                "full_multiplier": round(self.full_multiplier, 4),
                "weather_condition": self.weather_condition,
                "demand": self.demand,
                "supply": self.supply,
                "surge_scope": self.surge_scope,
                "floor_cents": self.floor_cents,
                "cap_cents": self.cap_cents,
                "quoted_price_cents": self.quoted_price_cents,
                "rider_charge_cents": self.rider_charge_cents,
                "subsidy_cents": self.subsidy_cents,
                "platform_fee_cents": self.platform_fee_cents,
                "anter_net_cents": self.anter_net_cents,
                "order_base_cents": self.order_base_cents,
                "order_rider_charge_cents": self.order_rider_charge_cents,
            },
            ensure_ascii=False,
        )


# --------------------------------------------------------------------------- #
# Pure component functions
# --------------------------------------------------------------------------- #
def order_base_package(o: OrderPriceInput, settings: Settings) -> int:
    """Effort-based, deterministic per-order base fee in cents."""
    fee = float(settings.price_base_start_cents)

    extra_m = max(0.0, o.distance_m - settings.price_free_distance_m)
    fee += round(extra_m / 100.0 * settings.price_per_100m_cents)

    if not o.has_elevator and o.floor > 1:
        floors = min(o.floor - 1, settings.price_walkup_max_floors)
        fee += floors * settings.price_per_floor_cents

    over_g = max(0, o.weight_grams - settings.price_weight_free_grams)
    fee += round(over_g / 1000.0 * settings.price_per_kg_over_cents)

    if o.category == "fresh":
        fee += settings.price_surcharge_fresh_cents
    elif o.category == "fragile":
        fee += settings.price_surcharge_fragile_cents

    if o.sla_minutes <= settings.price_sla_tight_minutes:
        fee += settings.price_sla_tight_cents

    return int(fee)


def aggregate_base(sum_base_cents: int, n: int, settings: Settings) -> tuple[int, int]:
    """Non-linear aggregation price: a real bundle (n>=2) costs a flat
    `aggregation_discount_ratio` (default 5%) less than the sum of its sub-order
    packages. Returns (P_base, pool_contribution) where the discount funds the
    daily emergency bonus pool. A single order gets no aggregation discount.
    """
    if n < 2:
        return sum_base_cents, 0
    p_base = int(round(sum_base_cents * (1.0 - settings.aggregation_discount_ratio)))
    return p_base, sum_base_cents - p_base


def time_multiplier(local_hour: int, settings: Settings) -> float:
    """Peak (lunch/dinner) & late-night multiplier for CN local hour [0,24)."""
    if 11 <= local_hour < 13 or 17 <= local_hour < 20:
        return settings.price_peak_multiplier
    if local_hour >= 22 or local_hour < 6:
        return settings.price_latenight_multiplier
    return 1.0


def weather_multiplier(condition: str, settings: Settings) -> float:
    return {
        "clear": 1.0,
        "rain": settings.price_weather_rain_multiplier,
        "heavy_rain": settings.price_weather_heavy_rain_multiplier,
        "snow": settings.price_weather_snow_multiplier,
        "extreme": settings.price_weather_extreme_multiplier,
    }.get(condition, 1.0)


def surge_multiplier(demand: int, supply: int, settings: Settings) -> float:
    """Supply-demand surge: 1 + k·(demand/supply − 1), clamped to [1, surge_max]."""
    r = demand / max(supply, 1)
    surge = 1.0 + settings.surge_k * (r - 1.0)
    return float(min(max(surge, 1.0), settings.surge_max))


def early_gate_discount(rider_charge_cents: int, slack_minutes: float, settings: Settings) -> int:
    """Reward the delivery rider for dropping at the gate early.

    The more SLA slack remains when the rider hands off at the community gate
    (i.e. the earlier they arrive), the larger the discount on their errand fee
    — this buys the Anter more time to aggregate & deliver. Platform-funded.
    """
    if slack_minutes <= 0 or rider_charge_cents <= 0:
        return 0
    ref = settings.early_gate_slack_ref_minutes
    frac = min(slack_minutes / ref, 1.0) if ref > 0 else 1.0
    return int(round(rider_charge_cents * settings.early_gate_discount_ratio_max * frac))


def _distribute(total: int, weights: Dict[str, int]) -> Dict[str, int]:
    """Split `total` across keys proportional to weights, no cents lost."""
    keys = list(weights.keys())
    if not keys:
        return {}
    wsum = sum(weights.values())
    out: Dict[str, int] = {}
    if wsum <= 0:
        base = total // len(keys)
        for k in keys:
            out[k] = base
        out[keys[-1]] += total - base * len(keys)
        return out
    allocated = 0
    for k in keys[:-1]:
        share = round(total * weights[k] / wsum)
        out[k] = share
        allocated += share
    out[keys[-1]] = total - allocated
    return out


def quote(
    orders: List[OrderPriceInput],
    *,
    local_hour: int,
    weather_condition: str,
    demand: int,
    supply: int,
    surge_scope: str = "community",
    total_income_cents: int,
    y_pct: float,
    settings: Settings,
) -> PriceBreakdown:
    """Pure end-to-end quote for a candidate bundle."""
    order_base = {o.order_id: order_base_package(o, settings) for o in orders}
    sum_base = sum(order_base.values())
    n = len(orders)
    p_base, pool_contribution = aggregate_base(sum_base, n, settings)

    m_time = time_multiplier(local_hour, settings)
    m_weather = weather_multiplier(weather_condition, settings)
    m_surge = surge_multiplier(demand, supply, settings)
    m_full = m_time * m_weather * m_surge

    floor_cents = int(round(total_income_cents * settings.price_floor_pct_of_income / 100.0))
    cap_cents = int(settings.price_cap_per_order_cents * max(n, 1))
    raw = int(round(p_base * m_full))
    price = int(min(max(raw, floor_cents), cap_cents))

    # Rider-facing multiplier: capped peak; surge/weather optional per config.
    m_rider = min(m_time, settings.price_rider_peak_cap)
    if settings.rider_bears_weather:
        m_rider *= m_weather
    if settings.rider_bears_surge:
        m_rider *= m_surge
    rider_charge = int(min(round(p_base * m_rider), price))
    rider_charge = max(rider_charge, 0)
    subsidy = price - rider_charge

    platform_fee = int(round(price * y_pct / 100.0))
    anter_net = price - platform_fee

    order_rider = _distribute(rider_charge, order_base)

    return PriceBreakdown(
        base_price_cents=p_base,
        sum_base_cents=sum_base,
        aggregation_discount_ratio=(settings.aggregation_discount_ratio if n >= 2 else 0.0),
        pool_contribution_cents=pool_contribution,
        time_multiplier=m_time,
        weather_multiplier=m_weather,
        surge_multiplier=m_surge,
        full_multiplier=m_full,
        weather_condition=weather_condition,
        demand=demand,
        supply=supply,
        surge_scope=surge_scope,
        floor_cents=floor_cents,
        cap_cents=cap_cents,
        quoted_price_cents=price,
        rider_charge_cents=rider_charge,
        subsidy_cents=subsidy,
        platform_fee_cents=platform_fee,
        anter_net_cents=anter_net,
        order_base_cents=order_base,
        order_rider_charge_cents=order_rider,
    )


# --------------------------------------------------------------------------- #
# DB-integrated helpers
# --------------------------------------------------------------------------- #
def _centroid(orders: List[Order]) -> tuple[float, float]:
    lat = sum(o.lat for o in orders) / len(orders)
    lng = sum(o.lng for o in orders) / len(orders)
    return lat, lng


def _anter_serves(anter: User, community_id: str) -> bool:
    if not anter.service_community_ids:
        return True  # empty => serves all communities
    served = {c.strip() for c in anter.service_community_ids.split(",") if c.strip()}
    return community_id in served


def community_supply_demand(
    session: Session,
    community_id: str,
    settings: Optional[Settings] = None,
    now: Optional[datetime] = None,
) -> tuple[int, int, str]:
    """(demand, supply, scope) for a community, falling back to global when sparse."""
    settings = settings or get_settings()
    now = now or datetime.utcnow()
    awaiting = (BundleStatus.ready, BundleStatus.at_gate)

    demand = len(
        session.exec(
            select(Bundle).where(
                Bundle.community_id == community_id, Bundle.status.in_(awaiting)
            )
        ).all()
    )
    anters = session.exec(
        select(User).where(User.role == Role.anter, User.verified == True)  # noqa: E712
    ).all()

    def _eligible(a: User) -> bool:
        return a.cooldown_until is None or a.cooldown_until <= now

    supply = sum(
        1 for a in anters if _eligible(a) and _anter_serves(a, community_id)
    )

    if demand + supply < settings.surge_min_samples:
        demand = len(
            session.exec(select(Bundle).where(Bundle.status.in_(awaiting))).all()
        )
        supply = sum(1 for a in anters if _eligible(a))
        return demand, supply, "global"
    return demand, supply, "community"


def compute_bundle_quote(
    session: Session,
    bundle: Bundle,
    settings: Optional[Settings] = None,
    now: Optional[datetime] = None,
    map_adapter=None,
    weather_adapter=None,
) -> PriceBreakdown:
    """Gather live inputs and produce a quote for a bundle (does not persist)."""
    from ..adapters import get_map_adapter, get_weather_adapter

    settings = settings or get_settings()
    now = now or datetime.utcnow()
    map_adapter = map_adapter or get_map_adapter()
    weather_adapter = weather_adapter or get_weather_adapter()

    orders = session.exec(select(Order).where(Order.bundle_id == bundle.id)).all()
    if not orders:
        return quote(
            [], local_hour=(now + timedelta(hours=8)).hour, weather_condition="clear",
            demand=0, supply=1, total_income_cents=0, y_pct=bundle.y_rate, settings=settings,
        )

    clat, clng = _centroid(orders)
    weather = weather_adapter.current(clat, clng)
    local_hour = (now + timedelta(hours=8)).hour

    inputs: List[OrderPriceInput] = []
    for o in orders:
        distance_m = map_adapter.walking_distance_m(clat, clng, o.lat, o.lng)
        sla_minutes = (o.sla_deadline - now).total_seconds() / 60.0
        inputs.append(
            OrderPriceInput(
                order_id=o.id,
                distance_m=distance_m,
                floor=o.floor,
                has_elevator=o.has_elevator,
                weight_grams=o.weight_grams,
                category=o.category,
                sla_minutes=sla_minutes,
                rider_income_cents=o.rider_income_cents,
            )
        )

    demand, supply, scope = community_supply_demand(session, bundle.community_id, settings, now)

    return quote(
        inputs,
        local_hour=local_hour,
        weather_condition=weather.condition,
        demand=demand,
        supply=supply,
        surge_scope=scope,
        total_income_cents=bundle.total_income_cents,
        y_pct=bundle.y_rate,
        settings=settings,
    )


def freeze_quote_onto_bundle(
    session: Session,
    bundle: Bundle,
    breakdown: PriceBreakdown,
) -> None:
    """Persist the pricing snapshot onto the bundle, its orders, and an audit row."""
    from datetime import datetime as _dt

    from ..models import EmergencyPoolEntry, PriceQuote

    # the 5% aggregation saving funds the daily emergency bonus pool
    if breakdown.pool_contribution_cents > 0:
        session.add(
            EmergencyPoolEntry(
                day=_dt.utcnow().strftime("%Y-%m-%d"),
                amount_cents=breakdown.pool_contribution_cents,
                kind="contribution",
                bundle_id=bundle.id,
                memo="5% aggregation saving",
            )
        )

    bundle.base_price_cents = breakdown.base_price_cents
    bundle.pool_contribution_cents = breakdown.pool_contribution_cents
    bundle.quoted_price_cents = breakdown.quoted_price_cents
    bundle.errand_fee_cents = breakdown.quoted_price_cents
    bundle.platform_fee_cents = breakdown.platform_fee_cents
    bundle.anter_net_cents = breakdown.anter_net_cents
    bundle.rider_charge_cents = breakdown.rider_charge_cents
    bundle.subsidy_cents = breakdown.subsidy_cents
    bundle.surge_multiplier = breakdown.surge_multiplier
    bundle.time_multiplier = breakdown.time_multiplier
    bundle.weather_multiplier = breakdown.weather_multiplier
    bundle.weather_condition = breakdown.weather_condition
    bundle.pricing_breakdown = breakdown.to_json()
    session.add(bundle)

    for o in session.exec(select(Order).where(Order.bundle_id == bundle.id)).all():
        o.rider_charge_cents = breakdown.order_rider_charge_cents.get(o.id, 0)
        session.add(o)

    session.add(
        PriceQuote(
            bundle_id=bundle.id,
            base_price_cents=breakdown.base_price_cents,
            quoted_price_cents=breakdown.quoted_price_cents,
            rider_charge_cents=breakdown.rider_charge_cents,
            subsidy_cents=breakdown.subsidy_cents,
            platform_fee_cents=breakdown.platform_fee_cents,
            anter_net_cents=breakdown.anter_net_cents,
            surge_multiplier=breakdown.surge_multiplier,
            time_multiplier=breakdown.time_multiplier,
            weather_multiplier=breakdown.weather_multiplier,
            weather_condition=breakdown.weather_condition,
            demand=breakdown.demand,
            supply=breakdown.supply,
            surge_scope=breakdown.surge_scope,
            floor_cents=breakdown.floor_cents,
            cap_cents=breakdown.cap_cents,
            breakdown=breakdown.to_json(),
        )
    )
