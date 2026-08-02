"""Delivery-proof (拍照凭证) service: persist uploaded photos to media dir."""
from __future__ import annotations

import os
import uuid
from typing import Optional

from sqlmodel import Session

from ..config import get_settings
from ..models import Proof, ProofType


def save_proof_image(content: bytes, suffix: str = ".jpg") -> str:
    settings = get_settings()
    os.makedirs(settings.media_dir, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{suffix}"
    path = os.path.join(settings.media_dir, fname)
    with open(path, "wb") as f:
        f.write(content)
    return path


def record_proof(
    session: Session,
    proof_type: ProofType,
    image_path: str,
    bundle_id: Optional[str] = None,
    order_id: Optional[str] = None,
    uploaded_by: Optional[str] = None,
) -> Proof:
    proof = Proof(
        bundle_id=bundle_id,
        order_id=order_id,
        type=proof_type,
        image_path=image_path,
        uploaded_by=uploaded_by,
    )
    session.add(proof)
    session.commit()
    session.refresh(proof)
    return proof
