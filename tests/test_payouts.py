from app.services.payouts import compute_payouts


def test_compute_payouts_basic():
    stake = 1_000_000
    ppm = 900_000  # 90%
    out = compute_payouts(stake, ppm, platform_fee_bps_fail=1000, reward_bps_of_fee=500)
    assert out["refund_wei"] == 900_000
    assert out["fail_wei"] == 100_000
    assert out["commission_wei"] == 10_000  # 10% of fail
    assert out["charity_wei"] == 90_000
    assert out["reward_from_commission_wei"] == 500  # 5% of commission (500 bps)


def test_compute_payouts_edges():
    assert compute_payouts(0, 0)["refund_wei"] == 0
    assert compute_payouts(123, 0)["refund_wei"] == 0
    assert compute_payouts(123, 1_000_000)["refund_wei"] == 123
