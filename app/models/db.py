from __future__ import annotations

from typing import Any, Optional
from supabase import create_client, Client
from pydantic import BaseModel
from app.core.config import settings


class Proof(BaseModel):
    challenge_id: int
    user_wallet: str
    provider: str
    metric: str
    value: int
    day_key: str
    window_start: str
    window_end: str
    source_payload_json: dict
    idempotency_key: str


class SupabaseDAL:
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)

    @classmethod
    def from_env(cls) -> Optional["SupabaseDAL"]:
        if settings.SUPABASE_URL and (settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY):
            key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
            return cls(settings.SUPABASE_URL, key)
        return None

    # Idempotent insert: relies on DB unique constraints
    def insert_proof(self, proof: Proof) -> dict[str, Any]:
        data = proof.model_dump()
        # Use upsert w/ on_conflict idempotency_key to avoid duplicates
        resp = (
            self.client.table("proofs")
            .upsert(data, on_conflict="idempotency_key")
            .execute()
        )
        return {"inserted": True, "response": resp.model_dump() if hasattr(resp, "model_dump") else str(resp)}
