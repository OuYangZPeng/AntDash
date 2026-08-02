from app.services.ledger import compute_split


def test_example_from_spec():
    # 4 orders totalling 40 元 (4000 cents), X=20%, Y=10%
    split = compute_split(4000, 20.0, 10.0)
    assert split.errand_fee_cents == 800      # 8 元
    assert split.platform_fee_cents == 80     # 0.8 元
    assert split.anter_net_cents == 720       # 7.2 元
    # anter_net == errand_fee * (1 - Y%)
    assert split.anter_net_cents == split.errand_fee_cents - split.platform_fee_cents


def test_zero_income():
    split = compute_split(0, 20.0, 10.0)
    assert split.errand_fee_cents == 0
    assert split.platform_fee_cents == 0
    assert split.anter_net_cents == 0


def test_conservation():
    split = compute_split(3333, 17.0, 7.0)
    # platform + anter net must equal the errand fee exactly (no cents lost)
    assert split.platform_fee_cents + split.anter_net_cents == split.errand_fee_cents


def test_invalid_ratios():
    import pytest

    with pytest.raises(ValueError):
        compute_split(1000, 120.0, 10.0)
    with pytest.raises(ValueError):
        compute_split(-1, 20.0, 10.0)
