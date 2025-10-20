from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import datetime as _dt
import time as _time
import requests

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
    """Return per-user completion ratio in [0.0, 1.0].

    For api_type == "strava":
      - Supports goal_type in {distance_m, active_days}
      - Aggregates activities in [start_time, end_time]

    Keys are participant addresses (lowercased), values are floats. If a value is None,
    callers should apply a sensible default (e.g., fallback percent).
    """
    addr_key = lambda a: str(a).lower()

    if not participants:
        return {}

    # Strava provider implementation
    if (api_type or "").lower() == "strava":
        return _fetch_progress_strava(challenge_id, participants)

    # Default for unknown provider: no data
    return {addr_key(p["participant_address"]): None for p in participants}


# --------------------------
# Strava provider
# --------------------------

_STRAVA_ACTIVITIES_URL = "https://www.strava.com/api/v3/athlete/activities"
_HTTP_TIMEOUT_SEC = 15
_MAX_PAGES = 5  # cap to 5*200 = 1000 activities per user for safety


def _get_challenge_meta(challenge_id: int) -> Optional[Dict[str, Any]]:
    """Load challenge meta needed for fetching progress.

    Returns dict with: start_time, end_time, goal_type, goal_amount, contract_address
    """
    dal = SupabaseDAL.from_env()
    if not dal:
        raise RuntimeError("Supabase not configured for progress fetching")
    resp = (
        dal.client
        .table("chain_challenges")
        .select("start_time,end_time,goal_type,goal_amount")
        .eq("contract_address", settings.MOTIFY_CONTRACT_ADDRESS)
        .eq("challenge_id", int(challenge_id))
        .limit(1)
        .execute()
    )
    data = resp.data if hasattr(resp, "data") else (resp.model_dump().get("data") if hasattr(resp, "model_dump") else [])
    return (data[0] if data else None)


def _strava_fetch_user_activities(token: str, start_ts: int, end_ts: int) -> List[Dict[str, Any]]:
    """Fetch Strava activities for a user within timeframe.

    Respects pagination; returns a list of activity dicts with at least distance, moving_time, total_elevation_gain, start_date.
    """
    headers = {"Authorization": f"Bearer {token}"}
    page = 1
    items: List[Dict[str, Any]] = []
    while page <= _MAX_PAGES:
        params = {
            "after": int(start_ts),
            "before": int(end_ts),
            "per_page": 200,
            "page": page,
        }
        r = requests.get(_STRAVA_ACTIVITIES_URL, headers=headers, params=params, timeout=_HTTP_TIMEOUT_SEC)
        if r.status_code == 401 or r.status_code == 403:
            # Unauthorized/forbidden - token missing scopes or expired; caller will treat as no data
            return []
        if r.status_code == 429:
            # rate limited; stop early
            break
        if r.status_code >= 500:
            # transient server error
            break
        r.raise_for_status()
        batch = r.json() or []
        if not batch:
            break
        # normalize minimal subset
        for a in batch:
            items.append({
                "distance": a.get("distance") or 0.0,
                "moving_time": a.get("moving_time") or 0,
                "total_elevation_gain": a.get("total_elevation_gain") or 0.0,
                "start_date": a.get("start_date"),
                "type": a.get("type"),
            })
        page += 1
    return items


def _aggregate_strava(goal_type: str, goal_amount: float, activities: List[Dict[str, Any]]) -> float:
    """Compute ratio (0..1) for supported Strava goal types."""
    if goal_amount is None or float(goal_amount) <= 0:
        return 0.0
    gt = (goal_type or "").lower()
    if gt == "distance_m":
        total = 0.0
        for a in activities:
            try:
                total += float(a.get("distance") or 0.0)
            except Exception:
                pass
        return max(0.0, min(1.0, total / float(goal_amount)))
    if gt == "active_days":
        days = set()
        for a in activities:
            sd = a.get("start_date")
            if not sd:
                continue
            try:
                # Strava start_date is ISO8601 in UTC, e.g., 2023-10-01T08:12:34Z
                dt = _dt.datetime.fromisoformat(sd.replace("Z", "+00:00"))
                days.add(dt.date())
            except Exception:
                continue
        return max(0.0, min(1.0, float(len(days)) / float(goal_amount)))
    # Unsupported goal type for Strava provider
    return 0.0


def _fetch_progress_strava(challenge_id: int, participants: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Fetch Strava-based progress ratios for participants for the challenge window."""
    addr_key = lambda a: str(a).lower()
    meta = _get_challenge_meta(challenge_id)
    if not meta:
        # Missing meta; return None for all
        return {addr_key(p["participant_address"]): None for p in participants}
    start_ts = int(meta.get("start_time") or 0)
    end_ts = int(meta.get("end_time") or 0)
    goal_type = meta.get("goal_type")
    goal_amount = meta.get("goal_amount")

    # Token lookup for provider "strava"
    tokens = _lookup_tokens("strava", participants)

    out: Dict[str, Optional[float]] = {}
    for p in participants:
        addr = addr_key(p["participant_address"])
        tok = tokens.get(addr)
        if not tok:
            out[addr] = None
            continue
        try:
            acts = _strava_fetch_user_activities(tok, start_ts, end_ts)
            ratio = _aggregate_strava(goal_type, goal_amount, acts)
            out[addr] = ratio
        except Exception:
            # On any unexpected error, treat as no data so caller may use a fallback
            out[addr] = None
    return out


def ratio_to_ppm(ratio: float) -> int:
    """Clamp ratio to [0.0,1.0] and convert to parts-per-million integer."""
    if ratio is None:
        return 0
    try:
        r = max(0.0, min(1.0, float(ratio)))
    except (TypeError, ValueError):
        return 0
    return int(round(r * 1_000_000))
