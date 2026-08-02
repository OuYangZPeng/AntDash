"""Shared API dependencies."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session

from ..database import get_session
from ..models import User
from ..services import auth as auth_service


def get_current_user(
    authorization: str = Header(default=""),
    session: Session = Depends(get_session),
) -> User:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = auth_service.decode_token(token)
    except Exception:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    user = session.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return user


def require_verified(user: User = Depends(get_current_user)) -> User:
    if not user.verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "real-name verification required")
    return user
