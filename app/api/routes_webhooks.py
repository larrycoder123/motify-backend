from fastapi import APIRouter, Request, HTTPException
from app.core.security import verify_n8n_hmac
from app.core.config import settings
from app.models.db import SupabaseDAL, Proof

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/proofs/{challenge_id}")
async def ingest_proof(challenge_id: int, request: Request):
    raw = await request.body()
    sig = request.headers.get("X-N8N-Signature")
    ts = request.headers.get("X-N8N-Timestamp")
    try:
        verify_n8n_hmac(raw, sig, ts, settings.N8N_WEBHOOK_SECRET)
    except HTTPException as e:
        raise e
    payload = await request.json()
    dal = SupabaseDAL.from_env()
    # Only allow storing when service role key is configured (bypasses RLS).
    if dal is None or not settings.SUPABASE_SERVICE_ROLE_KEY:
        # DB not configured or missing service role; accept but do not store to avoid RLS violations.
        return {"status": "accepted", "challenge_id": challenge_id, "stored": False}
    # Ensure user exists to satisfy FK on proofs.user_wallet
    user_wallet = payload.get("user_wallet")
    if user_wallet:
        try:
            dal.client.table("users").upsert({"wallet": user_wallet}).execute()
        except Exception:
            # Don't fail webhook on user upsert; proof insert will surface errors if critical
            pass
    proof = Proof(
        challenge_id=challenge_id,
        user_wallet=user_wallet,
        provider=payload.get("provider"),
        metric=payload.get("metric"),
        value=int(payload.get("value", 0)),
        day_key=payload.get("day_key"),
        window_start=payload.get("window_start"),
        window_end=payload.get("window_end"),
        source_payload_json=payload.get("source_payload_json") or {},
        idempotency_key=payload.get("idempotency_key"),
    )
    dal.insert_proof(proof)
    return {"status": "accepted", "challenge_id": challenge_id, "stored": True}
