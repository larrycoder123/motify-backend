from __future__ import annotations

from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from app.core.config import settings


class SupabaseDAL:
    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)

    @classmethod
    def from_env(cls) -> Optional["SupabaseDAL"]:
        if settings.SUPABASE_URL and (settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY):
            key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
            return cls(settings.SUPABASE_URL, key)
        return None

    def upsert_chain_challenges(self, items: List[Dict[str, Any]]) -> Any:
        if not items:
            return {"count": 0}
        # on_conflict by (contract_address, challenge_id)
        return (
            self.client.table("chain_challenges")
            .upsert(items, on_conflict="contract_address,challenge_id")
            .execute()
        )
    
    def upsert_chain_participants(self, items: List[Dict[str, Any]]):
        if not items:
            return {"count": 0}
        return (
            self.client.table("chain_participants")
            .upsert(items, on_conflict="contract_address,challenge_id,participant_address")
            .execute()
        )

    def upsert_finished_challenges(self, items: List[Dict[str, Any]]):
        if not items:
            return {"count": 0}
        return (
            self.client.table("finished_challenges")
            .upsert(items, on_conflict="contract_address,challenge_id")
            .execute()
        )

    def upsert_finished_participants(self, items: List[Dict[str, Any]]):
        if not items:
            return {"count": 0}
        return (
            self.client.table("finished_participants")
            .upsert(items, on_conflict="contract_address,challenge_id,participant_address")
            .execute()
        )

    def delete_chain_challenge(self, contract_address: str, challenge_id: int):
        return (
            self.client
            .table("chain_challenges")
            .delete()
            .eq("contract_address", contract_address)
            .eq("challenge_id", challenge_id)
            .execute()
        )

    def delete_chain_participants(self, contract_address: str, challenge_id: int):
        return (
            self.client
            .table("chain_participants")
            .delete()
            .eq("contract_address", contract_address)
            .eq("challenge_id", challenge_id)
            .execute()
        )
