"""IP geolocation endpoint.

The city/coordinate is resolved server-side from the request IP, so the client
cannot tamper with it. Result is persisted onto the user for the 1km new-order
notification radius.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlmodel import Session

from ..adapters import get_geo_adapter
from ..database import get_session
from ..models import User
from .deps import get_current_user

router = APIRouter(prefix="/geo", tags=["geo"])


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else ""


@router.get("/locate")
def locate(
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
):
    ip = _client_ip(request)
    loc = get_geo_adapter().locate(ip)
    # Persist the IP-derived location (non-tamperable) onto the user.
    user.city = loc.city
    user.lat = loc.lat
    user.lng = loc.lng
    session.add(user)
    session.commit()
    return {
        "city": loc.city,
        "lat": loc.lat,
        "lng": loc.lng,
        "source": loc.source,  # 'ip' or 'fallback'
        "editable": False,
    }
