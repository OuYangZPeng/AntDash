"""Abstract adapter interfaces.

Replace the mock implementations with real SDK-backed ones (Meituan Open
Platform, JD Logistics, WeChat Pay, Alipay, a real-name KYC provider, etc.)
without touching the services that depend on these interfaces.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class ExternalOrder:
    platform: str
    external_id: str
    community_id: str
    community_name: str
    address: str
    lat: float
    lng: float
    rider_income_cents: int
    sla_deadline: datetime
    floor: int = 1
    has_elevator: bool = True
    weight_grams: int = 500
    category: str = "normal"    # normal | fresh | fragile
    building_no: int = 0        # 楼栋号(同/相邻楼栋聚合用)


@dataclass
class PaymentResult:
    ok: bool
    transaction_id: str
    kind: str
    amount_cents: int
    message: str = ""


@dataclass
class IdentityResult:
    ok: bool
    name: str
    id_card_masked: str
    message: str = ""


@dataclass
class WeatherInfo:
    """Current weather at a location, feeding the pricing weather multiplier."""
    condition: str      # clear | rain | heavy_rain | snow | extreme
    intensity: float    # 0..1 informational severity
    temp_c: float = 20.0
    message: str = ""


@dataclass
class GeoLocation:
    """IP-derived location. Resolved server-side so it can't be spoofed by the client."""
    city: str
    lat: float
    lng: float
    source: str = "ip"  # ip | fallback
    ip: str = ""


class PlatformAdapter(ABC):
    """Reads orders from and pushes status back to a delivery platform."""

    name: str

    @abstractmethod
    def fetch_orders(self, limit: int = 20) -> List[ExternalOrder]:
        ...

    @abstractmethod
    def push_status(self, external_id: str, status: str, proof_url: Optional[str] = None) -> bool:
        ...


class PaymentAdapter(ABC):
    """Bind payment methods, move errand fees, pay out Anters."""

    @abstractmethod
    def bind_method(self, kind: str, credential: str) -> PaymentResult:
        ...

    @abstractmethod
    def charge(self, token: str, amount_cents: int, memo: str = "") -> PaymentResult:
        ...

    @abstractmethod
    def payout(self, token: str, amount_cents: int, memo: str = "") -> PaymentResult:
        ...


class IdentityAdapter(ABC):
    """Real-name (实名) verification."""

    @abstractmethod
    def verify(self, name: str, id_card: str) -> IdentityResult:
        ...


class MapAdapter(ABC):
    """Geocoding + on-foot distance/ETA. Replace mock with 高德/百度地图 SDK."""

    @abstractmethod
    def geocode(self, address: str) -> tuple[float, float]:
        """address -> (lat, lng)."""
        ...

    @abstractmethod
    def walking_distance_m(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """On-foot distance in metres between two points."""
        ...

    @abstractmethod
    def walking_eta_minutes(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        ...


class WeatherAdapter(ABC):
    """Current weather lookup. Replace mock with 和风/彩云天气 SDK."""

    @abstractmethod
    def current(self, lat: float, lng: float) -> WeatherInfo:
        ...


class GeoAdapter(ABC):
    """IP -> city/coordinate. Replace mock with 高德/百度 IP 定位 SDK."""

    @abstractmethod
    def locate(self, ip: str) -> GeoLocation:
        ...
