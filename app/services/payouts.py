from typing import TypedDict


class PayoutBreakdown(TypedDict):
    refund_amount: int
    fail_amount: int
    commission_amount: int
    charity_amount: int
    reward_from_commission_amount: int


def compute_payouts(
    stake_amount: int,
    percent_ppm: int,
    platform_fee_bps_fail: int = 1000,
    reward_bps_of_fee: int = 500,
) -> PayoutBreakdown:
    """
    Compute the payout split using integer math in the token's smallest unit
    (e.g., USDC has 6 decimals). percent_ppm is parts-per-million.
    """
    if percent_ppm < 0 or percent_ppm > 1_000_000:
        raise ValueError("percent_ppm must be 0..1_000_000")
    if stake_amount < 0:
        raise ValueError("stake_amount must be >= 0")
    refund = (stake_amount * percent_ppm) // 1_000_000
    fail = stake_amount - refund
    commission = (fail * platform_fee_bps_fail) // 10_000
    charity = fail - commission
    reward_from_fee = (commission * reward_bps_of_fee) // 10_000
    return PayoutBreakdown(
        refund_amount=refund,
        fail_amount=fail,
        commission_amount=commission,
        charity_amount=charity,
        reward_from_commission_amount=reward_from_fee,
    )
