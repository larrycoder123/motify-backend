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


def handle_joined_challenge_event(
    dal: SupabaseDAL,
    *,
    contract_address: str | None = None,
    on_chain_challenge_id: int | None = None,
    db_challenge_id: int | None = None,
    user_wallet: str,
    amount_minor_units: int | str,
    tx_hash: str | None = None,
    block_number: int | None = None,
) -> Dict[str, Any]:
    """Handle on-chain JoinedChallenge by inserting/updating the stake row.

    - Ensures the user exists in users table (wallet lowercase for consistency)
    - Upserts into stakes on (challenge_id, user_wallet)
    - Sets amount_minor_units from on-chain amount (token smallest unit, USDC 6 decimals)
    - Associates joined_via from challenges.api_provider if present
    - Optionally stores tx_hash_deposit
    Returns the upserted stake payload
    """
    wallet_norm = (user_wallet or "").lower()
    if not wallet_norm:
        raise HTTPException(400, detail={"error": {"code": "VALIDATION_FAILED", "message": "missing user wallet", "details": {}}})

    # Ensure user exists
    dal.client.table("users").upsert({"wallet": wallet_norm}).execute()

    # Fetch challenge for provider association
    if db_challenge_id is not None:
        ch = (
            dal.client.table("challenges")
            .select("id, api_provider")
            .eq("id", db_challenge_id)
            .limit(1)
            .execute()
        )
    else:
        if not (contract_address and on_chain_challenge_id is not None):
            raise HTTPException(400, detail={"error": {"code": "VALIDATION_FAILED", "message": "challenge reference required", "details": {}}})
        ch = (
            dal.client.table("challenges")
            .select("id, api_provider")
            .eq("contract_address", contract_address)
            .eq("on_chain_challenge_id", on_chain_challenge_id)
            .limit(1)
            .execute()
        )
    rows = getattr(ch, "data", [])
    if not rows:
        raise HTTPException(404, detail={"error": {"code": "NOT_FOUND", "message": "challenge not found", "details": {"contract_address": contract_address, "on_chain_challenge_id": on_chain_challenge_id, "db_id": db_challenge_id}}})
    api_provider = rows[0].get("api_provider")
    resolved_db_id = rows[0].get("id")

    amt_str = str(int(amount_minor_units))
    stake_payload = {
        "challenge_id": resolved_db_id,
        "user_wallet": wallet_norm,
        "amount_minor_units": amt_str,
        "joined_via": api_provider,
    }
    if tx_hash:
        stake_payload["tx_hash_deposit"] = tx_hash
    if block_number is not None:
        stake_payload["joined_block_number"] = block_number

    try:
        resp = dal.client.table("stakes").upsert(stake_payload, on_conflict="challenge_id,user_wallet").execute()
    except Exception as e:
        # Legacy DB compatibility: some deployments still enforce NOT NULL on amount_wei
        # Retry with amount_wei populated matching amount_minor_units
        try:
            stake_payload_legacy = dict(stake_payload)
            stake_payload_legacy["amount_wei"] = amt_str
            resp = dal.client.table("stakes").upsert(stake_payload_legacy, on_conflict="challenge_id,user_wallet").execute()
        except Exception:
            raise
    data = getattr(resp, "data", [])
    return data[0] if data else stake_payload
