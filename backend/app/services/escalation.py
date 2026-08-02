"""Near-timeout escalation & rider rescue (临期未接单升级).

Unaccepted bundles are swept periodically; as the soonest sub-order approaches
its SLA, we escalate:
  - grow a platform-funded **urgency fee** (加急费) so accepting an urgent bundle
    pays more (rider/骑手 is not charged extra — the platform subsidises it),
  - widen the notification radius and re-push to more Anters,
  - once remaining < rescue_threshold, push a **rescue** alert to nearby 外卖骑手
    (who can act as Anters); rescuing earns a bonus + reputation (→ dispatch priority).

The pure helpers are unit-tested; `sweep_once` is the DB-integrated step and
`run_sweeper` is the thin async loop started at app startup.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from ..config import Settings, get_settings
from ..models import Bundle, BundleStatus, Order


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def escalation_stage(remaining_minutes: float, settings: Settings) -> int:
    """0 normal · 1 nudge · 2 rescue(<threshold) · 3 critical · 4 breached."""
    if remaining_minutes > settings.urgency_start_minutes:
        return 0
    if remaining_minutes > settings.rescue_threshold_minutes:
        return 1
    if remaining_minutes > 6:
        return 2
    if remaining_minutes > 0:
        return 3
    return 4


def is_rescue(remaining_minutes: float, settings: Settings) -> bool:
    """Rider-rescue kicks in below the rescue threshold (default <15 min)."""
    return remaining_minutes <= settings.rescue_threshold_minutes


def urgency_fee_cents(base_price_cents: int, remaining_minutes: float, settings: Settings) -> int:
    """Platform-funded urgency fee, ramping 0 → base×max_ratio as time runs out."""
    start = settings.urgency_start_minutes
    if remaining_minutes >= start or start <= 0:
        return 0
    frac = min(1.0, max(0.0, (start - remaining_minutes) / start))
    return int(round(base_price_cents * settings.urgency_fee_max_ratio * frac))


def push_radius_km(stage: int, settings: Settings) -> float:
    """Notification radius grows with stage, capped at escalation_radius_max_km."""
    if stage <= 1:
        return settings.notify_radius_km
    widened = settings.notify_radius_km + settings.escalation_radius_step_km * (stage - 1)
    return float(min(widened, settings.escalation_radius_max_km))


# --------------------------------------------------------------------------- #
# DB-integrated sweep
# --------------------------------------------------------------------------- #
def sweep_once(session: Session, settings: Optional[Settings] = None, now: Optional[datetime] = None) -> dict:
    """Advance escalation for all unaccepted (at_gate) bundles once.

    Updates urgency fee / stage / rescue flag, and re-pushes to nearby users
    (riders included on rescue) when a bundle escalates to a new stage.
    """
    from .notifications import get_hub

    settings = settings or get_settings()
    now = now or datetime.utcnow()
    hub = get_hub()

    bundles = session.exec(
        select(Bundle).where(Bundle.status == BundleStatus.at_gate)
    ).all()
    escalated = 0
    rescues = 0
    for b in bundles:
        orders = session.exec(select(Order).where(Order.bundle_id == b.id)).all()
        if not orders:
            continue
        soonest = min(o.sla_deadline for o in orders)
        remaining = (soonest - now).total_seconds() / 60.0

        stage = escalation_stage(remaining, settings)
        prev_stage = b.escalation_stage
        b.urgency_fee_cents = urgency_fee_cents(b.base_price_cents, remaining, settings)
        if is_rescue(remaining, settings):
            b.rescue = True
        b.escalation_stage = stage
        session.add(b)

        # Only (re)push when the bundle crosses into a higher stage (avoid spam).
        if stage > prev_stage and stage >= 1:
            clat = sum(o.lat for o in orders) / len(orders)
            clng = sum(o.lng for o in orders) / len(orders)
            rescue = is_rescue(remaining, settings)
            event = {
                "type": "rescue" if rescue else "urgent",
                "bundle_id": b.id,
                "community_name": b.community_name,
                "order_count": b.order_count,
                "urgency_fee_cents": b.urgency_fee_cents,
                "anter_net_cents": b.anter_net_cents + b.urgency_fee_cents,
                "remaining_minutes": max(0, int(remaining)),
                "stage": stage,
            }
            if rescue:
                # rescue: push to riders + anters within the 1km rescue radius
                rescues += hub.publish_new_bundle(
                    event, clat, clng, settings.notify_radius_km
                )
            else:
                hub.publish_new_bundle(event, clat, clng, push_radius_km(stage, settings))
            escalated += 1

    session.commit()
    return {"scanned": len(bundles), "escalated": escalated, "rescue_pushes": rescues}


async def run_sweeper() -> None:
    """Background loop: escalate unaccepted bundles every escalation_sweep_seconds."""
    from ..database import engine

    settings = get_settings()
    if not settings.escalation_enabled:
        return
    while True:
        await asyncio.sleep(settings.escalation_sweep_seconds)
        try:
            with Session(engine) as session:
                sweep_once(session, settings)
        except Exception:  # noqa: BLE001 - never let the loop die
            pass
