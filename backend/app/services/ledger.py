"""Revenue split (分账) engine.

Given the rider's total income for the bundled orders:
    errand_fee = total_income * X%          (deducted from the rider)
    platform_fee = errand_fee * Y%          (AntDash maintenance cut)
    anter_net   = errand_fee * (1 - Y%)     (paid to the Anter)

Example: 4 orders totalling 40 元, X=20%, Y=10%
    errand_fee = 40 * 20% = 8 元
    platform_fee = 8 * 10% = 0.8 元
    anter_net = 8 * (1 - 10%) = 7.2 元
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Split:
    total_income_cents: int
    errand_fee_cents: int
    platform_fee_cents: int
    anter_net_cents: int
    x_rate: float
    y_rate: float


def split_from_errand_fee(errand_fee_cents: int, y_pct: float) -> Split:
    """Split a *given* errand fee (e.g. the dynamic quoted price P) by Y%.

    Used by dynamic pricing where P is computed by the pricing engine rather
    than as total_income × X%.
    """
    if errand_fee_cents < 0:
        raise ValueError("errand_fee_cents must be non-negative")
    if not (0 <= y_pct <= 100):
        raise ValueError("y_pct must be within [0, 100]")
    platform_fee = round(errand_fee_cents * y_pct / 100.0)
    anter_net = errand_fee_cents - platform_fee
    return Split(
        total_income_cents=errand_fee_cents,
        errand_fee_cents=int(errand_fee_cents),
        platform_fee_cents=int(platform_fee),
        anter_net_cents=int(anter_net),
        x_rate=0.0,
        y_rate=y_pct,
    )


def compute_split(total_income_cents: int, x_pct: float, y_pct: float) -> Split:
    """Pure split computation. Rounds to whole cents (banker-safe via round())."""
    if total_income_cents < 0:
        raise ValueError("total_income_cents must be non-negative")
    if not (0 <= x_pct <= 100) or not (0 <= y_pct <= 100):
        raise ValueError("x_pct and y_pct must be within [0, 100]")

    errand_fee = round(total_income_cents * x_pct / 100.0)
    platform_fee = round(errand_fee * y_pct / 100.0)
    anter_net = errand_fee - platform_fee
    return Split(
        total_income_cents=total_income_cents,
        errand_fee_cents=int(errand_fee),
        platform_fee_cents=int(platform_fee),
        anter_net_cents=int(anter_net),
        x_rate=x_pct,
        y_rate=y_pct,
    )
