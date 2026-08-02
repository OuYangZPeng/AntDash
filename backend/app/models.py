"""Database models (SQLModel) for AntDash.

The schema deliberately keeps platform / payment / identity concerns behind
adapter boundaries; these tables store only what AntDash itself owns.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.utcnow()


class Role(str, Enum):
    rider = "rider"      # 外卖骑手 - drops at community gate
    anter = "anter"      # 末端专职配送员
    admin = "admin"


class Platform(str, Enum):
    meituan = "meituan"   # 美团
    shangou = "shangou"   # 闪购
    jd = "jd"             # 京东


class OrderStatus(str, Enum):
    ingested = "ingested"          # read from platform, awaiting matching
    matched = "matched"            # placed into a bundle
    at_gate = "at_gate"            # rider dropped at community gate (photo uploaded)
    delivered = "delivered"        # Anter completed final leg
    synced = "synced"              # status pushed back to platform
    cancelled = "cancelled"


class BundleStatus(str, Enum):
    open = "open"              # accumulating orders within the time window
    ready = "ready"            # matched & sealed, awaiting gate handoff
    at_gate = "at_gate"        # rider dropped, offered to Anters
    accepted = "accepted"      # an Anter took it (must fulfil)
    delivered = "delivered"    # Anter delivered
    settled = "settled"        # ledger written, platforms synced
    expired = "expired"


class ProofType(str, Enum):
    gate_dropoff = "gate_dropoff"       # rider -> gate
    final_delivery = "final_delivery"   # Anter -> customer door


class LedgerType(str, Enum):
    errand_fee_debit = "errand_fee_debit"   # deducted from rider (确定性 effort 成本)
    anter_credit = "anter_credit"           # paid to Anter (net)
    platform_fee = "platform_fee"           # AntDash maintenance cut
    platform_subsidy = "platform_subsidy"   # platform-funded surge/weather premium
    rescue_bonus = "rescue_bonus"           # bonus-pool reward for rescuing a near-timeout bundle


class OrderCategory(str, Enum):
    normal = "normal"
    fresh = "fresh"       # 生鲜
    fragile = "fragile"   # 易碎/大件


class ReputationReason(str, Enum):
    on_time = "on_time"
    early = "early"
    late = "late"
    abandon = "abandon"
    complaint = "complaint"
    recovery = "recovery"
    rescue = "rescue"       # 主动救援临期单的信誉加成(→优先派单)


class User(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    role: Role = Field(default=Role.anter, index=True)
    phone: Optional[str] = Field(default=None, index=True)
    name: Optional[str] = None
    id_card_masked: Optional[str] = None
    verified: bool = False
    wechat_openid: Optional[str] = Field(default=None, index=True)
    alipay_uid: Optional[str] = Field(default=None, index=True)
    reputation_score: float = 60.0
    on_time_rate: float = 1.0
    cooldown_until: Optional[datetime] = None
    balance_cents: int = 0
    # Comma-separated community ids this Anter serves (empty/None = serves all).
    # Used to compute per-community supply for surge pricing.
    service_community_ids: Optional[str] = None
    # IP-derived location (non-tamperable, resolved server-side). Used for the
    # city display and the 1km new-order notification radius.
    city: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    # How many near-timeout bundles this user has rescued (riders included).
    rescue_count: int = 0
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Order(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    platform: Platform = Field(index=True)
    external_id: str = Field(index=True)
    community_id: str = Field(index=True)
    community_name: str
    address: str
    lat: float
    lng: float
    building_no: int = 0     # 楼栋号(用于同/相邻楼栋聚合)
    rider_id: Optional[str] = Field(default=None, foreign_key="user.id")
    rider_income_cents: int = 0
    # Last-leg effort attributes feeding dynamic pricing.
    floor: int = 1
    has_elevator: bool = True
    weight_grams: int = 500
    category: str = "normal"
    # Deterministic portion of the errand fee this order's rider is charged
    # (frozen at settlement). Rider-visible "本单扣款".
    rider_charge_cents: int = 0
    # Per-sub-order final-delivery photo proof uploaded by the Anter.
    proof_uploaded: bool = False
    # Rider's gate hand-off: when the delivery rider dropped this order at the
    # community gate, and the earliness discount it earned on rider_charge.
    gate_dropoff_at: Optional[datetime] = None
    gate_discount_cents: int = 0
    status: OrderStatus = Field(default=OrderStatus.ingested, index=True)
    bundle_id: Optional[str] = Field(default=None, foreign_key="bundle.id", index=True)
    sla_deadline: datetime
    created_at: datetime = Field(default_factory=utcnow)


class Bundle(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    community_id: str = Field(index=True)
    community_name: str
    status: BundleStatus = Field(default=BundleStatus.open, index=True)
    anter_id: Optional[str] = Field(default=None, foreign_key="user.id", index=True)
    order_count: int = 0
    total_income_cents: int = 0        # sum of rider incomes across orders
    errand_fee_cents: int = 0          # dynamic quoted price P (=跑腿费总额)
    platform_fee_cents: int = 0        # errand_fee * Y%
    anter_net_cents: int = 0           # errand_fee * (1 - Y%)
    # --- dynamic pricing snapshot (frozen at seal) ---
    base_price_cents: int = 0          # P_base (effort-based, deterministic)
    quoted_price_cents: int = 0        # P = clamp(P_base * M_full, floor, cap)
    rider_charge_cents: int = 0        # 骑手承担(确定性 + 封顶高峰)
    subsidy_cents: int = 0             # 平台补贴 = P - rider_charge
    surge_multiplier: float = 1.0
    time_multiplier: float = 1.0
    weather_multiplier: float = 1.0
    weather_condition: str = "clear"
    pricing_breakdown: str = ""        # JSON snapshot for audit / UI
    # --- escalation (临期未接单加急) ---
    urgency_fee_cents: int = 0         # 加急费(平台补贴,随临期递增,accept 时冻结)
    escalation_stage: int = 0          # 0 正常 → 4 已超时
    rescue: bool = False               # 曾进入 <15min 救援态(结算给救援者奖金)
    pool_contribution_cents: int = 0   # 成团 5% 聚合折扣投入应急奖金池的金额
    x_rate: float = 20.0
    y_rate: float = 10.0
    window_deadline: datetime          # when the matching window closes
    accepted_at: Optional[datetime] = None
    delivery_deadline: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class Proof(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    bundle_id: Optional[str] = Field(default=None, foreign_key="bundle.id", index=True)
    order_id: Optional[str] = Field(default=None, foreign_key="order.id", index=True)
    type: ProofType
    image_path: str
    uploaded_by: Optional[str] = Field(default=None, foreign_key="user.id")
    created_at: datetime = Field(default_factory=utcnow)


class LedgerEntry(SQLModel, table=True):
    """Append-only accounting record. Never mutated after creation."""
    id: str = Field(default_factory=_uuid, primary_key=True)
    bundle_id: str = Field(foreign_key="bundle.id", index=True)
    type: LedgerType = Field(index=True)
    account_id: Optional[str] = Field(default=None, foreign_key="user.id", index=True)
    amount_cents: int = 0   # signed: negative = debit, positive = credit
    memo: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class PriceQuote(SQLModel, table=True):
    """Immutable snapshot of a bundle's dynamic-pricing computation (audit)."""
    id: str = Field(default_factory=_uuid, primary_key=True)
    bundle_id: str = Field(foreign_key="bundle.id", index=True)
    base_price_cents: int = 0
    quoted_price_cents: int = 0
    rider_charge_cents: int = 0
    subsidy_cents: int = 0
    platform_fee_cents: int = 0
    anter_net_cents: int = 0
    surge_multiplier: float = 1.0
    time_multiplier: float = 1.0
    weather_multiplier: float = 1.0
    weather_condition: str = "clear"
    demand: int = 0
    supply: int = 0
    surge_scope: str = "community"   # community | global (fallback)
    floor_cents: int = 0
    cap_cents: int = 0
    breakdown: str = ""              # JSON detail
    created_at: datetime = Field(default_factory=utcnow)


class EmergencyPoolEntry(SQLModel, table=True):
    """Daily 应急奖金池 ledger: +contributions (5% aggregation savings) and
    −payouts (rescue bonuses / emergency incentives). Append-only."""
    id: str = Field(default_factory=_uuid, primary_key=True)
    day: str = Field(index=True)          # YYYY-MM-DD (UTC)
    amount_cents: int = 0                 # signed: + contribution, − payout
    kind: str = "contribution"            # contribution | rescue_payout
    bundle_id: Optional[str] = Field(default=None, foreign_key="bundle.id", index=True)
    memo: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class ReputationEvent(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    anter_id: str = Field(foreign_key="user.id", index=True)
    reason: ReputationReason
    delta: float = 0.0
    score_after: float = 0.0
    on_time_rate_after: float = 1.0
    memo: str = ""
    created_at: datetime = Field(default_factory=utcnow)


class PaymentMethod(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    user_id: str = Field(foreign_key="user.id", index=True)
    kind: str  # wechat | alipay | bank_card
    display: str  # masked display, e.g. "**** 8888"
    token: str    # opaque token from the (mock) payment adapter
    is_default: bool = False
    created_at: datetime = Field(default_factory=utcnow)
