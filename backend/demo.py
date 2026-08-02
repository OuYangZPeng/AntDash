"""Narrated end-to-end walkthrough of the AntDash business flow.

Runs entirely in-process against a fresh temp database (no server needed):

    python demo.py

Steps: login (rider + Anter) -> real-name -> ingest platform orders ->
match into community bundles -> rider drops at gate -> Anter accepts ->
Anter delivers -> settlement (split ledger) -> reputation update.
"""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "ANTDASH_DATABASE_URL", f"sqlite:///{os.path.join(tempfile.mkdtemp(), 'demo.db')}"
)
os.environ.setdefault("ANTDASH_MEDIA_DIR", os.path.join(tempfile.mkdtemp(), "media"))

from sqlmodel import Session, select  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import engine, init_db  # noqa: E402
from app.adapters import (  # noqa: E402
    MockPaymentAdapter,
    get_platform_adapters,
    get_weather_adapter,
)
from app.models import Bundle, BundleStatus, Order, Platform, Role, User  # noqa: E402
from app.services import auth as auth_service  # noqa: E402
from app.services import dispatch as dispatch_service  # noqa: E402
from app.services import pricing as pricing_service  # noqa: E402
from app.services.matching import run_matching  # noqa: E402
from app.services.reputation import dispatch_weight  # noqa: E402


def money(cents: int) -> str:
    return f"¥{cents / 100:.2f}"


def step(n, title):
    print(f"\n\033[1m[{n}] {title}\033[0m")


def main() -> None:
    settings = get_settings()
    init_db()
    payment = MockPaymentAdapter()

    with Session(engine) as s:
        step(1, "登录并实名 (骑手 + Anter)")
        rider = auth_service.login_phone(s, "13900000002", role=Role.rider)
        auth_service.verify_real_name(s, rider, "李骑手", "310101199001011234")
        anter = auth_service.login_phone(s, "13800000001", role=Role.anter)
        auth_service.verify_real_name(s, anter, "王小蚂", "11010119900307051X")
        print(f"  骑手 {rider.name} 已实名; Anter {anter.name} 已实名 (信誉 {anter.reputation_score:.0f})")

        step(2, "接入三大平台订单 (mock)")
        adapters = get_platform_adapters()
        count = 0
        for adapter in adapters.values():
            for eo in adapter.fetch_orders(limit=6):
                s.add(Order(
                    platform=Platform(eo.platform), external_id=eo.external_id,
                    community_id=eo.community_id, community_name=eo.community_name,
                    address=eo.address, lat=eo.lat, lng=eo.lng,
                    rider_income_cents=eo.rider_income_cents, rider_id=rider.id,
                    sla_deadline=eo.sla_deadline,
                    floor=eo.floor, has_elevator=eo.has_elevator,
                    weight_grams=eo.weight_grams, category=eo.category,
                    building_no=eo.building_no,
                ))
                count += 1
        s.commit()
        print(f"  从 美团/闪购/京东 共接入 {count} 笔订单")

        # simulate bad weather so surge/weather pricing is visible in the demo
        get_weather_adapter().set_condition("rain")

        step(3, "撮合引擎:同小区聚合成团 + 动态定价")
        run_matching(s)
        # force-seal any still-open bundles for the demo, freezing a price snapshot
        for b in s.exec(select(Bundle).where(Bundle.status == BundleStatus.open)).all():
            if b.order_count:
                b.status = BundleStatus.ready
                s.add(b)
                bd = pricing_service.compute_bundle_quote(s, b, settings)
                pricing_service.freeze_quote_onto_bundle(s, b, bd)
        s.commit()
        ready = s.exec(select(Bundle).where(Bundle.status == BundleStatus.ready)).all()
        for b in ready:
            print(f"  聚合单 {b.community_name}: {b.order_count} 单, 总额 {money(b.total_income_cents)}")
        if not ready:
            print("  (本次未成团)")
            return
        bundle = max(ready, key=lambda b: b.order_count)

        step(4, "骑手送到小区门口并拍照上传")
        dispatch_service.mark_bundle_at_gate(s, bundle)
        print(f"  聚合单 {bundle.community_name} 已到门口, 开放给附近 Anter")

        step(5, "派单排序 (按信誉分权重)")
        for a in dispatch_service.rank_anters(s):
            print(f"  Anter {a.name}: 信誉 {a.reputation_score:.0f}, 派单权重 {dispatch_weight(a.reputation_score, settings):.3f}")

        step(6, "Anter 接单 (接单后必须履约)")
        dispatch_service.accept_bundle(s, bundle, anter)
        print(f"  {anter.name} 已接单, 履约截止 {bundle.delivery_deadline}")

        step(7, "Anter 送达并拍照回写各平台")
        before = anter.reputation_score
        dispatch_service.deliver_bundle(s, bundle, payment)
        s.refresh(bundle)
        s.refresh(anter)

        step(8, "动态定价分账结算")
        y = bundle.y_rate
        print(f"  订单总额(骑手收入) : {money(bundle.total_income_cents)}")
        print(f"  基础包 P_base(effort) : {money(bundle.base_price_cents)}")
        print(
            f"  动态系数: 时段 ×{bundle.time_multiplier:.2f}  天气({bundle.weather_condition}) "
            f"×{bundle.weather_multiplier:.2f}  供需 surge ×{bundle.surge_multiplier:.2f}"
        )
        print(f"  聚合单价 P(跑腿费) = {money(bundle.quoted_price_cents)}")
        print(f"    ├─ 骑手扣款(确定性)  = {money(bundle.rider_charge_cents)}  (从骑手账户扣除)")
        print(f"    └─ 平台补贴(高峰/天气) = {money(bundle.subsidy_cents)}")
        print(f"  平台维护费 = P × {y:.0f}% = {money(bundle.platform_fee_cents)}")
        print(f"  Anter 实收 = P × (1-{y:.0f}%) = {money(bundle.anter_net_cents)}")

        step(9, "信誉更新 & 平台状态回写")
        print(f"  {anter.name} 信誉分 {before:.0f} -> {anter.reputation_score:.0f}, 准时率 {anter.on_time_rate:.2f}")
        for key, adapter in adapters.items():
            if adapter.status_log:
                print(f"  已回写 {key}: {len(adapter.status_log)} 条订单状态")

        print("\n\033[1m演示完成 ✔\033[0m")


if __name__ == "__main__":
    main()
