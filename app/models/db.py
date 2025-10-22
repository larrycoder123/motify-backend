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

    # ----------------------------
    # OAuth user_tokens helpers
    # ----------------------------
    def get_user_token(self, wallet_address: str, provider: str):
        w = (wallet_address or "").lower()
        p = (provider or "").lower()
        resp = (
            self.client
            .table("user_tokens")
            .select("wallet_address,provider,access_token,refresh_token,expires_at,scopes,updated_at")
            .eq("wallet_address", w)
            .eq("provider", p)
            .limit(1)
            .execute()
        )
        data = getattr(resp, "data", None)
        if data is None and hasattr(resp, "model_dump"):
            data = resp.model_dump().get("data")
        return (data[0] if data else None)

    def upsert_user_token(self, item: dict):
        # Normalize fields and enforce lowercase wallet/provider
        item = dict(item or {})
        if "wallet_address" in item and item["wallet_address"]:
            item["wallet_address"] = str(item["wallet_address"]).lower()
        if "provider" in item and item["provider"]:
            item["provider"] = str(item["provider"]).lower()
        return (
            self.client
            .table("user_tokens")
            .upsert(item, on_conflict="wallet_address,provider")
            .execute()
        )

    def delete_user_token(self, wallet_address: str, provider: str):
        w = (wallet_address or "").lower()
        p = (provider or "").lower()
        return (
            self.client
            .table("user_tokens")
            .delete()
            .eq("wallet_address", w)
            .eq("provider", p)
            .execute()
        )

    # OAuth / user_tokens methods
    def get_user_token(self, wallet_address: str, provider: str) -> Optional[Dict[str, Any]]:
        """Get OAuth token for a wallet address and provider."""
        result = (
            self.client
            .table("user_tokens")
            .select("*")
            .eq("wallet_address", wallet_address.lower())
            .eq("provider", provider.lower())
            .execute()
        )
        return result.data[0] if result.data else None

    def upsert_user_token(self, data: Dict[str, Any]) -> Any:
        """Insert or update user OAuth token."""
        return (
            self.client
            .table("user_tokens")
            .upsert(data, on_conflict="wallet_address,provider")
            .execute()
        )

    def delete_user_token(self, wallet_address: str, provider: str) -> Any:
        """Delete OAuth token for a wallet address and provider."""
        return (
            self.client
            .table("user_tokens")
            .delete()
            .eq("wallet_address", wallet_address.lower())
            .eq("provider", provider.lower())
            .execute()
        )
