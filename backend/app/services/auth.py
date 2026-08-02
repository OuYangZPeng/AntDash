"""Authentication & real-name registration service.

Login methods mirror Meituan-style options: WeChat, phone (OTP), Alipay.
Real-name (实名) verification is required before an Anter can accept bundles.
Tokens are JWTs signed with the configured secret.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import jwt
from sqlmodel import Session, select

from ..adapters import MockIdentityAdapter
from ..config import get_settings
from ..models import Role, User

_identity = MockIdentityAdapter()


def create_token(user: User) -> str:
    settings = get_settings()
    payload = {
        "sub": user.id,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "exp": datetime.utcnow() + timedelta(minutes=settings.jwt_ttl_minutes),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])


def _get_or_create(session: Session, *, phone: Optional[str] = None,
                   wechat_openid: Optional[str] = None, alipay_uid: Optional[str] = None,
                   role: Role = Role.anter) -> User:
    stmt = None
    if phone:
        stmt = select(User).where(User.phone == phone)
    elif wechat_openid:
        stmt = select(User).where(User.wechat_openid == wechat_openid)
    elif alipay_uid:
        stmt = select(User).where(User.alipay_uid == alipay_uid)
    user = session.exec(stmt).first() if stmt is not None else None
    if user is None:
        user = User(role=role, phone=phone, wechat_openid=wechat_openid, alipay_uid=alipay_uid)
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


def login_phone(session: Session, phone: str, role: Role = Role.anter) -> User:
    # OTP verification is mocked: any code accepted upstream in the API layer.
    return _get_or_create(session, phone=phone, role=role)


def login_wechat(session: Session, openid: str, role: Role = Role.anter) -> User:
    return _get_or_create(session, wechat_openid=openid, role=role)


def login_alipay(session: Session, alipay_uid: str, role: Role = Role.anter) -> User:
    return _get_or_create(session, alipay_uid=alipay_uid, role=role)


def verify_real_name(session: Session, user: User, name: str, id_card: str) -> User:
    result = _identity.verify(name, id_card)
    if not result.ok:
        raise ValueError(result.message)
    user.name = result.name
    user.id_card_masked = result.id_card_masked
    user.verified = True
    user.updated_at = datetime.utcnow()
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
