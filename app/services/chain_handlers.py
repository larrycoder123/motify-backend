from __future__ import annotations

from typing import Optional, Dict, Any

from fastapi import HTTPException

from app.models.db import SupabaseDAL


def handle_challenge_created_event(
    dal: SupabaseDAL,
    *,
    contract_address: str,
    on_chain_challenge_id: int,
    db_challenge_id: Optional[int] = None,
    owner_wallet: Optional[str] = None,
    description_hash: Optional[str] = None,
    created_tx_hash: Optional[str] = None,
    created_block_number: Optional[int] = None,
) -> Dict[str, Any]:
    """Attach on-chain id to a pending challenge and mark it active.
    If db_challenge_id is provided, use it. Otherwise try to find the latest pending challenge by contract and optional description_hash.
    Returns the updated row. Raises HTTPException on failure.
    """
    # Resolve target challenge row
    target = None
    if db_challenge_id:
        q = (
            dal.client.table("challenges")
            .select("id,contract_address,status")
            .eq("id", db_challenge_id)
            .limit(1)
            .execute()
        )
        rows = getattr(q, "data", [])
        target = rows[0] if rows else None
    else:
        q = dal.client.table("challenges").select("id,contract_address,status").eq("contract_address", contract_address)
        q = q.eq("status", "pending")
        if description_hash:
            q = q.eq("description_hash", description_hash)
        q = q.order("id", desc=True).limit(1).execute()
        rows = getattr(q, "data", [])
        target = rows[0] if rows else None

    if not target:
        raise HTTPException(404, detail={"error": {"code": "NOT_FOUND", "message": "No pending challenge to attach", "details": {}}})

    # Update: set on_chain_challenge_id, owner_wallet (optional), status='active'
    update_data = {
        "on_chain_challenge_id": on_chain_challenge_id,
        "status": "active",
    }
    if owner_wallet:
        update_data["owner_wallet"] = owner_wallet
    if created_tx_hash:
        update_data["created_tx_hash"] = created_tx_hash
    if created_block_number is not None:
        update_data["created_block_number"] = created_block_number

    upd = dal.client.table("challenges").update(update_data).eq("id", target["id"]).execute()
    # Follow-up fetch to return the updated row
    sel = (
        dal.client.table("challenges")
        .select("id,contract_address,on_chain_challenge_id,status,owner_wallet,created_tx_hash,created_block_number")
        .eq("id", target["id"]).limit(1).execute()
    )
    data = getattr(sel, "data", [])
    if not data:
        raise HTTPException(500, detail={"error": {"code": "INTERNAL", "message": "Update fetch failed", "details": {}}})
    return data[0]
