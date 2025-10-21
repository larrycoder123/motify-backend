from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from app.models.db import SupabaseDAL
from app.core.config import settings

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/user")
def get_user_stats(wallet: str = Query(..., description="User wallet address")):
    """Compute per-user stats from finished_participants.

    Returns:
      - challenges_completed: count of distinct (contract_address, challenge_id)
      - success_percentage_overall: weighted average of percent_ppm over challenges or simple mean
      - total_wagered: sum of stake in display units (USDC assumed by decimals)
    - total_donations: sum((1 - percent) * stake)

    Note: percent_ppm is parts-per-million (0..1_000_000).
    """
    if not wallet:
        raise HTTPException(status_code=400, detail="wallet is required")

    dal = SupabaseDAL.from_env()
    if not dal:
        raise HTTPException(status_code=500, detail="Supabase not configured")

    w = wallet.lower()
    # Use case-insensitive match for addresses (checksum vs lowercase)
    resp = (
        dal.client
        .table("finished_participants")
        .select("challenge_id,contract_address,stake_minor_units,percent_ppm")
        .ilike("contract_address", settings.MOTIFY_CONTRACT_ADDRESS)
        .ilike("participant_address", w)
        .limit(5000)
        .execute()
    )
    data = resp.data if hasattr(resp, "data") else (resp.model_dump().get("data") if hasattr(resp, "model_dump") else [])

    if not data:
        return {
            "wallet": wallet,
            "challenges_completed": 0,
            "success_percentage_overall": 0.0,
            "total_wagered": 0.0,
            "total_donations": 0.0,
        }

    # Aggregate
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
        # Donations are the portion NOT refunded: stake * (1 - percent)
        total_donation_minor += int(stake_minor * (1 - (ppm / 1_000_000)))
        perc_list.append(ppm)

    challenges_completed = len(seen)
    success_percentage_overall = (sum(perc_list) / (len(perc_list) * 10_000)) if perc_list else 0.0  # as percent (0..100)
    total_wagered = total_stake_minor / denom
    total_donations = total_donation_minor / denom

    return {
        "wallet": wallet,
        "challenges_completed": challenges_completed,
        "success_percentage_overall": round(success_percentage_overall, 2),
        "total_wagered": float(total_wagered),
        "total_donations": float(total_donations),
    }
