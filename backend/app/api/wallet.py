"""Wallet & payment-method endpoints."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..adapters import MockPaymentAdapter
from ..database import get_session
from ..models import LedgerEntry, LedgerType, PaymentMethod, User
from ..schemas import BindPaymentRequest, PaymentMethodOut
from .deps import get_current_user

router = APIRouter(prefix="/wallet", tags=["wallet"])
_payment = MockPaymentAdapter()


@router.get("/balance")
def balance(user: User = Depends(get_current_user)):
    return {"balance_cents": user.balance_cents, "balance_yuan": round(user.balance_cents / 100, 2)}


@router.get("/ledger")
def ledger(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    entries = session.exec(
        select(LedgerEntry).where(LedgerEntry.account_id == user.id).order_by(LedgerEntry.created_at.desc())
    ).all()
    return [
        {
            "id": e.id,
            "bundle_id": e.bundle_id,
            "type": e.type.value if hasattr(e.type, "value") else e.type,
            "amount_cents": e.amount_cents,
            "memo": e.memo,
            "created_at": e.created_at,
        }
        for e in entries
    ]


@router.post("/methods", response_model=PaymentMethodOut)
def bind_method(
    req: BindPaymentRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    result = _payment.bind_method(req.kind, req.credential)
    if not result.ok:
        raise HTTPException(400, result.message)
    existing = session.exec(select(PaymentMethod).where(PaymentMethod.user_id == user.id)).all()
    pm = PaymentMethod(
        user_id=user.id,
        kind=req.kind,
        display=req.display or f"**** {req.credential[-4:]}",
        token=result.transaction_id,
        is_default=len(existing) == 0,
    )
    session.add(pm)
    session.commit()
    session.refresh(pm)
    return PaymentMethodOut(id=pm.id, kind=pm.kind, display=pm.display, is_default=pm.is_default)


@router.get("/methods", response_model=List[PaymentMethodOut])
def list_methods(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    methods = session.exec(select(PaymentMethod).where(PaymentMethod.user_id == user.id)).all()
    return [PaymentMethodOut(id=m.id, kind=m.kind, display=m.display, is_default=m.is_default) for m in methods]


@router.post("/withdraw")
def withdraw(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    if user.balance_cents <= 0:
        raise HTTPException(400, "no balance to withdraw")
    amount = user.balance_cents
    result = _payment.payout("wallet", amount, memo="withdraw")
    if not result.ok:
        raise HTTPException(400, result.message)
    user.balance_cents = 0
    session.add(user)
    session.commit()
    return {"withdrawn_cents": amount, "transaction_id": result.transaction_id}
