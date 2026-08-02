"""Mock IP-geolocation adapter.

Resolves a client IP to a city + coordinate. Loopback/private IPs (localhost,
simulators, LAN) fall back to the configured default city near the demo
communities so the 1km notification radius is demonstrable. Swap in a real
高德/百度 IP 定位 client later without touching business logic.

The location is always derived server-side from the request IP, so the client
cannot tamper with it.
"""
from __future__ import annotations

import ipaddress

from ..config import get_settings
from .base import GeoAdapter, GeoLocation

# A few well-known public IP ranges mapped to cities, purely for demo variety.
_DEMO_CITY_BY_PREFIX = {
    "116.": ("北京市", 39.9042, 116.4074),
    "180.": ("广州市", 23.1291, 113.2644),
    "101.": ("深圳市", 22.5431, 114.0579),
}


def _is_local(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_loopback or addr.is_private or addr.is_link_local
    except ValueError:
        return True


class MockGeoAdapter(GeoAdapter):
    def locate(self, ip: str) -> GeoLocation:
        s = get_settings()
        if not ip or _is_local(ip):
            return GeoLocation(
                city=s.default_city, lat=s.default_lat, lng=s.default_lng,
                source="fallback", ip=ip,
            )
        for prefix, (city, lat, lng) in _DEMO_CITY_BY_PREFIX.items():
            if ip.startswith(prefix):
                return GeoLocation(city=city, lat=lat, lng=lng, source="ip", ip=ip)
        # Unknown public IP -> default city (a real adapter would query the API).
        return GeoLocation(
            city=s.default_city, lat=s.default_lat, lng=s.default_lng,
            source="ip", ip=ip,
        )


_GEO_ADAPTER: MockGeoAdapter | None = None


def get_geo_adapter() -> MockGeoAdapter:
    global _GEO_ADAPTER
    if _GEO_ADAPTER is None:
        _GEO_ADAPTER = MockGeoAdapter()
    return _GEO_ADAPTER
