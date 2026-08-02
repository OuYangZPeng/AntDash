"""Runtime configuration for the AntDash backend.

All business tunables (X / Y split ratios, matching time window T, bundle size,
scoring weights, reputation deltas) live here so they can be adjusted centrally
and, at runtime, overridden through the admin settings table.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANTDASH_", env_file=".env", extra="ignore")

    # --- infrastructure ---
    app_name: str = "AntDash"
    app_name_cn: str = "蚂蚁闪达"
    database_url: str = "sqlite:///./antdash.db"
    jwt_secret: str = "dev-secret-change-me-please-use-a-32byte-min-secret"
    jwt_alg: str = "HS256"
    jwt_ttl_minutes: int = 60 * 24 * 7
    media_dir: str = "./media"

    # --- revenue split (percent, 0-100) ---
    # X = errand-fee ratio taken from the rider's per-order income.
    # Y = platform maintenance ratio taken from the Anter's errand fee.
    errand_fee_pct_X: float = 20.0
    platform_fee_pct_Y: float = 10.0

    # --- matching engine ---
    match_window_base_minutes: float = 10.0
    match_window_min_minutes: float = 3.0
    match_window_max_minutes: float = 25.0
    match_target_bundle_size: int = 4
    match_max_bundle_size: int = 6
    # 一个聚合单只聚合同一/相邻楼栋的订单,最多 5 单
    match_max_bundle_size_adjacent: int = 5
    building_adjacency: int = 1                 # 楼栋号差 ≤ 此值视为相邻
    # scoring weights
    w_same_community: float = 0.4
    w_proximity: float = 0.25
    w_time_slack: float = 0.2
    w_bundle_efficiency: float = 0.15

    # --- geo / notifications ---
    # Anters within this radius of a bundle's community get a new-order popup.
    notify_radius_km: float = 1.0
    # Demo convenience: auto-advance freshly-sealed bundles to `at_gate` (simulate
    # the rider gate hand-off) so they immediately appear in the Anter hall.
    auto_gate_on_match: bool = True

    # --- escalation / rescue (临期未接单升级 + 骑手救援) ---
    escalation_enabled: bool = True
    escalation_sweep_seconds: float = 20.0     # 后台巡检间隔
    urgency_start_minutes: float = 20.0        # 剩余 SLA 低于此值开始加急
    urgency_fee_max_ratio: float = 0.6         # 加急费封顶 = 基础包 × 该比例
    rescue_threshold_minutes: float = 15.0     # 剩余 < 15min → 触发骑手救援推送
    escalation_radius_step_km: float = 1.0     # 每升一级扩大的推送半径
    escalation_radius_max_km: float = 3.0
    # 骑手(外卖员)主动救援配送的奖励:
    rider_rescue_bonus_cents: int = 300        # 救援奖金(平台奖金池出资)
    rescue_reputation_bonus: float = 5.0       # 救援信誉加成 → 优先排聚合单

    # --- 骑手提前送达小区门口奖励(越早到,骑手跑腿费越省) ---
    # 折扣 = rider_charge × ratio_max × min(送达时剩余SLA / slack_ref, 1)
    early_gate_discount_ratio_max: float = 0.3    # 最高抵扣骑手跑腿费的 30%
    early_gate_slack_ref_minutes: float = 30.0    # 剩余 SLA ≥ 该值即拿满折扣
    # Fallback location when IP geolocation can't resolve (loopback/emulator).
    default_city: str = "上海市"
    default_lat: float = 31.2304
    default_lng: float = 121.4737

    # --- dynamic pricing (聚合单动态定价) ---
    # Master switch. When off, settlement falls back to the flat total×X% model.
    pricing_enabled: bool = True

    # Per-order base package (effort-based, deterministic), all in cents.
    price_base_start_cents: int = 250          # 起步价 2.5 元/单
    price_free_distance_m: float = 80.0        # 门口→门 免距离加价半径
    price_per_100m_cents: int = 50             # 超出后每 100m 0.5 元
    price_per_floor_cents: int = 60            # 无电梯每层 0.6 元(有电梯不计)
    price_walkup_max_floors: int = 8           # 楼层加价封顶层数
    price_weight_free_grams: int = 3000        # 3kg 内不加重量费
    price_per_kg_over_cents: int = 100         # 每超 1kg 加 1 元
    price_surcharge_fresh_cents: int = 100     # 生鲜品类加价
    price_surcharge_fragile_cents: int = 150   # 易碎/大件品类加价
    price_sla_tight_minutes: float = 15.0      # 剩余 SLA 低于此值视为时效紧张
    price_sla_tight_cents: int = 150           # 时效紧张加价

    # 聚合折扣:成团价 = 各子单基础包之和 × (1 − 该比例)。省下的部分投入当天
    # **应急奖金池**(用于救援等紧急激励)。仅在真正聚合(≥2 单)时生效。
    aggregation_discount_ratio: float = 0.05

    # Floor & cap guardrails.
    price_floor_pct_of_income: float = 20.0    # 保底 = total_income × 该% (对齐 X)
    price_cap_per_order_cents: int = 1500      # 单均封顶 15 元

    # Time-of-day multipliers (local CN time, UTC+8).
    price_peak_multiplier: float = 1.2         # 午/晚高峰
    price_latenight_multiplier: float = 1.15   # 深夜
    price_rider_peak_cap: float = 1.1          # 骑手侧高峰系数封顶(骑手可预期)

    # Weather multipliers (fed by WeatherAdapter).
    price_weather_rain_multiplier: float = 1.15
    price_weather_heavy_rain_multiplier: float = 1.3
    price_weather_snow_multiplier: float = 1.5
    price_weather_extreme_multiplier: float = 1.25   # 高温/大风等

    # Supply-demand surge (per community, with fallback to global when sparse).
    surge_k: float = 0.6                       # 敏感度:surge = 1 + k·(r−1)
    surge_max: float = 1.8
    surge_min_samples: int = 3                 # demand+supply 低于此值回退全局

    # Who bears the volatile premium. Default: platform subsidises surge/weather,
    # rider only pays the deterministic (capped-peak) effort cost.
    rider_bears_surge: bool = False
    rider_bears_weather: bool = False

    # --- reputation engine ---
    reputation_initial: float = 60.0
    reputation_min: float = 0.0
    reputation_max: float = 100.0
    rep_delta_on_time: float = 3.0
    rep_delta_early: float = 1.0
    rep_delta_late: float = -5.0
    rep_delta_abandon: float = -15.0
    rep_delta_complaint: float = -10.0
    rep_ewma_alpha: float = 0.3
    # per-minute passive recovery toward the initial score while idle & compliant
    rep_recovery_per_minute: float = 0.05
    # dispatch weighting: base * sigmoid((S - midpoint) / scale)
    dispatch_base_weight: float = 1.0
    dispatch_sigmoid_midpoint: float = 50.0
    dispatch_sigmoid_scale: float = 10.0
    # below this score the Anter enters a cooldown and receives fewer offers
    dispatch_cooldown_score: float = 35.0
    dispatch_cooldown_minutes: float = 15.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
