from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import requests
from datetime import datetime, timezone, timedelta

from app.core.config import settings
from app.models.db import SupabaseDAL


def _lookup_tokens(api_type: Optional[str], participants: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """Optionally fetch per-user access tokens from Supabase for a given provider.

    Returns dict[address_lower] = token or None.
    Controlled by settings.USER_TOKENS_*; if not set, returns None for all.
    """
    addr_key = lambda a: str(a).lower()
    # If no provider specified; return None tokens
    if not api_type:
        # No provider specified; return None tokens
        return {addr_key(p["participant_address"]): None for p in participants}

    # Provider specified but token lookup not configured: return None tokens to trigger fallback
    if not (settings.USER_TOKENS_TABLE and settings.USER_TOKENS_WALLET_COL and settings.USER_TOKENS_PROVIDER_COL and settings.USER_TOKENS_ACCESS_TOKEN_COL):
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


def fetch_progress(challenge_id: int, participants: List[Dict[str, Any]], api_type: Optional[str] = None) -> Dict[str, Optional[float]]:
    """Stub: return a per-user completion ratio in [0.0, 1.0].

    Keys are participant addresses (lowercased), values are floats.
    Replace this with real API calls to compute completion for each participant.
    """
    addr_key = lambda a: str(a).lower()
    tokens = _lookup_tokens(api_type, participants)  # tokens available when you integrate real provider calls

    # If tokens are not configured/available, return None to trigger DEFAULT_PERCENT_PPM fallback in prepare_run
    if not tokens or all(tokens.get(addr_key(p["participant_address"])) is None for p in participants):
        return {addr_key(p["participant_address"]): None for p in participants}

    # Fetch challenge window and goal from DB (start/end are unix seconds)
    dal = SupabaseDAL.from_env()
    window: Tuple[int, int] | None = None
    goal_type: Optional[str] = None
    goal_amount: int = 1
    if dal:
        try:
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
            if data:
                row = data[0]
                st = int(row.get("start_time") or 0)
                et = int(row.get("end_time") or 0)
                if et and st and et >= st:
                    window = (st, et)
                goal_type = row.get("goal_type")
                try:
                    goal_amount = int(row.get("goal_amount") or 1)
                except Exception:
                    goal_amount = 1
        except Exception:
            window = None

    # Provider-specific logic
    if (api_type or "").lower() == "github":
        return _progress_github(tokens, participants, window=window, goal_type=goal_type, goal_amount=goal_amount)

    # Default for unknown providers: no data
    return {addr_key(p["participant_address"]): None for p in participants}


def _progress_github(
    tokens: Dict[str, Optional[str]],
    participants: List[Dict[str, Any]],
    window: Optional[Tuple[int, int]] = None,
    goal_type: Optional[str] = None,
    goal_amount: int = 1,
) -> Dict[str, Optional[float]]:
    """Compute progress ratios for GitHub-based challenges.

    Uses GitHub GraphQL contributions calendar to count per-day contributions.
    Supports goal_type values like: "contribution_per_day", "push_per_day", "commit_per_day"
    with goal_amount contributions required per UTC calendar day.
    Ratio = days_met / total_days within [start_time, end_time]. If window missing, falls back to today (UTC).

    Note: With scope 'user:email' only public contributions are visible. For private repo commits, add 'repo' scope.
    """
    addr_key = lambda a: str(a).lower()

    # Determine window in UTC days
    if window and window[0] and window[1] and window[1] >= window[0]:
        start_dt = datetime.fromtimestamp(window[0], tz=timezone.utc).date()
        end_dt = datetime.fromtimestamp(window[1], tz=timezone.utc).date()
    else:
        # Default to today's UTC day
        today = datetime.now(tz=timezone.utc).date()
        start_dt = end_dt = today

    total_days = (end_dt - start_dt).days + 1
    total_days = max(1, total_days)

    # Normalize goal (treat push/commit/contribution keywords equivalently)
    gt = (goal_type or "contribution_per_day").lower()
    required_per_day = max(1, int(goal_amount or 1)) if ("push" in gt or "commit" in gt or "contribution" in gt or "per_day" in gt) else 1

    out: Dict[str, Optional[float]] = {}
    for p in participants:
        addr = addr_key(p["participant_address"])
        token = tokens.get(addr)
        if not token:
            out[addr] = None
            continue
        try:
            ratio = _github_ratio_for_user(token, start_dt, end_dt, required_per_day)
            out[addr] = ratio
        except Exception:
            # On failure (rate limit, network, etc.), return None to trigger fallback
            out[addr] = None
    return out


def _github_ratio_for_user(token: str, start_date, end_date, required_per_day: int) -> float:
    """Return ratio in [0.0,1.0] of days meeting the required number of contributions.

    Approach: use GitHub GraphQL contributionsCollection.calendar to fetch per-day contribution counts
    between start_date and end_date (UTC). Counts include public contributions; private counts may
    also appear for the authenticated user depending on token scope and GitHub settings.
    """
    # Build ISO window boundaries (inclusive)
    from_iso = f"{start_date.isoformat()}T00:00:00Z"
    to_iso = f"{end_date.isoformat()}T23:59:59Z"

    q = (
        "query($from: DateTime!, $to: DateTime!) {"
        "  viewer {"
        "    contributionsCollection(from: $from, to: $to) {"
        "      contributionCalendar {"
        "        weeks {"
        "          contributionDays { date contributionCount }"
        "        }"
        "      }"
        "    }"
        "  }"
        "}"
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "motify-backend"
    }
    resp = requests.post(
        "https://api.github.com/graphql",
        json={"query": q, "variables": {"from": from_iso, "to": to_iso}},
        headers=headers,
        timeout=25,
    )
    resp.raise_for_status()
    payload = resp.json()
    if isinstance(payload, dict) and payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL errors: {payload['errors']}")
    weeks = (((payload or {}).get("data") or {}).get("viewer") or {}).get("contributionsCollection", {}).get("contributionCalendar", {}).get("weeks", [])
    days = [d for w in (weeks or []) for d in (w.get("contributionDays") or [])]

    # Build day lookup and compute ratio
    total_days = (end_date - start_date).days + 1
    total_days = max(1, total_days)
    lookup: Dict[str, int] = {str(d.get("date")): int(d.get("contributionCount") or 0) for d in (days or [])}

    met = 0
    cur = start_date
    while cur <= end_date:
        if lookup.get(cur.isoformat(), 0) >= required_per_day:
            met += 1
        cur += timedelta(days=1)

    return round(met / total_days, 6)


def ratio_to_ppm(ratio: float) -> int:
    """Clamp ratio to [0.0,1.0] and convert to parts-per-million integer."""
    if ratio is None:
        return 0
    try:
        r = max(0.0, min(1.0, float(ratio)))
    except (TypeError, ValueError):
        return 0
    return int(round(r * 1_000_000))
