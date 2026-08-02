"""Request/response schemas for the API layer."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from .models import Role


# --- auth ---
class PhoneLoginRequest(BaseModel):
    phone: str
    otp: str = "0000"  # mock OTP
    role: Role = Role.anter


class OAuthLoginRequest(BaseModel):
    code: str  # mock auth code from WeChat/Alipay
    role: Role = Role.anter


class RealNameRequest(BaseModel):
    name: str
    id_card: str


class TokenResponse(BaseModel):
    token: str
    user_id: str
    role: Role
    verified: bool


class UserOut(BaseModel):
    id: str
    role: Role
    phone: Optional[str] = None
    name: Optional[str] = None
    verified: bool
    reputation_score: float
    on_time_rate: float
    balance_cents: int
    rescue_count: int = 0


# --- orders / bundles ---
class OrderOut(BaseModel):
    id: str
    platform: str
    external_id: str
    community_name: str
    address: str
    rider_income_cents: int
    status: str
    sla_deadline: datetime
    floor: int = 1
    has_elevator: bool = True
    category: str = "normal"
    proof_uploaded: bool = False
    gate_dropoff_at: Optional[datetime] = None
    gate_discount_cents: int = 0
    # 本单骑手扣款(rider-visible). None when hidden for the viewer role.
    rider_charge_cents: Optional[int] = None


class BundleOut(BaseModel):
    id: str
    community_name: str
    status: str
    anter_id: Optional[str] = None
    order_count: int
    total_income_cents: int
    errand_fee_cents: int
    platform_fee_cents: int
    anter_net_cents: int
    x_rate: float
    y_rate: float
    window_deadline: datetime
    delivery_deadline: Optional[datetime] = None
    orders: List[OrderOut] = []
    # --- dynamic pricing (role-scoped visibility) ---
    base_price_cents: Optional[int] = None
    quoted_price_cents: Optional[int] = None
    rider_charge_cents: Optional[int] = None      # rider-visible aggregate deduction
    subsidy_cents: Optional[int] = None           # anter/admin only
    surge_multiplier: Optional[float] = None
    time_multiplier: Optional[float] = None
    weather_multiplier: Optional[float] = None
    weather_condition: Optional[str] = None
    pricing_breakdown: Optional[str] = None       # anter/admin only
    # escalation / rescue
    urgency_fee_cents: int = 0
    escalation_stage: int = 0
    rescue: bool = False


# --- payment ---
class BindPaymentRequest(BaseModel):
    kind: str  # wechat | alipay | bank_card
    credential: str
    display: str = ""


class PaymentMethodOut(BaseModel):
    id: str
    kind: str
    display: str
    is_default: bool


# --- admin config ---
class ConfigUpdate(BaseModel):
    errand_fee_pct_X: Optional[float] = None
    platform_fee_pct_Y: Optional[float] = None
    match_window_base_minutes: Optional[float] = None
    match_max_bundle_size: Optional[int] = None
    # dynamic pricing knobs
    pricing_enabled: Optional[bool] = None
    surge_k: Optional[float] = None
    surge_max: Optional[float] = None
    price_base_start_cents: Optional[int] = None
    price_cap_per_order_cents: Optional[int] = None
    rider_bears_surge: Optional[bool] = None
    rider_bears_weather: Optional[bool] = None


class SplitPreview(BaseModel):
    total_income_cents: int
    errand_fee_cents: int
    platform_fee_cents: int
    anter_net_cents: int
    x_rate: float
    y_rate: float


class PricePreview(BaseModel):
    base_price_cents: int
    time_multiplier: float
    weather_multiplier: float
    surge_multiplier: float
    full_multiplier: float
    quoted_price_cents: int
    rider_charge_cents: int
    subsidy_cents: int
    platform_fee_cents: int
    anter_net_cents: int
    floor_cents: int
    cap_cents: int
    weather_condition: str
