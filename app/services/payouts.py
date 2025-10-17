from typing import TypedDict


class PayoutBreakdown(TypedDict):
    refund_wei: int
    fail_wei: int
    commission_wei: int
    charity_wei: int
    reward_from_commission_wei: int


def compute_payouts(
    stake_wei: int,
    percent_ppm: int,
    platform_fee_bps_fail: int = 1000,
    reward_bps_of_fee: int = 500,
) -> PayoutBreakdown:
    if percent_ppm < 0 or percent_ppm > 1_000_000:
        raise ValueError("percent_ppm must be 0..1_000_000")
    if stake_wei < 0:
        raise ValueError("stake_wei must be >= 0")
    refund = (stake_wei * percent_ppm) // 1_000_000
    fail = stake_wei - refund
    commission = (fail * platform_fee_bps_fail) // 10_000
    charity = fail - commission
    reward_from_fee = (commission * reward_bps_of_fee) // 10_000
    return PayoutBreakdown(
        refund_wei=refund,
        fail_wei=fail,
        commission_wei=commission,
        charity_wei=charity,
        reward_from_commission_wei=reward_from_fee,
    )
