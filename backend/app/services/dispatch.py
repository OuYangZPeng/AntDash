"""Dispatch & settlement service.

Orchestrates the second-leg lifecycle:
  gate hand-off -> offer to Anters (ranked by dispatch weight) -> accept
  (binding: must fulfil) -> deliver -> settle (ledger + payout + platform sync).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Optional

from sqlmodel import Session, select

from ..adapters import get_platform_adapters
from ..adapters.base import PaymentAdapter
from ..config import Settings, get_settings
from ..models import (
    Bundle,
    BundleStatus,
    LedgerEntry,
    LedgerType,
    Order,
    OrderStatus,
    ReputationReason,
    Role,
    User,
)
from . import reputation as rep
from .ledger import compute_split, split_from_errand_fee as compute_split_price


class DispatchError(Exception):
    pass


def mark_bundle_at_gate(session: Session, bundle: Bundle, settings: Optional[Settings] = None) -> Bundle:
    """Rider dropped the bundled orders at the community gate."""
    settings = settings or get_settings()
    if bundle.status == BundleStatus.at_gate:
        return bundle  # idempotent: already offerable
    if bundle.status not in (BundleStatus.ready, BundleStatus.open):
        raise DispatchError(f"bundle not droppable in status {bundle.status}")
    bundle.status = BundleStatus.at_gate
    for order in session.exec(select(Order).where(Order.bundle_id == bundle.id)).all():
        order.status = OrderStatus.at_gate
        session.add(order)
    session.add(bundle)
    session.commit()
    session.refresh(bundle)
    return bundle


def rider_gate_dropoff(
    session: Session,
    order: Order,
    settings: Optional[Settings] = None,
    now: Optional[datetime] = None,
) -> dict:
    """Delivery rider confirms this order is dropped at the community gate.

    Applies an *earliness discount* to the rider's errand fee (the earlier vs.
    the order SLA, the bigger the discount; platform absorbs it so the Anter's
    payout is unchanged). Advances the bundle to `at_gate` once all its orders
    are dropped. Idempotent per order.
    """
    from .pricing import early_gate_discount

    settings = settings or get_settings()
    now = now or datetime.utcnow()
    if order.gate_dropoff_at is not None:
        return {"discount_cents": order.gate_discount_cents, "already": True,
                "all_dropped": False}

    slack_minutes = (order.sla_deadline - now).total_seconds() / 60.0
    discount = early_gate_discount(order.rider_charge_cents, slack_minutes, settings)
    order.gate_dropoff_at = now
    order.gate_discount_cents = discount
    order.rider_charge_cents = max(0, order.rider_charge_cents - discount)
    order.status = OrderStatus.at_gate
    session.add(order)

    bundle = session.get(Bundle, order.bundle_id) if order.bundle_id else None
    all_dropped = False
    if bundle is not None:
        # platform absorbs the discount so the Anter still gets full payout
        bundle.subsidy_cents += discount
        session.add(bundle)
        siblings = session.exec(select(Order).where(Order.bundle_id == bundle.id)).all()
        all_dropped = all(o.gate_dropoff_at is not None for o in siblings)
        if all_dropped and bundle.status in (BundleStatus.ready, BundleStatus.open):
            try:
                mark_bundle_at_gate(session, bundle, settings)
            except DispatchError:
                pass
    session.commit()
    return {
        "discount_cents": discount,
        "slack_minutes": round(slack_minutes, 1),
        "all_dropped": all_dropped,
        "already": False,
    }


def rank_anters(session: Session, settings: Optional[Settings] = None) -> List[User]:
    """Eligible Anters ordered by dispatch weight (cooldown ones excluded)."""
    settings = settings or get_settings()
    now = datetime.utcnow()
    anters = session.exec(
        select(User).where(User.role == Role.anter, User.verified == True)  # noqa: E712
    ).all()
    eligible = [a for a in anters if not rep.is_in_cooldown(a, now)]
    eligible.sort(key=lambda a: rep.dispatch_weight(a.reputation_score, settings), reverse=True)
    return eligible


def list_offerable_bundles(session: Session) -> List[Bundle]:
    return session.exec(
        select(Bundle).where(Bundle.status == BundleStatus.at_gate)
    ).all()


def accept_bundle(
    session: Session,
    bundle: Bundle,
    anter: User,
    settings: Optional[Settings] = None,
) -> Bundle:
    settings = settings or get_settings()
    if bundle.status != BundleStatus.at_gate:
        raise DispatchError("bundle is not available for acceptance")
    if rep.is_in_cooldown(anter):
        raise DispatchError("anter is in cooldown")
    bundle.anter_id = anter.id
    bundle.status = BundleStatus.accepted
    bundle.accepted_at = datetime.utcnow()
    # delivery SLA: min remaining order SLA, capped to 30 min from acceptance
    bundle.delivery_deadline = bundle.accepted_at + timedelta(minutes=30)
    session.add(bundle)
    session.commit()
    session.refresh(bundle)
    return bundle


def abandon_bundle(session: Session, bundle: Bundle, settings: Optional[Settings] = None) -> Bundle:
    """Anter accepted but failed to fulfil -> penalise and re-open to gate."""
    settings = settings or get_settings()
    if bundle.status != BundleStatus.accepted or not bundle.anter_id:
        raise DispatchError("bundle is not in an abandonable state")
    anter = session.get(User, bundle.anter_id)
    if anter:
        rep.record_event(session, anter, ReputationReason.abandon, memo=f"abandoned {bundle.id}", settings=settings)
    bundle.anter_id = None
    bundle.accepted_at = None
    bundle.delivery_deadline = None
    bundle.status = BundleStatus.at_gate
    session.add(bundle)
    session.commit()
    session.refresh(bundle)
    return bundle


def deliver_bundle(
    session: Session,
    bundle: Bundle,
    payment: PaymentAdapter,
    complaint: bool = False,
    settings: Optional[Settings] = None,
) -> Bundle:
    """Anter delivered: settle ledger, pay out, sync platforms, update reputation."""
    settings = settings or get_settings()
    if bundle.status != BundleStatus.accepted or not bundle.anter_id:
        raise DispatchError("bundle is not in a deliverable state")

    # every sub-order must be photographed individually before settlement
    pending = session.exec(
        select(Order).where(Order.bundle_id == bundle.id, Order.proof_uploaded == False)  # noqa: E712
    ).all()
    if pending:
        raise DispatchError(f"还有 {len(pending)} 个子单未拍照上传")

    now = datetime.utcnow()
    bundle.delivered_at = now
    bundle.status = BundleStatus.delivered

    orders = session.exec(select(Order).where(Order.bundle_id == bundle.id)).all()

    # --- split & immutable ledger ---
    # Dynamic pricing: errand fee = frozen quoted price P; riders pay only the
    # deterministic rider_charge, platform subsidises the surge/weather premium.
    dynamic = settings.pricing_enabled and bundle.quoted_price_cents > 0
    if dynamic:
        # effective errand fee = frozen quoted price + urgency fee (加急费, platform-funded)
        effective = bundle.quoted_price_cents + bundle.urgency_fee_cents
        split = compute_split_price(effective, bundle.y_rate)
        rider_debits = {o.id: o.rider_charge_cents for o in orders}
        subsidy_cents = bundle.subsidy_cents + bundle.urgency_fee_cents
    else:
        split = compute_split(bundle.total_income_cents, bundle.x_rate, bundle.y_rate)
        # legacy: errand fee debited from riders proportional to contribution
        rider_debits = {}
        for order in orders:
            if bundle.total_income_cents > 0:
                rider_debits[order.id] = round(
                    split.errand_fee_cents * order.rider_income_cents / bundle.total_income_cents
                )
            else:
                rider_debits[order.id] = 0
        subsidy_cents = 0

    # rescue bonus (奖金池) for whoever delivers a bundle that went into rescue.
    rescue_bonus = settings.rider_rescue_bonus_cents if bundle.rescue else 0
    anter_net_total = split.anter_net_cents + rescue_bonus

    bundle.errand_fee_cents = split.errand_fee_cents
    bundle.platform_fee_cents = split.platform_fee_cents
    bundle.anter_net_cents = anter_net_total

    # errand fee debited from riders
    for order in orders:
        share = rider_debits.get(order.id, 0)
        if order.rider_id:
            rider = session.get(User, order.rider_id)
            if rider:
                rider.balance_cents -= share
                session.add(rider)
        session.add(
            LedgerEntry(
                bundle_id=bundle.id,
                type=LedgerType.errand_fee_debit,
                account_id=order.rider_id,
                amount_cents=-share,
                memo=f"errand fee debit for order {order.external_id}",
            )
        )

    # platform-funded subsidy (surge/weather/urgency premium beyond rider charge)
    if subsidy_cents:
        session.add(
            LedgerEntry(
                bundle_id=bundle.id,
                type=LedgerType.platform_subsidy,
                account_id=None,
                amount_cents=subsidy_cents,
                memo="platform surge/weather/urgency subsidy",
            )
        )

    # rescue bonus (奖金池) credited to the deliverer, drawn from the daily pool
    if rescue_bonus:
        session.add(
            LedgerEntry(
                bundle_id=bundle.id,
                type=LedgerType.rescue_bonus,
                account_id=bundle.anter_id,
                amount_cents=rescue_bonus,
                memo="rescue bonus for near-timeout delivery",
            )
        )
        from ..models import EmergencyPoolEntry

        session.add(
            EmergencyPoolEntry(
                day=now.strftime("%Y-%m-%d"),
                amount_cents=-rescue_bonus,
                kind="rescue_payout",
                bundle_id=bundle.id,
                memo="rescue bonus payout",
            )
        )

    # platform maintenance fee
    session.add(
        LedgerEntry(
            bundle_id=bundle.id,
            type=LedgerType.platform_fee,
            account_id=None,
            amount_cents=split.platform_fee_cents,
            memo="AntDash maintenance fee",
        )
    )

    # net credit to Anter (includes rescue bonus)
    anter = session.get(User, bundle.anter_id)
    if anter:
        anter.balance_cents += anter_net_total
        session.add(anter)
        payment.payout("anter-wallet", anter_net_total, memo=f"bundle {bundle.id}")
    session.add(
        LedgerEntry(
            bundle_id=bundle.id,
            type=LedgerType.anter_credit,
            account_id=bundle.anter_id,
            amount_cents=anter_net_total,
            memo="anter net income",
        )
    )

    # --- reputation ---
    if anter:
        # rescuing a near-timeout bundle grants a reputation boost -> dispatch priority
        if bundle.rescue:
            anter.rescue_count += 1
            session.add(anter)
            rep.record_event(session, anter, ReputationReason.rescue, memo=f"rescue {bundle.id}", settings=settings)
        if complaint:
            rep.record_event(session, anter, ReputationReason.complaint, memo=f"complaint {bundle.id}", settings=settings)
        elif bundle.delivery_deadline and now <= bundle.delivery_deadline:
            # early if delivered with >10 min headroom
            headroom = (bundle.delivery_deadline - now).total_seconds() / 60.0
            reason = ReputationReason.early if headroom > 10 else ReputationReason.on_time
            rep.record_event(session, anter, reason, memo=f"delivered {bundle.id}", settings=settings)
        else:
            rep.record_event(session, anter, ReputationReason.late, memo=f"late {bundle.id}", settings=settings)

    # --- sync order status back to platforms ---
    adapters = get_platform_adapters()
    for order in orders:
        order.status = OrderStatus.synced
        session.add(order)
        adapter = adapters.get(order.platform.value if hasattr(order.platform, "value") else order.platform)
        if adapter:
            adapter.push_status(order.external_id, "delivered")

    bundle.status = BundleStatus.settled
    session.add(bundle)
    session.commit()
    session.refresh(bundle)
    return bundle
