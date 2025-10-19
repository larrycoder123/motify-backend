from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.models.db import SupabaseDAL
from app.services.chain_reader import ChainReader

router = APIRouter(prefix="/indexer", tags=["indexer"])


@router.post("/challenges/{challenge_id}/detail")
def index_challenge_detail(challenge_id: int):
    if challenge_id < 0:
        raise HTTPException(400, "challenge_id must be >= 0")
    if not (settings.WEB3_RPC_URL and settings.MOTIFY_CONTRACT_ADDRESS and settings.MOTIFY_CONTRACT_ABI_PATH):
        raise HTTPException(400, "Web3 not configured")

    dal = SupabaseDAL.from_env()
    if not dal:
        raise HTTPException(400, "Supabase not configured")

    reader = ChainReader.from_settings()
    if not reader:
        raise HTTPException(500, "Failed to init ChainReader")

    detail = reader.get_challenge_detail(challenge_id)

    rows = []
    for p in detail.get("participants", []):
        rows.append({
            "contract_address": settings.MOTIFY_CONTRACT_ADDRESS,
            "challenge_id": detail["challenge_id"],
            "participant_address": p["participant_address"],
            "amount": p["amount"],
            "refund_percentage": p["refund_percentage"],
            "result_declared": p["result_declared"],
        })
    if rows:
        dal.upsert_chain_participants(rows)

    return {"challenge_id": challenge_id, "participants_indexed": len(rows)}


@router.get("/ready")
def list_ready_to_end():
    dal = SupabaseDAL.from_env()
    if not dal:
        raise HTTPException(400, "Supabase not configured")

    # Select ended and not finalized challenges from cache
    from time import time as now
    ts = int(now())
    resp = (
        dal.client
        .table("chain_challenges")
        .select("*")
        .lte("end_time", ts)
        .eq("results_finalized", False)
        .limit(200)
        .execute()
    )
    # normalize SDK response
    if hasattr(resp, "data"):
        data = resp.data
    else:
        md = getattr(resp, "model_dump", None)
        data = md().get("data") if callable(md) else []
    return {"count": len(data), "data": data}


@router.get("/challenges/{challenge_id}/preview")
def preview_refund_percentages(challenge_id: int):
    if challenge_id < 0:
        raise HTTPException(400, "challenge_id must be >= 0")
    dal = SupabaseDAL.from_env()
    if not dal:
        raise HTTPException(400, "Supabase not configured")

    # Load participants from cache
    resp = (
        dal.client
        .table("chain_participants")
        .select("participant_address,amount,refund_percentage,result_declared")
        .eq("contract_address", settings.MOTIFY_CONTRACT_ADDRESS)
        .eq("challenge_id", challenge_id)
        .limit(2000)
        .execute()
    )
    if hasattr(resp, "data"):
        data = resp.data
    else:
        md = getattr(resp, "model_dump", None)
        data = md().get("data") if callable(md) else []
    # For now, return the cached refund_percentage as a placeholder.
    # Later, compute from off-chain proofs or rules.
    items = [
        {
            "user": row["participant_address"],
            "stake_minor_units": int(row["amount"]),
            "percent_ppm": int(row["refund_percentage"]),  # assuming contract stores PPM or similar unit
            "declared": bool(row["result_declared"]),
        }
        for row in data
    ]
    return {"challenge_id": challenge_id, "items": items}


@router.post("/challenges/{challenge_id}/prepare")
def prepare_refund_percentages(challenge_id: int, default_percent_ppm: int = 0):
    """Prepare a simple run of refund percentages.
    This stub uses a constant default_percent_ppm for all participants.
    Later, replace with real logic based on proofs or rules.
    """
    if challenge_id < 0:
        raise HTTPException(400, "challenge_id must be >= 0")
    if not (0 <= default_percent_ppm <= 1_000_000):
        raise HTTPException(400, "default_percent_ppm must be between 0 and 1_000_000")

    dal = SupabaseDAL.from_env()
    if not dal:
        raise HTTPException(400, "Supabase not configured")

    # Ensure participants are cached; if not, fetch from chain
    resp = (
        dal.client
        .table("chain_participants")
        .select("participant_address,amount")
        .eq("contract_address", settings.MOTIFY_CONTRACT_ADDRESS)
        .eq("challenge_id", challenge_id)
        .limit(2000)
        .execute()
    )
    if hasattr(resp, "data"):
        participants = resp.data
    else:
        md = getattr(resp, "model_dump", None)
        participants = md().get("data") if callable(md) else []
    if not participants:
        # fetch from chain and upsert
        if not (settings.WEB3_RPC_URL and settings.MOTIFY_CONTRACT_ADDRESS and settings.MOTIFY_CONTRACT_ABI_PATH):
            raise HTTPException(400, "Web3 not configured and no cached participants")
        from app.services.chain_reader import ChainReader
        reader = ChainReader.from_settings()
        if not reader:
            raise HTTPException(500, "Failed to init ChainReader")
        detail = reader.get_challenge_detail(challenge_id)
        rows = []
        for p in detail.get("participants", []):
            rows.append({
                "contract_address": settings.MOTIFY_CONTRACT_ADDRESS,
                "challenge_id": detail["challenge_id"],
                "participant_address": p["participant_address"],
                "amount": p["amount"],
                "refund_percentage": p["refund_percentage"],
                "result_declared": p["result_declared"],
            })
        if rows:
            dal.upsert_chain_participants(rows)
            participants = rows

    items = [
        {
            "user": row["participant_address"],
            "stake_minor_units": int(row["amount"]),
            "percent_ppm": int(default_percent_ppm),
        }
        for row in participants
    ]
    return {"challenge_id": challenge_id, "items": items, "rule": {"type": "constant", "default_percent_ppm": default_percent_ppm}}


@router.post("/ready/details")
def index_ready_challenges_details(limit: int = 200):
    dal = SupabaseDAL.from_env()
    if not dal:
        raise HTTPException(400, "Supabase not configured")
    if not (settings.WEB3_RPC_URL and settings.MOTIFY_CONTRACT_ADDRESS and settings.MOTIFY_CONTRACT_ABI_PATH):
        raise HTTPException(400, "Web3 not configured")

    from time import time as now
    ts = int(now())
    ready_resp = (
        dal.client
        .table("chain_challenges")
        .select("challenge_id")
        .lte("end_time", ts)
        .eq("results_finalized", False)
        .limit(limit)
        .execute()
    )
    if hasattr(ready_resp, "data"):
        ready = ready_resp.data
    else:
        md = getattr(ready_resp, "model_dump", None)
        ready = md().get("data") if callable(md) else []

    from app.services.chain_reader import ChainReader
    reader = ChainReader.from_settings()
    if not reader:
        raise HTTPException(500, "Failed to init ChainReader")

    total = 0
    for row in ready:
        cid = int(row["challenge_id"])
        detail = reader.get_challenge_detail(cid)
        rows = []
        for p in detail.get("participants", []):
            rows.append({
                "contract_address": settings.MOTIFY_CONTRACT_ADDRESS,
                "challenge_id": detail["challenge_id"],
                "participant_address": p["participant_address"],
                "amount": p["amount"],
                "refund_percentage": p["refund_percentage"],
                "result_declared": p["result_declared"],
            })
        if rows:
            dal.upsert_chain_participants(rows)
            total += len(rows)

    return {"ready": len(ready), "participants_indexed": total}
