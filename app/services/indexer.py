from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.models.db import SupabaseDAL
from app.services.chain_reader import ChainReader
from app.services.progress import fetch_progress, ratio_to_ppm


def _ensure_web3_configured() -> None:
    if not (settings.WEB3_RPC_URL and settings.MOTIFY_CONTRACT_ADDRESS and settings.MOTIFY_CONTRACT_ABI_PATH):
        raise RuntimeError("Web3 not configured")


def _get_resp_data(resp: Any) -> List[Dict[str, Any]]:
    if hasattr(resp, "data"):
        return resp.data or []
    md = getattr(resp, "model_dump", None)
    if callable(md):
        d = md()
        return d.get("data") or []
    return []


def fetch_and_cache_ended_challenges(limit: int = 1000, only_ready_to_end: bool = True, exclude_finished: bool = True) -> Dict[str, Any]:
    """Fetch challenges from chain and cache ended & not-finalized ones into Supabase."""
    _ensure_web3_configured()
    reader = ChainReader.from_settings()
    if not reader:
        raise RuntimeError("Failed to init ChainReader")

    dal = SupabaseDAL.from_env()
    if not dal:
        raise RuntimeError("Supabase not configured")

    items = reader.get_all_challenges(limit=limit)

    from time import time as now
    ts = int(now())
    filtered = [c for c in items if (not only_ready_to_end) or (c["end_time"] <= ts and not c["results_finalized"])]

    # Optionally skip already-archived challenges (present in finished_challenges)
    archived_ids: set[int] = set()
    if exclude_finished and filtered:
        try:
            ids = [int(c["challenge_id"]) for c in filtered]
            resp_arch = (
                dal.client
                .table("finished_challenges")
                .select("challenge_id")
                .eq("contract_address", settings.MOTIFY_CONTRACT_ADDRESS)
                .in_("challenge_id", ids)
                .execute()
            )
            archived_rows = _get_resp_data(resp_arch)
            archived_ids = {int(r["challenge_id"]) for r in archived_rows}
        except Exception:
            archived_ids = set()

    rows = []
    for c in filtered:
        if exclude_finished and int(c["challenge_id"]) in archived_ids:
            continue
        rows.append({
            "contract_address": settings.MOTIFY_CONTRACT_ADDRESS,
            "challenge_id": c["challenge_id"],
            "recipient": c["recipient"],
            "start_time": c["start_time"],
            "end_time": c["end_time"],
            "is_private": c["is_private"],
            "name": c.get("name", ""),
            "api_type": c["api_type"],
            "goal_type": c["goal_type"],
            "goal_amount": c["goal_amount"],
            "description": c["description"],
            "total_donation_amount": c["total_donation_amount"],
            "results_finalized": c["results_finalized"],
            "participant_count": c["participant_count"],
        })

    resp = dal.upsert_chain_challenges(rows)
    # normalize for logging/debug only
    supabase_response = getattr(resp, "model_dump", lambda: str(resp))()
    return {
        "fetched": len(items),
        "indexed": len(rows),
        "only_ready_to_end": only_ready_to_end,
        "exclude_finished": exclude_finished,
        "skipped_archived": len(archived_ids) if exclude_finished else 0,
        "supabase_response": supabase_response,
    }


def cache_participants(challenge_id: int) -> Dict[str, Any]:
    if challenge_id < 0:
        raise ValueError("challenge_id must be >= 0")

    dal = SupabaseDAL.from_env()
    if not dal:
        raise RuntimeError("Supabase not configured")

    # If already archived, skip any further caching
    archived_chk = (
        dal.client
        .table("finished_challenges")
        .select("challenge_id")
        .eq("contract_address", settings.MOTIFY_CONTRACT_ADDRESS)
        .eq("challenge_id", int(challenge_id))
        .limit(1)
        .execute()
    )
    if _get_resp_data(archived_chk):
        return {"challenge_id": challenge_id, "participants_indexed": 0, "skipped": True, "reason": "already_archived"}

    # Enforce ready-state: challenge must be ended and not finalized in cache
    from time import time as now
    ts = int(now())
    chk = (
        dal.client
        .table("chain_challenges")
        .select("challenge_id,end_time,results_finalized")
        .eq("contract_address", settings.MOTIFY_CONTRACT_ADDRESS)
        .eq("challenge_id", challenge_id)
        .lte("end_time", ts)
        .eq("results_finalized", False)
        .limit(1)
        .execute()
    )
    ready_rows = _get_resp_data(chk)
    if not ready_rows:
        return {"challenge_id": challenge_id, "participants_indexed": 0, "skipped": True, "reason": "not_ready"}

    _ensure_web3_configured()
    reader = ChainReader.from_settings()
    if not reader:
        raise RuntimeError("Failed to init ChainReader")

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

    return {"challenge_id": challenge_id, "participants_indexed": len(rows), "skipped": False}


def list_ready_challenges(limit: int = 200) -> List[Dict[str, Any]]:
    dal = SupabaseDAL.from_env()
    if not dal:
        raise RuntimeError("Supabase not configured")

    from time import time as now
    ts = int(now())
    resp = (
        dal.client
        .table("chain_challenges")
        .select("*")
        .lte("end_time", ts)
        .eq("results_finalized", False)
        .limit(limit)
        .execute()
    )
    return _get_resp_data(resp)


    


def prepare_run(challenge_id: int, default_percent_ppm: int = 0) -> Dict[str, Any]:
    if challenge_id < 0:
        raise ValueError("challenge_id must be >= 0")
    if not (0 <= default_percent_ppm <= 1_000_000):
        raise ValueError("default_percent_ppm must be between 0 and 1_000_000")

    dal = SupabaseDAL.from_env()
    if not dal:
        raise RuntimeError("Supabase not configured")

    resp = (
        dal.client
        .table("chain_participants")
        .select("participant_address,amount,result_declared")
        .eq("contract_address", settings.MOTIFY_CONTRACT_ADDRESS)
        .eq("challenge_id", challenge_id)
        .eq("result_declared", False)
        .limit(2000)
        .execute()
    )
    participants = _get_resp_data(resp)

    if not participants:
        # Attempt to cache participants (enforces ready state)
        res = cache_participants(challenge_id)
        if res.get("participants_indexed"):
            participants = (
                dal.client
                .table("chain_participants")
                .select("participant_address,amount,result_declared")
                .eq("contract_address", settings.MOTIFY_CONTRACT_ADDRESS)
                .eq("challenge_id", challenge_id)
                .eq("result_declared", False)
                .limit(2000)
                .execute()
            )
            participants = _get_resp_data(participants)

    # Determine provider from cached challenge (api_type) to select correct token source
    chal = (
        dal.client
        .table("chain_challenges")
        .select("api_type")
        .eq("contract_address", settings.MOTIFY_CONTRACT_ADDRESS)
        .eq("challenge_id", challenge_id)
        .limit(1)
        .execute()
    )
    chal_rows = _get_resp_data(chal)
    api_type = (chal_rows[0]["api_type"] if chal_rows else None)

    # Look up progress ratios for each participant and compute ppm
    addr_key = lambda a: str(a).lower()
    ratios = fetch_progress(challenge_id, participants, api_type=api_type)
    items = []
    for row in participants:
        addr = row["participant_address"]
        stake = int(row["amount"])
        ratio = ratios.get(addr_key(addr))
        ppm = ratio_to_ppm(ratio) if ratio is not None else int(default_percent_ppm)
        items.append({
            "user": addr,
            "stake_minor_units": stake,
            "percent_ppm": int(ppm),
            "progress_ratio": ratio,
        })

    return {
        "challenge_id": challenge_id,
        "items": items,
        "rule": {"type": "progress", "fallback_percent_ppm": int(default_percent_ppm)},
    }


def cache_details_for_ready(limit: int = 200) -> Dict[str, Any]:
    dal = SupabaseDAL.from_env()
    if not dal:
        raise RuntimeError("Supabase not configured")

    _ensure_web3_configured()
    ready = list_ready_challenges(limit=limit)

    total = 0
    for row in ready:
        cid = int(row["challenge_id"])
        res = cache_participants(cid)
        total += int(res.get("participants_indexed", 0))

    return {"ready": len(ready), "participants_indexed": total}


def process_ready_once(default_percent_ppm: int = 0, limit: int = 50) -> Dict[str, Any]:
        """One-shot processor for the envisioned loop (sans on-chain txs).

        Steps:
            1) Refresh cache of ended & not-finalized challenges from chain
            2) List ready challenges from DB
            3) For each, ensure participants are cached
            4) Build a simple constant-ppm preview (stand-in for proofs/policy)
            5) [Placeholder] Here you'd submit declareResults and afterwards mark as finished
        """
        # 1) Refresh cache
        refresh = fetch_and_cache_ended_challenges(limit=limit, only_ready_to_end=True)
        # 2) List ready
        ready = list_ready_challenges(limit=limit)
        processed = []
        for row in ready:
                cid = int(row["challenge_id"])
                # 3) Cache participants (enforces ready-state)
                cached = cache_participants(cid)
                # 4) Build preview
                preview = prepare_run(cid, default_percent_ppm=default_percent_ppm)
                processed.append({"challenge_id": cid, "cached": cached, "preview": preview})

        return {"refresh": refresh, "count": len(processed), "items": processed}


def archive_and_cleanup(
    challenge_id: int,
    rule: Dict[str, Any],
    summary: Optional[Dict[str, Any]] = None,
    delete_participants: bool = True,
    finished_items: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Archive a processed challenge and clean up cached rows.

    Call this AFTER a successful on-chain declare/finalize. It will:
    - upsert into finished_challenges with rule and optional summary
    - upsert per-participant rows into finished_participants when provided
      - delete the challenge row from chain_challenges
      - optionally delete all chain_participants for that challenge

    Returns a compact report of affected rows.
    """
    if challenge_id < 0:
        raise ValueError("challenge_id must be >= 0")

    dal = SupabaseDAL.from_env()
    if not dal:
        raise RuntimeError("Supabase not configured")

    # 1) Archive (challenge-level)
    archive_item = {
        "contract_address": settings.MOTIFY_CONTRACT_ADDRESS,
        "challenge_id": int(challenge_id),
        "rule": rule,
        "summary": summary or {},
    }
    arch_resp = dal.upsert_finished_challenges([archive_item])

    # 1b) Archive (participant-level) if provided
    parts_resp = None
    if finished_items:
        to_row = []
        for it in finished_items:
            # expected keys in `it`: participant_address, stake_minor_units, percent_ppm
            # optional: progress_ratio, batch_no, tx_hash
            to_row.append({
                "contract_address": settings.MOTIFY_CONTRACT_ADDRESS,
                "challenge_id": int(challenge_id),
                "participant_address": it["user"] if "user" in it else it["participant_address"],
                "stake_minor_units": int(it["stake_minor_units"] if "stake_minor_units" in it else it.get("amount_minor_units", 0)),
                "percent_ppm": int(it["percent_ppm"]),
                "progress_ratio": it.get("progress_ratio"),
                "batch_no": it.get("batch_no"),
                "tx_hash": it.get("tx_hash"),
            })
        if to_row:
            parts_resp = dal.upsert_finished_participants(to_row)

    # 2) Delete from working cache
    del_chal = dal.delete_chain_challenge(settings.MOTIFY_CONTRACT_ADDRESS, int(challenge_id))
    del_parts = None
    if delete_participants:
        del_parts = dal.delete_chain_participants(settings.MOTIFY_CONTRACT_ADDRESS, int(challenge_id))

    # Normalize responses for logging/debug only
    to_dump = lambda r: getattr(r, "model_dump", lambda: str(r))()
    return {
        "archived": to_dump(arch_resp),
        "archived_participants": to_dump(parts_resp) if parts_resp is not None else None,
        "deleted_challenge": to_dump(del_chal),
        "deleted_participants": to_dump(del_parts) if del_parts is not None else None,
    }
