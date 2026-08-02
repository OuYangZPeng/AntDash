"""Auth & real-name endpoints."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from ..database import get_session
from ..models import User
from ..schemas import (
    OAuthLoginRequest,
    PhoneLoginRequest,
    RealNameRequest,
    TokenResponse,
    UserOut,
)
from ..services import auth as auth_service
from .deps import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(user: User) -> TokenResponse:
    return TokenResponse(
        token=auth_service.create_token(user),
        user_id=user.id,
        role=user.role,
        verified=user.verified,
    )


@router.post("/login/phone", response_model=TokenResponse)
def login_phone(req: PhoneLoginRequest, session: Session = Depends(get_session)):
    # Mock OTP: accept any 4+ digit code.
    if len(req.otp) < 4:
        raise HTTPException(400, "invalid otp")
    user = auth_service.login_phone(session, req.phone, role=req.role)
    return _token_response(user)


@router.post("/login/wechat", response_model=TokenResponse)
def login_wechat(req: OAuthLoginRequest, session: Session = Depends(get_session)):
    # Mock: exchange code for a stable pseudo openid.
    openid = f"wx_{uuid.uuid5(uuid.NAMESPACE_OID, req.code).hex[:16]}"
    user = auth_service.login_wechat(session, openid, role=req.role)
    return _token_response(user)


@router.post("/login/alipay", response_model=TokenResponse)
def login_alipay(req: OAuthLoginRequest, session: Session = Depends(get_session)):
    alipay_uid = f"ali_{uuid.uuid5(uuid.NAMESPACE_OID, req.code).hex[:16]}"
    user = auth_service.login_alipay(session, alipay_uid, role=req.role)
    return _token_response(user)


@router.post("/real-name", response_model=UserOut)
def real_name(
    req: RealNameRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    try:
        user = auth_service.verify_real_name(session, user, req.name, req.id_card)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _user_out(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return _user_out(user)


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        role=user.role,
        phone=user.phone,
        name=user.name,
        verified=user.verified,
        reputation_score=user.reputation_score,
        on_time_rate=user.on_time_rate,
        balance_cents=user.balance_cents,
        rescue_count=user.rescue_count,
    )
