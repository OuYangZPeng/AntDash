"""Mock weather adapter.

Returns a process-wide, settable condition so demos/tests are deterministic and
the admin can simulate rain/snow to see surge pricing kick in. Swap in a real
和风/彩云天气 client later without touching pricing logic.
"""
from __future__ import annotations

from .base import WeatherAdapter, WeatherInfo

_CONDITION_INTENSITY = {
    "clear": 0.0,
    "rain": 0.4,
    "heavy_rain": 0.7,
    "snow": 0.9,
    "extreme": 0.8,
}


class MockWeatherAdapter(WeatherAdapter):
    def __init__(self, condition: str = "clear", temp_c: float = 22.0) -> None:
        self.condition = condition
        self.temp_c = temp_c

    def set_condition(self, condition: str, temp_c: float | None = None) -> None:
        if condition not in _CONDITION_INTENSITY:
            raise ValueError(f"unknown weather condition: {condition}")
        self.condition = condition
        if temp_c is not None:
            self.temp_c = temp_c

    def current(self, lat: float, lng: float) -> WeatherInfo:
        return WeatherInfo(
            condition=self.condition,
            intensity=_CONDITION_INTENSITY.get(self.condition, 0.0),
            temp_c=self.temp_c,
        )


_WEATHER_ADAPTER: MockWeatherAdapter | None = None


def get_weather_adapter() -> MockWeatherAdapter:
    global _WEATHER_ADAPTER
    if _WEATHER_ADAPTER is None:
        _WEATHER_ADAPTER = MockWeatherAdapter()
    return _WEATHER_ADAPTER
