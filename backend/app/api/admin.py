"""Admin config & preview endpoints (X/Y ratios, matching window, pricing)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select

from ..config import get_settings
from ..database import get_session
from ..models import EmergencyPoolEntry
from ..schemas import ConfigUpdate, PricePreview, SplitPreview
from ..services import pricing
from ..services.ledger import compute_split

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/pool")
def emergency_pool(day: Optional[str] = None, session: Session = Depends(get_session)):
    """当天应急奖金池:5% 聚合折扣的累计投入 − 救援等紧急支出 = 余额。"""
    day = day or datetime.utcnow().strftime("%Y-%m-%d")
    entries = session.exec(
        select(EmergencyPoolEntry).where(EmergencyPoolEntry.day == day)
    ).all()
    contributions = sum(e.amount_cents for e in entries if e.amount_cents > 0)
    payouts = -sum(e.amount_cents for e in entries if e.amount_cents < 0)
    return {
        "day": day,
        "contributions_cents": contributions,
        "payouts_cents": payouts,
        "balance_cents": contributions - payouts,
        "entries": len(entries),
    }


@router.get("/config")
def get_config():
    s = get_settings()
    return {
        "errand_fee_pct_X": s.errand_fee_pct_X,
        "platform_fee_pct_Y": s.platform_fee_pct_Y,
        "match_window_base_minutes": s.match_window_base_minutes,
        "match_window_min_minutes": s.match_window_min_minutes,
        "match_window_max_minutes": s.match_window_max_minutes,
        "match_target_bundle_size": s.match_target_bundle_size,
        "match_max_bundle_size": s.match_max_bundle_size,
        "pricing_enabled": s.pricing_enabled,
        "surge_k": s.surge_k,
        "surge_max": s.surge_max,
        "price_base_start_cents": s.price_base_start_cents,
        "price_cap_per_order_cents": s.price_cap_per_order_cents,
        "rider_bears_surge": s.rider_bears_surge,
        "rider_bears_weather": s.rider_bears_weather,
    }


@router.patch("/config")
def update_config(update: ConfigUpdate):
    """Runtime override of tunables (in-memory for the MVP)."""
    s = get_settings()
    data = update.model_dump(exclude_none=True)
    for key, value in data.items():
        setattr(s, key, value)
    return get_config()


@router.get("/split-preview", response_model=SplitPreview)
def split_preview(total_income_cents: int = Query(..., ge=0)):
    s = get_settings()
    split = compute_split(total_income_cents, s.errand_fee_pct_X, s.platform_fee_pct_Y)
    return SplitPreview(
        total_income_cents=split.total_income_cents,
        errand_fee_cents=split.errand_fee_cents,
        platform_fee_cents=split.platform_fee_cents,
        anter_net_cents=split.anter_net_cents,
        x_rate=split.x_rate,
        y_rate=split.y_rate,
    )


@router.get("/price-preview", response_model=PricePreview)
def price_preview(
    order_count: int = Query(4, ge=1, le=20),
    total_income_cents: int = Query(4000, ge=0),
    distance_m: float = Query(150.0, ge=0),
    floor: int = Query(6, ge=1),
    has_elevator: bool = Query(True),
    weight_grams: int = Query(1000, ge=0),
    category: str = Query("normal"),
    sla_minutes: float = Query(20.0),
    local_hour: int = Query(18, ge=0, le=23),
    weather_condition: str = Query("clear"),
    demand: int = Query(3, ge=0),
    supply: int = Query(2, ge=0),
):
    """Dry-run the dynamic pricing engine for a hypothetical bundle."""
    s = get_settings()
    per_income = round(total_income_cents / max(order_count, 1))
    orders = [
        pricing.OrderPriceInput(
            order_id=f"o{i}",
            distance_m=distance_m,
            floor=floor,
            has_elevator=has_elevator,
            weight_grams=weight_grams,
            category=category,
            sla_minutes=sla_minutes,
            rider_income_cents=per_income,
        )
        for i in range(order_count)
    ]
    bd = pricing.quote(
        orders,
        local_hour=local_hour,
        weather_condition=weather_condition,
        demand=demand,
        supply=supply,
        total_income_cents=total_income_cents,
        y_pct=s.platform_fee_pct_Y,
        settings=s,
    )
    return PricePreview(
        base_price_cents=bd.base_price_cents,
        time_multiplier=bd.time_multiplier,
        weather_multiplier=bd.weather_multiplier,
        surge_multiplier=bd.surge_multiplier,
        full_multiplier=bd.full_multiplier,
        quoted_price_cents=bd.quoted_price_cents,
        rider_charge_cents=bd.rider_charge_cents,
        subsidy_cents=bd.subsidy_cents,
        platform_fee_cents=bd.platform_fee_cents,
        anter_net_cents=bd.anter_net_cents,
        floor_cents=bd.floor_cents,
        cap_cents=bd.cap_cents,
        weather_condition=bd.weather_condition,
    )
