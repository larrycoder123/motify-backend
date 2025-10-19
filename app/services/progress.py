from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.models.db import SupabaseDAL


def _lookup_tokens(api_type: Optional[str], participants: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Optionally fetch per-user access tokens from Supabase for a given provider.

    Returns dict[address_lower] = token or None.
    Controlled by settings.USER_TOKENS_*; if not set, returns None for all.
    """
    addr_key = lambda a: str(a).lower()
    # If api_type is provided, token lookup must be configured
    if api_type:
        if not (settings.USER_TOKENS_TABLE and settings.USER_TOKENS_WALLET_COL and settings.USER_TOKENS_PROVIDER_COL and settings.USER_TOKENS_ACCESS_TOKEN_COL):
            raise RuntimeError("User token lookup not configured: set USER_TOKENS_TABLE and column envs for provider progress fetching.")
    else:
        # No provider specified; return None tokens
        return {addr_key(p["participant_address"]): None for p in participants}

    dal = SupabaseDAL.from_env()
    if not dal:
        raise RuntimeError("Supabase not configured for token lookup")

    addrs = [addr_key(p["participant_address"]) for p in participants]
    # Simple in-clause query; for large sets, batch or use rpc.
    resp = (
        dal.client
        .table(settings.USER_TOKENS_TABLE)
        .select(f"{settings.USER_TOKENS_WALLET_COL},{settings.USER_TOKENS_ACCESS_TOKEN_COL}")
        .eq(settings.USER_TOKENS_PROVIDER_COL, api_type)
        .in_(settings.USER_TOKENS_WALLET_COL, addrs)
        .limit(5000)
        .execute()
    )
    data = resp.data if hasattr(resp, "data") else (resp.model_dump().get("data") if hasattr(resp, "model_dump") else [])
    tokens = {str(row.get(settings.USER_TOKENS_WALLET_COL, "")).lower(): row.get(settings.USER_TOKENS_ACCESS_TOKEN_COL) for row in (data or [])}
    # Fill missing with None
    return {a: tokens.get(a) for a in addrs}


def fetch_progress(challenge_id: int, participants: List[Dict[str, Any]], api_type: Optional[str] = None) -> Dict[str, float]:
    """Stub: return a per-user completion ratio in [0.0, 1.0].

    Keys are participant addresses (lowercased), values are floats.
    Replace this with real API calls to compute completion for each participant.
    """
    addr_key = lambda a: str(a).lower()
    _ = _lookup_tokens(api_type, participants)  # tokens available when you integrate real provider calls
    # For now, return 0.0 for all participants as a placeholder.
    return {addr_key(p["participant_address"]): 0.0 for p in participants}


def ratio_to_ppm(ratio: float) -> int:
    """Clamp ratio to [0.0,1.0] and convert to parts-per-million integer."""
    if ratio is None:
        return 0
    try:
        r = max(0.0, min(1.0, float(ratio)))
    except (TypeError, ValueError):
        return 0
    return int(round(r * 1_000_000))
