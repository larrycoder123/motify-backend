"""
User statistics endpoint.

Provides aggregated statistics for user participation in challenges,
including success rates and total amounts wagered/donated.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.core.config import settings
from app.models.db import SupabaseDAL

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/user")
def get_user_stats(wallet: str = Query(..., description="User wallet address")):
    """
    Compute per-user stats from finished challenges.

    Args:
        wallet: Ethereum wallet address (0x...)

    Returns:
        challenges_completed: Count of distinct challenges participated in
        success_percentage_overall: Weighted average success rate (0-100%)
        total_wagered: Total amount staked in display units (USDC)
        total_donations: Total amount donated (stake * (1 - refund_percent))
    """
    if not wallet:
        raise HTTPException(status_code=400, detail="wallet is required")

    dal = SupabaseDAL.from_env()
    if not dal:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    w = wallet.lower()
    resp = (
        dal.client
        .table("finished_participants")
        .select("challenge_id,contract_address,stake_minor_units,percent_ppm")
        .ilike("contract_address", settings.MOTIFY_CONTRACT_ADDRESS)
        .ilike("participant_address", w)
        .limit(5000)
        .execute()
    )
    
    data = resp.data if hasattr(resp, "data") else (
        resp.model_dump().get("data") if hasattr(resp, "model_dump") else []
    )

    if not data:
        return {
            "wallet": wallet,
            "challenges_completed": 0,
            "success_percentage_overall": 0.0,
            "total_wagered": 0.0,
            "total_donations": 0.0,
        }

    # Aggregate results
    dec = int(settings.STAKE_TOKEN_DECIMALS or 0)
    denom = float(10 ** dec)
    total_stake_minor = 0
    total_donation_minor = 0
    perc_list = []
    seen = set()

    for row in data:
        key = (row.get("contract_address"), int(row.get("challenge_id", 0)))
        if key in seen:
            continue
        seen.add(key)
        
        stake_minor = int(row.get("stake_minor_units") or 0)
        ppm = int(row.get("percent_ppm") or 0)
        total_stake_minor += stake_minor
        total_donation_minor += int(stake_minor * (1 - (ppm / 1_000_000)))
        perc_list.append(ppm)

    challenges_completed = len(seen)
    success_percentage_overall = (
        (sum(perc_list) / (len(perc_list) * 10_000)) if perc_list else 0.0
    )
    total_wagered = total_stake_minor / denom
    total_donations = total_donation_minor / denom

    return {
        "wallet": wallet,
        "challenges_completed": challenges_completed,
        "success_percentage_overall": round(success_percentage_overall, 2),
        "total_wagered": float(total_wagered),
        "total_donations": float(total_donations),
    }
