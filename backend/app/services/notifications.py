"""In-memory real-time notification hub (WebSocket fan-out).

Anters open a WebSocket and register their (IP-derived) location. When new
bundles form nearby, `publish_new_bundle` fans the event out only to Anters
within `notify_radius_km`. Publishing is thread-safe so it can be called from
sync FastAPI endpoints (which run in a worker thread) while the WebSocket
handlers live on the event loop.
"""
from __future__ import annotations

import asyncio
import math
from typing import Dict, Optional


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class NotificationHub:
    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._clients: Dict[int, dict] = {}
        self._counter = 0

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def register(self, user_id: str, lat: Optional[float], lng: Optional[float], role: str = "anter"):
        self._counter += 1
        cid = self._counter
        queue: asyncio.Queue = asyncio.Queue()
        self._clients[cid] = {
            "q": queue, "user_id": user_id, "lat": lat, "lng": lng, "role": role,
        }
        return cid, queue

    def unregister(self, cid: int) -> None:
        self._clients.pop(cid, None)

    def online_count(self) -> int:
        return len(self._clients)

    def publish_new_bundle(
        self,
        event: dict,
        lat: float,
        lng: float,
        radius_km: float,
        roles: Optional[set] = None,
    ) -> int:
        """Fan `event` out to clients within radius_km (optionally role-filtered).

        Returns #recipients. Safe to call from a sync (threadpool) context.
        """
        loop = self._loop
        if loop is None:
            return 0
        sent = 0
        for client in list(self._clients.values()):
            clat, clng = client["lat"], client["lng"]
            if clat is None or clng is None:
                continue
            if roles is not None and client.get("role") not in roles:
                continue
            dist = haversine_km(clat, clng, lat, lng)
            if dist <= radius_km:
                payload = {**event, "distance_km": round(dist, 3)}
                loop.call_soon_threadsafe(client["q"].put_nowait, payload)
                sent += 1
        return sent


hub = NotificationHub()


def get_hub() -> NotificationHub:
    return hub
