"""WebSocket endpoint for real-time new-order notifications to nearby Anters."""
from __future__ import annotations

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlmodel import Session

from ..adapters import get_geo_adapter
from ..database import engine
from ..models import User
from ..services import auth as auth_service
from ..services.notifications import get_hub

router = APIRouter()


@router.websocket("/ws/notifications")
async def notifications_ws(websocket: WebSocket, token: str = Query(...)):
    # Authenticate via token query param (WebSocket can't use Authorization easily).
    try:
        payload = auth_service.decode_token(token)
    except Exception:  # noqa: BLE001
        await websocket.close(code=1008)
        return
    user_id = payload.get("sub")

    # Resolve the Anter's location: prefer stored IP-derived location, else
    # resolve from the socket's client IP now.
    lat = lng = None
    role = "anter"
    with Session(engine) as session:
        user = session.get(User, user_id)
        if user is not None:
            lat, lng = user.lat, user.lng
            role = user.role.value if hasattr(user.role, "value") else user.role
    if lat is None or lng is None:
        ip = websocket.client.host if websocket.client else ""
        loc = get_geo_adapter().locate(ip)
        lat, lng = loc.lat, loc.lng

    await websocket.accept()
    hub = get_hub()
    cid, queue = hub.register(user_id, lat, lng, role)
    try:
        await websocket.send_json({"type": "connected", "lat": lat, "lng": lng})
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        hub.unregister(cid)
