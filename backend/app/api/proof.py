"""Photo-proof upload endpoints (gate drop-off & final delivery)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session

from sqlmodel import select

from ..database import get_session
from ..models import Bundle, Order, ProofType, User
from ..services import proof as proof_service
from .deps import get_current_user

router = APIRouter(prefix="/proof", tags=["proof"])


@router.post("/bundles/{bundle_id}/gate")
async def upload_gate_proof(
    bundle_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Rider uploads a photo of the drop at the community gate."""
    if not session.get(Bundle, bundle_id):
        raise HTTPException(404, "bundle not found")
    content = await file.read()
    path = proof_service.save_proof_image(content)
    p = proof_service.record_proof(
        session, ProofType.gate_dropoff, path, bundle_id=bundle_id, uploaded_by=user.id
    )
    return {"proof_id": p.id, "image_path": p.image_path}


@router.post("/bundles/{bundle_id}/delivery")
async def upload_delivery_proof(
    bundle_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Anter uploads a photo of the final delivery at the customer's door."""
    if not session.get(Bundle, bundle_id):
        raise HTTPException(404, "bundle not found")
    content = await file.read()
    path = proof_service.save_proof_image(content)
    p = proof_service.record_proof(
        session, ProofType.final_delivery, path, bundle_id=bundle_id, uploaded_by=user.id
    )
    return {"proof_id": p.id, "image_path": p.image_path}


@router.post("/orders/{order_id}/gate")
async def upload_order_gate_proof(
    order_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Delivery rider confirms + photographs dropping THIS order at the gate.

    Records the gate photo and applies the earliness discount to the rider's
    errand fee (the earlier vs. the order SLA, the bigger the reward).
    """
    from ..services import dispatch as dispatch_service

    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(404, "order not found")
    content = await file.read()
    path = proof_service.save_proof_image(content)
    proof_service.record_proof(
        session, ProofType.gate_dropoff, path,
        bundle_id=order.bundle_id, order_id=order_id, uploaded_by=user.id,
    )
    result = dispatch_service.rider_gate_dropoff(session, order)
    return {"order_id": order_id, **result}


@router.post("/orders/{order_id}/delivery")
async def upload_order_delivery_proof(
    order_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Anter uploads a delivery photo for ONE sub-order in the bundle.

    Each sub-order is photographed individually; the bundle can only be settled
    once every sub-order has its own proof.
    """
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(404, "order not found")
    content = await file.read()
    path = proof_service.save_proof_image(content)
    p = proof_service.record_proof(
        session, ProofType.final_delivery, path,
        bundle_id=order.bundle_id, order_id=order_id, uploaded_by=user.id,
    )
    order.proof_uploaded = True
    session.add(order)
    session.commit()

    siblings = session.exec(select(Order).where(Order.bundle_id == order.bundle_id)).all()
    remaining = [o for o in siblings if not o.proof_uploaded]
    return {
        "proof_id": p.id,
        "image_path": p.image_path,
        "order_id": order_id,
        "all_uploaded": len(remaining) == 0,
        "remaining": len(remaining),
    }
