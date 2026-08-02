"""Mock delivery-platform adapters (美团 / 闪购 / 京东).

Generates synthetic orders clustered into a handful of communities so the
matching engine has realistic, aggregatable input. Also records status
pushes so the demo can show platform "write-back".
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from .base import ExternalOrder, PlatformAdapter

# A small fixed set of communities so multiple orders collide on the same key.
COMMUNITIES = [
    ("c-wanke", "万科城市花园", 31.2304, 121.4737),
    ("c-greenland", "绿地世纪城", 31.2201, 121.4550),
    ("c-vanke2", "保利叶语", 31.2410, 121.4880),
    ("c-poly", "融创滨江壹号", 31.2150, 121.5010),
    ("c-sunac", "招商雍华府", 31.2350, 121.4600),
]

_PLATFORM_LABELS = {"meituan": "美团", "shangou": "闪购", "jd": "京东"}


def _build_external_order(
    rng: random.Random,
    platform: str,
    community: tuple,
    external_id: str,
    now: Optional[datetime] = None,
    sla_min: int = 20,
    sla_max: int = 45,
) -> ExternalOrder:
    """Craft one synthetic order with realistic effort attributes."""
    now = now or datetime.utcnow()
    cid, cname, lat, lng = community
    floor = rng.randint(1, 24)
    # cluster orders into a small set of buildings so same/adjacent-building
    # aggregation is exercised.
    building_no = rng.randint(1, 8)
    return ExternalOrder(
        platform=platform,
        external_id=external_id,
        community_id=cid,
        community_name=cname,
        address=f"{cname}{building_no}号楼{rng.randint(101, 2508)}",
        lat=lat + rng.uniform(-0.001, 0.001),
        lng=lng + rng.uniform(-0.001, 0.001),
        rider_income_cents=rng.randint(600, 1800),  # 6-18 元
        sla_deadline=now + timedelta(minutes=rng.randint(sla_min, sla_max)),
        floor=floor,
        has_elevator=floor <= 6 or rng.random() < 0.7,
        weight_grams=rng.randint(300, 6000),
        category=rng.choices(["normal", "fresh", "fragile"], weights=[70, 20, 10])[0],
        building_no=building_no,
    )


def generate_external_orders(
    count: int,
    community_ids: Optional[List[str]] = None,
    seed: Optional[int] = None,
    sla_min: int = 20,
    sla_max: int = 45,
) -> List[ExternalOrder]:
    """Generate exactly `count` random orders, optionally restricted to a subset
    of communities (fewer communities => denser aggregation). For test tooling.
    """
    rng = random.Random(seed)
    pool = [c for c in COMMUNITIES if community_ids is None or c[0] in community_ids]
    if not pool:
        pool = list(COMMUNITIES)
    platforms = list(_PLATFORM_LABELS.keys())
    now = datetime.utcnow()
    out: List[ExternalOrder] = []
    for i in range(count):
        platform = rng.choice(platforms)
        community = rng.choice(pool)
        eid = f"sim-{platform}-{now.strftime('%H%M%S')}-{i:04d}-{rng.randint(1000, 9999)}"
        out.append(
            _build_external_order(rng, platform, community, eid, now, sla_min, sla_max)
        )
    return out


class MockPlatformAdapter(PlatformAdapter):
    def __init__(self, name: str, seed: Optional[int] = None) -> None:
        self.name = name
        self._rng = random.Random(seed)
        self._counter = 0
        self.status_log: List[Dict[str, str]] = []

    def fetch_orders(self, limit: int = 20) -> List[ExternalOrder]:
        n = self._rng.randint(1, limit)
        orders: List[ExternalOrder] = []
        now = datetime.utcnow()
        for _ in range(n):
            self._counter += 1
            community = self._rng.choice(COMMUNITIES)
            eid = f"{self.name}-{self._counter:06d}"
            orders.append(_build_external_order(self._rng, self.name, community, eid, now))
        return orders

    def push_status(self, external_id: str, status: str, proof_url: Optional[str] = None) -> bool:
        self.status_log.append(
            {
                "platform": self.name,
                "external_id": external_id,
                "status": status,
                "proof_url": proof_url or "",
                "at": datetime.utcnow().isoformat(),
            }
        )
        return True


_ADAPTERS: Dict[str, MockPlatformAdapter] = {}


def get_platform_adapters() -> Dict[str, MockPlatformAdapter]:
    """Process-wide singleton adapters, one per platform."""
    if not _ADAPTERS:
        for i, key in enumerate(_PLATFORM_LABELS):
            _ADAPTERS[key] = MockPlatformAdapter(key, seed=1000 + i)
    return _ADAPTERS
