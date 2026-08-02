from app.config import get_settings
from app.services.pricing import (
    OrderPriceInput,
    aggregate_base,
    early_gate_discount,
    order_base_package,
    quote,
    surge_multiplier,
    time_multiplier,
    weather_multiplier,
)

S = get_settings()


def _order(**kw):
    base = dict(
        order_id="o1", distance_m=0.0, floor=1, has_elevator=True,
        weight_grams=500, category="normal", sla_minutes=60.0, rider_income_cents=1000,
    )
    base.update(kw)
    return OrderPriceInput(**base)


def test_base_package_start_only():
    # within free distance, low floor w/ elevator, light, normal, loose SLA
    assert order_base_package(_order(), S) == S.price_base_start_cents


def test_base_package_distance_surcharge():
    near = order_base_package(_order(distance_m=50), S)
    far = order_base_package(_order(distance_m=580), S)  # 500m beyond free radius
    assert far > near


def test_base_package_walkup_floor():
    elevator = order_base_package(_order(floor=10, has_elevator=True), S)
    walkup = order_base_package(_order(floor=10, has_elevator=False), S)
    assert walkup > elevator


def test_base_package_weight_and_category():
    heavy = order_base_package(_order(weight_grams=8000), S)
    light = order_base_package(_order(weight_grams=500), S)
    fresh = order_base_package(_order(category="fresh"), S)
    fragile = order_base_package(_order(category="fragile"), S)
    assert heavy > light
    assert fresh > light and fragile > fresh


def test_base_package_sla_tight():
    tight = order_base_package(_order(sla_minutes=5), S)
    loose = order_base_package(_order(sla_minutes=60), S)
    assert tight > loose


def test_aggregate_base_discount_funds_pool():
    # single order: no aggregation discount
    p1, pool1 = aggregate_base(1000, 1, S)
    assert p1 == 1000 and pool1 == 0
    # real bundle: flat 5% off the sum, and the 5% goes to the pool
    p2, pool2 = aggregate_base(1000, 3, S)
    assert p2 == round(1000 * (1 - S.aggregation_discount_ratio))
    assert pool2 == 1000 - p2
    assert p2 + pool2 == 1000  # conserved: bundle price + pool = sum of sub-orders
    # discount is a flat ratio, independent of order count (非线性于单数)
    p3, _ = aggregate_base(1000, 5, S)
    assert p3 == p2


def test_time_multiplier_windows():
    assert time_multiplier(18, S) == S.price_peak_multiplier    # dinner
    assert time_multiplier(12, S) == S.price_peak_multiplier    # lunch
    assert time_multiplier(3, S) == S.price_latenight_multiplier
    assert time_multiplier(15, S) == 1.0


def test_weather_multiplier():
    assert weather_multiplier("clear", S) == 1.0
    assert weather_multiplier("snow", S) > weather_multiplier("rain", S)


def test_surge_clamped_and_monotonic():
    assert surge_multiplier(1, 10, S) == 1.0            # oversupply -> no surge
    assert surge_multiplier(10, 1, S) == S.surge_max    # scarce -> capped
    assert surge_multiplier(3, 2, S) > surge_multiplier(2, 2, S)


def test_quote_conservation_and_split():
    orders = [_order(order_id=f"o{i}", distance_m=150, floor=6) for i in range(4)]
    bd = quote(
        orders, local_hour=18, weather_condition="rain", demand=3, supply=2,
        total_income_cents=4000, y_pct=10.0, settings=S,
    )
    # platform_fee + anter_net == P
    assert bd.platform_fee_cents + bd.anter_net_cents == bd.quoted_price_cents
    # rider never overcharged beyond total price; subsidy fills the gap
    assert bd.rider_charge_cents <= bd.quoted_price_cents
    assert bd.subsidy_cents == bd.quoted_price_cents - bd.rider_charge_cents
    # per-order rider charges sum exactly to the aggregate (no cents lost)
    assert sum(bd.order_rider_charge_cents.values()) == bd.rider_charge_cents


def test_quote_floor_applies():
    # tiny effort but decent income -> floor (income × X%) lifts the price above
    # the bare base package. (income chosen so floor stays below the per-order cap)
    orders = [_order(distance_m=0)]
    bd = quote(
        orders, local_hour=15, weather_condition="clear", demand=1, supply=5,
        total_income_cents=5000, y_pct=10.0, settings=S,
    )
    assert bd.floor_cents <= bd.cap_cents            # guardrails not in conflict here
    assert bd.quoted_price_cents == bd.floor_cents   # base(250) < floor(1000) -> lifted
    assert bd.quoted_price_cents > bd.base_price_cents


def test_quote_cap_applies():
    orders = [_order(order_id=f"o{i}", distance_m=5000, floor=24, has_elevator=False,
                     weight_grams=10000, category="fragile", sla_minutes=1) for i in range(2)]
    bd = quote(
        orders, local_hour=18, weather_condition="snow", demand=20, supply=1,
        total_income_cents=100, y_pct=10.0, settings=S,
    )
    assert bd.quoted_price_cents <= bd.cap_cents


def test_early_gate_discount_rewards_earliness():
    # no slack -> no discount; more slack -> bigger; capped at ratio_max
    assert early_gate_discount(1000, 0, S) == 0
    small = early_gate_discount(1000, 5, S)
    big = early_gate_discount(1000, S.early_gate_slack_ref_minutes, S)
    assert 0 < small < big
    assert big == int(round(1000 * S.early_gate_discount_ratio_max))
    # beyond the reference slack it stays capped
    assert early_gate_discount(1000, S.early_gate_slack_ref_minutes * 3, S) == big


def test_platform_absorbs_surge_by_default():
    # with default config (rider_bears_surge/weather = False), a surge/weather
    # spike must raise subsidy, not the rider charge.
    common = dict(local_hour=15, total_income_cents=4000, y_pct=10.0, settings=S)
    orders = [_order(order_id=f"o{i}", distance_m=150) for i in range(4)]
    calm = quote(orders, weather_condition="clear", demand=1, supply=5, **common)
    storm = quote(orders, weather_condition="snow", demand=10, supply=1, **common)
    assert storm.quoted_price_cents > calm.quoted_price_cents
    assert storm.rider_charge_cents == calm.rider_charge_cents      # rider shielded
    assert storm.subsidy_cents > calm.subsidy_cents                 # platform funds it
