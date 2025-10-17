from fastapi import APIRouter, Request, HTTPException
from core.security import verify_n8n_hmac
from core.config import settings
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
    if dal is None:
        # DB not configured yet; accept payload
        return {"status": "accepted", "challenge_id": challenge_id, "stored": False}
    proof = Proof(
        challenge_id=challenge_id,
        user_wallet=payload.get("user_wallet"),
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
