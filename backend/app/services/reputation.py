"""Anter reputation & dispatch-frequency engine (信誉/派单频率引擎).

Principle: reward Anters who fulfil on time, penalise those who abandon
accepted orders, deliver late, or get complaints. Reputation drives how
frequently / preferentially an Anter is offered bundles.

    score S in [0, 100], start 60
    on-time  +3     early +1
    late     -5     abandon -15     complaint -10
    on-time-rate smoothed with EWMA
    dispatch_weight = base * sigmoid((S - midpoint) / scale)
    S below cooldown threshold -> temporary cooldown (fewer/no offers)
    passive recovery toward the initial score while idle & compliant
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlmodel import Session

from ..config import Settings, get_settings
from ..models import ReputationEvent, ReputationReason, User


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


@dataclass
class RepUpdate:
    score: float
    on_time_rate: float
    delta: float


def _delta_for(reason: ReputationReason, settings: Settings) -> float:
    return {
        ReputationReason.on_time: settings.rep_delta_on_time,
        ReputationReason.early: settings.rep_delta_early,
        ReputationReason.late: settings.rep_delta_late,
        ReputationReason.abandon: settings.rep_delta_abandon,
        ReputationReason.complaint: settings.rep_delta_complaint,
        ReputationReason.recovery: 0.0,
        ReputationReason.rescue: settings.rescue_reputation_bonus,
    }[reason]


def apply_event(
    score: float,
    on_time_rate: float,
    reason: ReputationReason,
    settings: Settings,
) -> RepUpdate:
    """Pure reputation state transition for a single event."""
    delta = _delta_for(reason, settings)
    new_score = _clamp(score + delta, settings.reputation_min, settings.reputation_max)

    # Update EWMA on-time rate for events that reflect timeliness outcomes.
    a = settings.rep_ewma_alpha
    outcome: Optional[float] = None
    if reason in (ReputationReason.on_time, ReputationReason.early):
        outcome = 1.0
    elif reason in (ReputationReason.late, ReputationReason.abandon):
        outcome = 0.0
    # complaints don't directly change the on-time rate

    new_rate = on_time_rate if outcome is None else a * outcome + (1 - a) * on_time_rate
    return RepUpdate(score=new_score, on_time_rate=new_rate, delta=delta)


def dispatch_weight(score: float, settings: Settings) -> float:
    """Relative likelihood/priority of being offered a bundle."""
    x = (score - settings.dispatch_sigmoid_midpoint) / settings.dispatch_sigmoid_scale
    return settings.dispatch_base_weight * sigmoid(x)


def passive_recovery(score: float, minutes: float, settings: Settings) -> float:
    """Slowly drift back toward the initial score while idle & compliant."""
    if score >= settings.reputation_initial:
        return score
    recovered = score + settings.rep_recovery_per_minute * minutes
    return _clamp(min(recovered, settings.reputation_initial), settings.reputation_min, settings.reputation_max)


# --------------------------------------------------------------------------- #
# Database-integrated service
# --------------------------------------------------------------------------- #

def record_event(
    session: Session,
    anter: User,
    reason: ReputationReason,
    memo: str = "",
    settings: Optional[Settings] = None,
) -> ReputationEvent:
    settings = settings or get_settings()
    upd = apply_event(anter.reputation_score, anter.on_time_rate, reason, settings)
    anter.reputation_score = upd.score
    anter.on_time_rate = upd.on_time_rate

    # enter cooldown if score dropped below threshold
    if upd.score < settings.dispatch_cooldown_score:
        anter.cooldown_until = datetime.utcnow() + timedelta(minutes=settings.dispatch_cooldown_minutes)

    event = ReputationEvent(
        anter_id=anter.id,
        reason=reason,
        delta=upd.delta,
        score_after=upd.score,
        on_time_rate_after=upd.on_time_rate,
        memo=memo,
    )
    session.add(event)
    session.add(anter)
    session.commit()
    session.refresh(event)
    return event


def is_in_cooldown(anter: User, now: Optional[datetime] = None) -> bool:
    now = now or datetime.utcnow()
    return anter.cooldown_until is not None and anter.cooldown_until > now
