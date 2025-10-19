from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.models.db import SupabaseDAL
from app.services.chain_reader import ChainReader

router = APIRouter(prefix="/indexer", tags=["indexer"])


@router.get("/challenges")
def index_challenges(limit: int = 1000, only_ready_to_end: bool = True):
    if not (settings.WEB3_RPC_URL and settings.MOTIFY_CONTRACT_ADDRESS and settings.MOTIFY_CONTRACT_ABI_PATH):
        raise HTTPException(400, "Web3 indexer not configured")

    reader = ChainReader.from_settings()
    if not reader:
        raise HTTPException(500, "Failed to init ChainReader")

    dal = SupabaseDAL.from_env()
    if not dal:
        raise HTTPException(400, "Supabase not configured")

    items = reader.get_all_challenges(limit=limit)

    # Filter: ended by time and not finalized yet (ready to process end-of-challenge)
    from time import time as now
    ts = int(now())
    filtered = [c for c in items if (not only_ready_to_end) or (c["end_time"] <= ts and not c["results_finalized"])]

    # Map to DB rows. We need contract address to disambiguate multi-network support later.
    rows = []
    for c in filtered:
        rows.append({
            "contract_address": settings.MOTIFY_CONTRACT_ADDRESS,
            "challenge_id": c["challenge_id"],
            "recipient": c["recipient"],
            "start_time": c["start_time"],
            "end_time": c["end_time"],
            "is_private": c["is_private"],
            "api_type": c["api_type"],
            "goal_type": c["goal_type"],
            "goal_amount": c["goal_amount"],
            "description": c["description"],
            "total_donation_amount": c["total_donation_amount"],
            "results_finalized": c["results_finalized"],
            "participant_count": c["participant_count"],
        })

    resp = dal.upsert_chain_challenges(rows)

    return {
        "fetched": len(items),
        "indexed": len(rows),
        "only_ready_to_end": only_ready_to_end,
        "supabase_response": getattr(resp, "model_dump", lambda: str(resp))(),
    }
