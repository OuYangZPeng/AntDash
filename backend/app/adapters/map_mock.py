"""Mock map adapter.

Approximates on-foot distance with the haversine great-circle distance scaled
by a detour factor (real streets/paths are longer than a straight line). Swap in
高德/百度地图 walking-route APIs later without touching pricing logic.
"""
from __future__ import annotations

import math

from .base import MapAdapter

# Straight-line -> walking-path detour factor and pedestrian speed.
_DETOUR_FACTOR = 1.3
_WALK_SPEED_M_PER_MIN = 80.0


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0  # metres
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class MockMapAdapter(MapAdapter):
    def geocode(self, address: str) -> tuple[float, float]:
        # Deterministic pseudo-coordinate around central Shanghai for demo/testing.
        h = abs(hash(address))
        lat = 31.2304 + (h % 1000) / 1_000_000.0
        lng = 121.4737 + ((h // 1000) % 1000) / 1_000_000.0
        return (lat, lng)

    def walking_distance_m(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        return _haversine_m(lat1, lng1, lat2, lng2) * _DETOUR_FACTOR

    def walking_eta_minutes(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        return self.walking_distance_m(lat1, lng1, lat2, lng2) / _WALK_SPEED_M_PER_MIN


_MAP_ADAPTER: MockMapAdapter | None = None


def get_map_adapter() -> MockMapAdapter:
    global _MAP_ADAPTER
    if _MAP_ADAPTER is None:
        _MAP_ADAPTER = MockMapAdapter()
    return _MAP_ADAPTER
