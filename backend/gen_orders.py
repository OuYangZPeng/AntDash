"""Random order generator to stress-test the aggregation (撮合) algorithm.

Fires batches of synthetic orders at a running AntDash backend and reports how
well they aggregate into community bundles (avg/max size, aggregation rate,
per-community & per-status breakdown). Fewer `--communities` => denser
aggregation; more rounds/interval simulates a real arrival stream.

Usage (backend must be running, e.g. `bash run.sh`):
    python gen_orders.py                          # 1 round, 20 orders, 5 communities
    python gen_orders.py --count 40 --rounds 5 --interval 3 --communities 2
    python gen_orders.py --url http://127.0.0.1:8090 --seed 42
"""
from __future__ import annotations

import argparse
import sys
import time

import httpx


def _bar(rate: float, width: int = 20) -> str:
    filled = int(round(rate * width))
    return "█" * filled + "·" * (width - filled)


def run() -> int:
    ap = argparse.ArgumentParser(description="AntDash 订单生成 / 聚合测试工具")
    ap.add_argument("--url", default="http://127.0.0.1:8080", help="backend base URL")
    ap.add_argument("--count", type=int, default=20, help="每轮生成订单数")
    ap.add_argument("--rounds", type=int, default=1, help="轮数")
    ap.add_argument("--interval", type=float, default=0.0, help="每轮间隔秒数")
    ap.add_argument("--communities", type=int, default=5, choices=range(1, 6),
                    help="订单分布的小区数(越少聚合越密)")
    ap.add_argument("--seed", type=int, default=None, help="随机种子(可复现)")
    args = ap.parse_args()

    stats = None
    with httpx.Client(base_url=args.url, timeout=30.0) as client:
        try:
            client.get("/health")
        except httpx.HTTPError as e:
            print(f"✗ 无法连接后端 {args.url} — 请先启动服务 (bash run.sh)。\n  {e}")
            return 1

        for r in range(1, args.rounds + 1):
            params = {"count": args.count, "communities": args.communities}
            if args.seed is not None:
                params["seed"] = args.seed + r  # vary per round but reproducible
            resp = client.post("/orders/simulate", params=params)
            resp.raise_for_status()
            data = resp.json()
            stats = data["stats"]
            print(
                f"[轮 {r}/{args.rounds}] 生成 {data['generated']} 单 → "
                f"本轮成团 {data['bundles_ready_this_round']} 个 · "
                f"推送附近 Anter {data.get('anters_notified', 0)} 人"
            )
            if r < args.rounds and args.interval > 0:
                time.sleep(args.interval)

    if not stats:
        return 1

    print("\n" + "=" * 46)
    print("  聚合算法测试报告 (累计)")
    print("=" * 46)
    print(f"  订单总数         : {stats['total_orders']}")
    print(f"  聚合单总数       : {stats['total_bundles']}")
    print(f"  平均每团单数     : {stats['avg_bundle_size']}")
    print(f"  最大团单数       : {stats['max_bundle_size']}")
    rate = stats["aggregated_order_rate"]
    print(f"  聚合率(≥2单占比) : {rate:.1%}  {_bar(rate)}")
    print("  各状态聚合单     :")
    for k, v in sorted(stats["bundles_by_status"].items()):
        print(f"      {k:<10} {v}")
    print("  各小区聚合单数   :")
    for k, v in sorted(stats["orders_per_community"].items(), key=lambda kv: -kv[1]):
        print(f"      {k:<14} {v}")
    print("=" * 46)
    return 0


if __name__ == "__main__":
    sys.exit(run())
