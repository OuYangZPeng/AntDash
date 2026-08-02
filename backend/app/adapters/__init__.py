"""Pluggable adapters for external dependencies.

Everything AntDash does not own (platform order feeds, payments, real-name
identity verification) sits behind an abstract interface here. The MVP ships
mock implementations; swapping in real integrations later only requires a new
implementation of the same interface -- core business logic is untouched.
"""
from .base import (
    GeoAdapter,
    GeoLocation,
    IdentityAdapter,
    MapAdapter,
    PaymentAdapter,
    PlatformAdapter,
    WeatherAdapter,
    WeatherInfo,
)
from .geo_mock import MockGeoAdapter, get_geo_adapter
from .identity_mock import MockIdentityAdapter
from .map_mock import MockMapAdapter, get_map_adapter
from .payment_mock import MockPaymentAdapter
from .platform_mock import MockPlatformAdapter, get_platform_adapters
from .weather_mock import MockWeatherAdapter, get_weather_adapter

__all__ = [
    "PlatformAdapter",
    "PaymentAdapter",
    "IdentityAdapter",
    "MapAdapter",
    "WeatherAdapter",
    "WeatherInfo",
    "GeoAdapter",
    "GeoLocation",
    "MockPlatformAdapter",
    "MockPaymentAdapter",
    "MockIdentityAdapter",
    "MockMapAdapter",
    "MockWeatherAdapter",
    "MockGeoAdapter",
    "get_platform_adapters",
    "get_map_adapter",
    "get_weather_adapter",
    "get_geo_adapter",
]
