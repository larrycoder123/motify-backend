"""
Supabase Data Access Layer (DAL).

Provides methods for interacting with the Supabase database, including
challenge/participant caching and OAuth token management.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from supabase import Client, create_client

from app.core.config import settings


class SupabaseDAL:
    """Data access layer for Supabase operations."""

    def __init__(self, url: str, key: str):
        self.client: Client = create_client(url, key)

    @classmethod
    def from_env(cls) -> Optional["SupabaseDAL"]:
        """Create DAL instance from environment variables."""
        if settings.SUPABASE_URL and (
            settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
        ):
            key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
            return cls(settings.SUPABASE_URL, key)
        return None

    # =========================================================================
    # Challenge Operations
    # =========================================================================

    def upsert_chain_challenges(self, items: List[Dict[str, Any]]) -> Any:
        """Upsert challenge data from chain into cache table."""
        if not items:
            return {"count": 0}
        return (
            self.client.table("chain_challenges")
            .upsert(items, on_conflict="contract_address,challenge_id")
            .execute()
        )

    def upsert_chain_participants(self, items: List[Dict[str, Any]]) -> Any:
        """Upsert participant data from chain into cache table."""
        if not items:
            return {"count": 0}
        return (
            self.client.table("chain_participants")
            .upsert(items, on_conflict="contract_address,challenge_id,participant_address")
            .execute()
        )

    def upsert_finished_challenges(self, items: List[Dict[str, Any]]) -> Any:
        """Archive processed challenge data."""
        if not items:
            return {"count": 0}
        return (
            self.client.table("finished_challenges")
            .upsert(items, on_conflict="contract_address,challenge_id")
            .execute()
        )

    def upsert_finished_participants(self, items: List[Dict[str, Any]]) -> Any:
        """Archive processed participant data with refund percentages."""
        if not items:
            return {"count": 0}
        return (
            self.client.table("finished_participants")
            .upsert(items, on_conflict="contract_address,challenge_id,participant_address")
            .execute()
        )

    def delete_chain_challenge(self, contract_address: str, challenge_id: int) -> Any:
        """Remove challenge from cache after archiving."""
        return (
            self.client
            .table("chain_challenges")
            .delete()
            .eq("contract_address", contract_address)
            .eq("challenge_id", challenge_id)
            .execute()
        )

    def delete_chain_participants(self, contract_address: str, challenge_id: int) -> Any:
        """Remove participants from cache after archiving."""
        return (
            self.client
            .table("chain_participants")
            .delete()
            .eq("contract_address", contract_address)
            .eq("challenge_id", challenge_id)
            .execute()
        )

    # =========================================================================
    # OAuth Token Operations
    # =========================================================================

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
