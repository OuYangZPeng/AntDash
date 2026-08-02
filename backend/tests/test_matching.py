from datetime import datetime, timedelta

from app.config import get_settings
from app.services.matching import (
    Candidate,
    dynamic_window_minutes,
    group_by_community,
    score_group,
)

S = get_settings()


def test_window_shrinks_with_high_rate():
    low = dynamic_window_minutes(0.1, S)   # sparse
    high = dynamic_window_minutes(10.0, S)  # busy
    assert low > high
    assert S.match_window_min_minutes <= high <= S.match_window_max_minutes
    assert S.match_window_min_minutes <= low <= S.match_window_max_minutes


def test_window_clamped():
    assert dynamic_window_minutes(1e-9, S) == S.match_window_max_minutes
    assert dynamic_window_minutes(1e9, S) == S.match_window_min_minutes


def test_group_by_community():
    now = datetime.utcnow()
    cs = [
        Candidate("o1", "A", 31.0, 121.0, 1000, now + timedelta(minutes=30)),
        Candidate("o2", "A", 31.0, 121.0, 1000, now + timedelta(minutes=30)),
        Candidate("o3", "B", 31.1, 121.1, 1000, now + timedelta(minutes=30)),
    ]
    groups = group_by_community(cs)
    assert set(groups.keys()) == {"A", "B"}
    assert len(groups["A"]) == 2


def test_same_community_scores_higher():
    now = datetime.utcnow()
    same = [
        Candidate("o1", "A", 31.0, 121.0, 1000, now + timedelta(minutes=30)),
        Candidate("o2", "A", 31.0, 121.0, 1000, now + timedelta(minutes=30)),
    ]
    mixed = [
        Candidate("o1", "A", 31.0, 121.0, 1000, now + timedelta(minutes=30)),
        Candidate("o3", "B", 32.0, 122.0, 1000, now + timedelta(minutes=30)),
    ]
    assert score_group(same, now, S) > score_group(mixed, now, S)


def test_empty_group_scores_zero():
    assert score_group([], datetime.utcnow(), S) == 0.0


def _mem_session():
    from sqlmodel import SQLModel, Session, create_engine

    eng = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(eng)
    return Session(eng)


def test_same_building_bundle_caps_at_five():
    from app.models import Bundle, Order
    from app.services.matching import run_matching

    with _mem_session() as s:
        for i in range(7):  # 7 orders, same community + same building
            s.add(Order(
                platform="meituan", external_id=f"e{i}", community_id="c-A",
                community_name="A小区", address="A小区3号楼", lat=31.0, lng=121.0,
                building_no=3, rider_income_cents=1000,
                sla_deadline=datetime.utcnow() + timedelta(minutes=30),
            ))
        s.commit()
        run_matching(s)
        bundles = s.exec(__import__("sqlmodel").select(Bundle)).all()
        matched = sum(b.order_count for b in bundles)
        assert matched == 7
        assert all(b.order_count <= S.match_max_bundle_size_adjacent for b in bundles)
        assert len(bundles) >= 2  # 5 + 2 -> at least two bundles


def test_non_adjacent_buildings_split():
    from app.models import Bundle, Order
    from app.services.matching import run_matching

    with _mem_session() as s:
        # buildings 1 and 8 are not adjacent -> must land in separate bundles
        for bno in (1, 8):
            s.add(Order(
                platform="jd", external_id=f"b{bno}", community_id="c-B",
                community_name="B小区", address=f"B小区{bno}号楼", lat=31.0, lng=121.0,
                building_no=bno, rider_income_cents=1000,
                sla_deadline=datetime.utcnow() + timedelta(minutes=30),
            ))
        s.commit()
        run_matching(s)
        bundles = s.exec(__import__("sqlmodel").select(Bundle)).all()
        assert len([b for b in bundles if b.order_count > 0]) == 2
