from app.config import get_settings
from app.models import ReputationReason
from app.services.reputation import (
    apply_event,
    dispatch_weight,
    passive_recovery,
)

S = get_settings()


def test_on_time_rewards():
    upd = apply_event(60.0, 1.0, ReputationReason.on_time, S)
    assert upd.score == 63.0
    assert upd.delta == S.rep_delta_on_time


def test_abandon_penalises_most():
    on_time = apply_event(60.0, 1.0, ReputationReason.on_time, S).delta
    late = apply_event(60.0, 1.0, ReputationReason.late, S).delta
    abandon = apply_event(60.0, 1.0, ReputationReason.abandon, S).delta
    complaint = apply_event(60.0, 1.0, ReputationReason.complaint, S).delta
    assert abandon < complaint < late < 0 < on_time


def test_score_clamped():
    high = apply_event(100.0, 1.0, ReputationReason.on_time, S)
    assert high.score == S.reputation_max
    low = apply_event(0.0, 0.0, ReputationReason.abandon, S)
    assert low.score == S.reputation_min


def test_ewma_on_time_rate_moves_down_on_late():
    upd = apply_event(60.0, 1.0, ReputationReason.late, S)
    assert upd.on_time_rate < 1.0
    # complaints don't change on-time rate
    upd2 = apply_event(60.0, 0.8, ReputationReason.complaint, S)
    assert upd2.on_time_rate == 0.8


def test_dispatch_weight_monotonic():
    assert dispatch_weight(80.0, S) > dispatch_weight(50.0, S) > dispatch_weight(20.0, S)


def test_passive_recovery_toward_initial():
    recovered = passive_recovery(30.0, minutes=100, settings=S)
    assert 30.0 < recovered <= S.reputation_initial
    # never exceeds initial
    assert passive_recovery(59.0, minutes=100000, settings=S) == S.reputation_initial
    # scores at/above initial are unchanged
    assert passive_recovery(70.0, minutes=100, settings=S) == 70.0
