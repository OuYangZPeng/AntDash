"""Dispatch endpoints: gate hand-off, offers, accept, deliver, abandon."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from ..adapters import MockPaymentAdapter
from ..database import get_session
from ..models import Bundle, Role, User
from ..schemas import BundleOut
from ..services import dispatch as dispatch_service
from .deps import require_verified
from .orders import bundle_out

router = APIRouter(prefix="/dispatch", tags=["dispatch"])
_payment = MockPaymentAdapter()


def _get_bundle(session: Session, bundle_id: str) -> Bundle:
    b = session.get(Bundle, bundle_id)
    if not b:
        raise HTTPException(404, "bundle not found")
    return b


@router.post("/bundles/{bundle_id}/at-gate", response_model=BundleOut)
def rider_drop_at_gate(bundle_id: str, session: Session = Depends(get_session)):
    b = _get_bundle(session, bundle_id)
    try:
        b = dispatch_service.mark_bundle_at_gate(session, b)
    except dispatch_service.DispatchError as e:
        raise HTTPException(409, str(e))
    return bundle_out(session, b, viewer_role=Role.rider)


@router.get("/offers", response_model=List[BundleOut])
def offerable_bundles(
    user: User = Depends(require_verified),
    session: Session = Depends(get_session),
):
    bundles = dispatch_service.list_offerable_bundles(session)
    return [bundle_out(session, b, viewer_role=Role.anter) for b in bundles]


@router.post("/bundles/{bundle_id}/accept", response_model=BundleOut)
def accept(
    bundle_id: str,
    user: User = Depends(require_verified),
    session: Session = Depends(get_session),
):
    b = _get_bundle(session, bundle_id)
    try:
        b = dispatch_service.accept_bundle(session, b, user)
    except dispatch_service.DispatchError as e:
        raise HTTPException(409, str(e))
    return bundle_out(session, b, viewer_role=Role.anter)


@router.post("/bundles/{bundle_id}/deliver", response_model=BundleOut)
def deliver(
    bundle_id: str,
    complaint: bool = Query(False),
    user: User = Depends(require_verified),
    session: Session = Depends(get_session),
):
    b = _get_bundle(session, bundle_id)
    if b.anter_id != user.id:
        raise HTTPException(403, "not your bundle")
    try:
        b = dispatch_service.deliver_bundle(session, b, _payment, complaint=complaint)
    except dispatch_service.DispatchError as e:
        raise HTTPException(409, str(e))
    return bundle_out(session, b, viewer_role=Role.anter)


@router.post("/bundles/{bundle_id}/abandon", response_model=BundleOut)
def abandon(
    bundle_id: str,
    user: User = Depends(require_verified),
    session: Session = Depends(get_session),
):
    b = _get_bundle(session, bundle_id)
    if b.anter_id != user.id:
        raise HTTPException(403, "not your bundle")
    try:
        b = dispatch_service.abandon_bundle(session, b)
    except dispatch_service.DispatchError as e:
        raise HTTPException(409, str(e))
    return bundle_out(session, b, viewer_role=Role.anter)
