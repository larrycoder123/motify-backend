from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import requests
from datetime import datetime, timezone, timedelta

from app.core.config import settings
from app.models.db import SupabaseDAL

import base64

def _progress_wakatime(
    tokens: Dict[str, Optional[str]], # This will contain the API key string
    participants: List[Dict[str, Any]],
    window: Optional[Tuple[int, int]] = None,
    goal_type: Optional[str] = None,
    goal_amount: int = 1,
) -> Dict[str, Optional[float]]:
    """
    Compute progress ratios for WakaTime-based challenges (coding hours).
    Expects:
    - tokens[address] = WakaTime API key string (e.g., 'waka_xxxxxxxx...')
    - window = (start_time_unix, end_time_unix) defining the challenge period
    - goal_type = "coding_time" or similar (case-insensitive check)
    - goal_amount = integer representing the target number of hours
    Uses WakaTime API: GET /users/current/stats/:range
    """
    addr_key = lambda a: str(a).lower()
    api_base_url = settings.WAKATIME_API_BASE_URL.rstrip('/') # Get base URL from config

    # Define WakaTime range strings based on challenge window
    # WakaTime uses specific strings for predefined ranges.
    # For custom ranges, we might need a different approach or use a default like 'last_7_days' if range doesn't match.
    # For now, let's handle specific common cases or fall back to 'all_time' if custom range is complex.
    range_str = "all_time" # Default fallback
    if window:
        start_dt = datetime.fromtimestamp(window[0], tz=timezone.utc)
        end_dt = datetime.fromtimestamp(window[1], tz=timezone.utc)
        duration = end_dt - start_dt

        # Map common durations to WakaTime ranges
        if duration.days == 6: # last_7_days
            range_str = "last_7_days"
        elif duration.days == 29: # last_30_days
            range_str = "last_30_days"
        # Add more mappings if needed, e.g., last_6_months, last_year
        # For arbitrary ranges, WakaTime API doesn't directly support a start/end date query via this endpoint.
        # We might need to use heartbeats API or stick to predefined ranges for now.
        # Let's assume predefined ranges are used or default to 'all_time' for custom.
        # For a more robust solution, consider fetching heartbeats or using a default range within the challenge window.
        # For now, using 'all_time' as a simple fallback if not matching standard ranges.
        # A more precise solution would require fetching heartbeats between specific timestamps,
        # which is more complex and might require a different WakaTime API endpoint or aggregation logic.
        # Let's use the standard ranges for simplicity based on the window duration.
        # If the duration matches a standard range, use it. Otherwise, default to 'all_time' or use the closest one.
        # We'll map based on the *end* date being today or close to it for standard ranges.
        # If the challenge end time is today, we can use standard ranges like last_7_days, last_30_days.
        # If the challenge ended in the past, we might need to calculate the range string differently or use 'all_time' or a custom approach.
        # For simplicity in this initial implementation, if the range doesn't match standard ones,
        # we'll default to 'all_time'. A more accurate implementation would require fetching stats for the exact period.
        # Standard ranges in WakaTime are relative to 'now'. To get stats for a past period,
        # WakaTime doesn't offer a direct start/end API call for /stats/:range.
        # We could potentially use the heartbeats API (/users/current/heartbeats) with date filters,
        # but it's paginated and more complex.
        # For now, let's use the closest standard range if the end time is recent enough.
        # If the challenge ended more than 30 days ago, 'all_time' might be the only option via /stats/:range.
        # Let's use a heuristic: if end time is within last 30 days, try to match standard ranges.
        # Otherwise, default to 'all_time'.
        now = datetime.now(timezone.utc)
        if end_dt <= now and (now - end_dt).days <= 30: # End is within last 30 days
             if duration.days == 6:
                 range_str = "last_7_days"
             elif duration.days == 29:
                 range_str = "last_30_days"
             # Could add more checks for last_6_months, last_year if end time aligns
             else:
                 # If duration doesn't match standard, but end is recent, defaulting to 'all_time' might be misleading.
                 # A better approach might be to use 'all_time' and filter client-side or use heartbeats.
                 # For now, stick to standard ranges if possible, otherwise 'all_time'.
                 # Let's try to map to the standard ones if the end date matches their typical end.
                 # last_7_days: ends today
                 # last_30_days: ends today
                 # last_6_months: ends today
                 # last_year: ends today
                 # all_time: ... all time
                 # If challenge ended yesterday, standard ranges won't work directly.
                 # Let's assume for now the frontend creates challenges where the end date aligns with standard ranges
                 # or that the user understands the stats might be for a slightly different period if using standard ranges.
                 # This is a limitation of the /stats/:range endpoint.
                 # For precise periods, heartbeats API is needed.
                 # For this implementation, we'll use the standard ranges if they match, else 'all_time'.
                 # A more advanced solution would involve fetching heartbeats.
                 range_str = "all_time" # Default if not matching standard ranges ending *today*

    # Normalize goal type check
    gt = (goal_type or "").lower()
    is_coding_time_goal = "coding" in gt and ("time" in gt or "hour" in gt or "hours" in gt)
    required_hours = max(1, int(goal_amount or 1)) if is_coding_time_goal else 1

    out: Dict[str, Optional[float]] = {}
    for p in participants:
        addr = addr_key(p["participant_address"])
        api_key = tokens.get(addr)

        if not api_key or not api_key.startswith("waka_"): # Validate basic key format
            out[addr] = None
            continue

        try:
            # Prepare Authorization header: Basic + base64(api_key)
            encoded_key = base64.b64encode(api_key.encode()).decode()
            headers = {
                "Authorization": f"Basic {encoded_key}",
                "Accept": "application/json", # Explicitly request JSON
            }

            # Construct the URL for user stats for the specific range
            # Using 'current' user assumes the API key belongs to the user whose stats we want.
            # WakaTime API key is typically tied to a specific user account.
            url = f"{api_base_url}/users/current/stats/{range_str}"

            response = requests.get(url, headers=headers, timeout=25)
            response.raise_for_status() # Raise exception for bad status codes (4xx, 5xx)

            data = response.json()

            # Extract total coding time from the response
            # Use 'total_seconds_including_other_language' as it represents total logged time
            total_seconds = data.get("data", {}).get("total_seconds_including_other_language", 0)
            total_hours = total_seconds / 3600.0 # Convert seconds to hours

            # Calculate ratio based on required hours
            ratio = min(1.0, max(0.0, total_hours / required_hours)) # Clamp ratio between 0 and 1

            out[addr] = round(ratio, 6) # Round for consistency

        except requests.exceptions.HTTPError as e:
             if response.status_code in [401, 403]: # Unauthorized or Forbidden
                 # API key is invalid or lacks scope
                 out[addr] = None
             elif response.status_code == 429: # Rate Limiting
                 # Could handle rate limiting, e.g., retry after delay or return None
                 out[addr] = None # For now, treat as no data
             else:
                 # Other HTTP errors (e.g., 500)
                 out[addr] = None
        except requests.exceptions.RequestException:
            # Network errors, timeouts, etc.
            out[addr] = None
        except (KeyError, ValueError, AttributeError):
            # Issues parsing the response JSON
            out[addr] = None
        except Exception:
             # Catch any other unexpected errors during processing
             out[addr] = None

    return out

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

    # Do not early-return on missing tokens: provider-specific logic may still resolve identities (e.g., Farcaster via wallet)

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
    if (api_type or "").lower() == "farcaster":
        return _progress_farcaster(tokens, participants, window=window, goal_type=goal_type, goal_amount=goal_amount)
    if (api_type or "").lower() == "wakatime":
        return _progress_wakatime(tokens, participants, window=window, goal_type=goal_type, goal_amount=goal_amount)

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


# --- Farcaster (via Neynar) ---

def _progress_farcaster(
    tokens: Dict[str, Optional[str]],
    participants: List[Dict[str, Any]],
    window: Optional[Tuple[int, int]] = None,
    goal_type: Optional[str] = None,
    goal_amount: int = 1,
) -> Dict[str, Optional[float]]:
    """Compute progress ratios for Farcaster-based challenges (post/cast per day).

    Assumptions:
    - tokens[address] contains the participant's Farcaster FID as a string (e.g., "12345").
      If you store OAuth tokens instead, adapt lookup to resolve FID.
    - Requires settings.NEYNAR_API_KEY to call Neynar REST API.
    - goal_type may include "post_per_day", "cast_per_day", or "per_day" to signal daily requirement.
    """
    addr_key = lambda a: str(a).lower()

    # Determine window in UTC days
    if window and window[0] and window[1] and window[1] >= window[0]:
        start_dt = datetime.fromtimestamp(window[0], tz=timezone.utc).date()
        end_dt = datetime.fromtimestamp(window[1], tz=timezone.utc).date()
    else:
        today = datetime.now(tz=timezone.utc).date()
        start_dt = end_dt = today

    # Normalize goal
    gt = (goal_type or "post_per_day").lower()
    required_per_day = max(1, int(goal_amount or 1)) if ("post" in gt or "cast" in gt or "per_day" in gt) else 1

    api_key = settings.NEYNAR_API_KEY
    out: Dict[str, Optional[float]] = {}
    for p in participants:
        addr = addr_key(p["participant_address"])
        fid_or_token = tokens.get(addr)
        # If missing API key, cannot fetch
        if not api_key:
            out[addr] = None
            continue
        # Determine fid: prefer numeric token value; else try resolve via address verification
        fid = None
        if fid_or_token is not None:
            try:
                fid = int(str(fid_or_token).strip())
            except Exception:
                fid = None
        if fid is None:
            # Try Neynar verification mapping
            try:
                fid = _resolve_farcaster_fid_for_address(api_key, addr)
            except Exception:
                fid = None
        if fid is None:
            out[addr] = None
            continue
        try:
            ratio = _farcaster_ratio_for_fid(api_key, fid, start_dt, end_dt, required_per_day)
            out[addr] = ratio
        except Exception:
            out[addr] = None
    return out


def _farcaster_ratio_for_fid(api_key: str, fid: int, start_date, end_date, required_per_day: int) -> float:
    """Return ratio in [0,1] of days meeting the required number of Farcaster casts.

    Uses Neynar API: GET /v2/farcaster/user/casts?fid=...&limit=100&cursor=...
    Requires header: {"x-api-key": <NEYNAR_API_KEY>}.
    """
    headers = {
        "accept": "application/json",
        "x-api-key": api_key,
        # Match docs default; safe to be explicit
        "x-neynar-experimental": "false",
    }
    base_url = settings.FARCASTER_USER_CASTS_URL or "https://api.neynar.com/v2/farcaster/feed/user/casts/"
    params = {"fid": str(fid), "limit": 100, "include_replies": "true"}

    counts_by_day: Dict[str, int] = {}
    start_dt_mid = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)

    pages = 0
    cursor = None
    while pages < 10:  # cap pages
        if cursor:
            params["cursor"] = cursor
        resp = requests.get(base_url, headers=headers, params=params, timeout=20)
        if resp.status_code == 404:
            break
        resp.raise_for_status()
        data = resp.json() or {}
        # Some responses may wrap data in a 'result' object
        if isinstance(data, dict) and "result" in data and isinstance(data["result"], dict):
            data = data["result"]
        casts = data.get("casts") or []
        if not casts:
            break
        stop = False
        for c in casts:
            # Try multiple timestamp fields; Neynar may return ISO strings or epoch numbers
            ts = c.get("timestamp") or c.get("published_at") or c.get("created_at")
            if not ts:
                continue
            try:
                # If ts is numeric (epoch seconds or ms)
                if isinstance(ts, (int, float)) or (isinstance(ts, str) and str(ts).isdigit()):
                    val = int(ts)
                    # Heuristic: >= 10^12 => milliseconds
                    if val > 1_000_000_000_000:
                        dt = datetime.fromtimestamp(val / 1000, tz=timezone.utc)
                    else:
                        dt = datetime.fromtimestamp(val, tz=timezone.utc)
                else:
                    # Assume ISO 8601
                    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except Exception:
                try:
                    dt = datetime.strptime(str(ts), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                except Exception:
                    continue
            if dt < start_dt_mid:
                stop = True
                break
            d = dt.date()
            if d < start_date or d > end_date:
                continue
            key = d.isoformat()
            counts_by_day[key] = counts_by_day.get(key, 0) + 1
        if stop:
            break
        pages += 1
        # Pagination per docs: response contains { next: { cursor: "..." } }
        next_obj = data.get("next")
        if isinstance(next_obj, dict):
            cursor = next_obj.get("cursor")
        elif isinstance(next_obj, str):
            cursor = next_obj
        else:
            cursor = data.get("cursor") or None
        if not cursor:
            break

    total_days = max(1, (end_date - start_date).days + 1)
    met = 0
    cur = start_date
    while cur <= end_date:
        if counts_by_day.get(cur.isoformat(), 0) >= required_per_day:
            met += 1
        cur += timedelta(days=1)
    return round(met / total_days, 6)


def _resolve_farcaster_fid_for_address(api_key: str, address: str) -> Optional[int]:
    """Resolve a Farcaster FID from an EVM wallet using Neynar.

    Resolution order:
      1) Bulk-by-address endpoint (recommended by docs)
      2) Verification-by-address (wallet verified on Farcaster)

    Returns None if not found or on errors.
    """
    addr_lc = str(address).lower()
    # First: bulk-by-address (ETH/SOL)
    try:
        headers = {
            "accept": "application/json",
            "x-api-key": api_key,
            "x-neynar-experimental": "false",
        }
        url = "https://api.neynar.com/v2/farcaster/user/bulk-by-address/"
        resp = requests.get(url, headers=headers, params={"addresses": addr_lc}, timeout=15)
        if resp.status_code == 404:
            pass
        else:
            resp.raise_for_status()
            payload = resp.json() or {}
            # Response is a mapping: { address_lower: [ { user... }, ... ] }
            data = payload.get("result", payload) if isinstance(payload, dict) else {}
            arr = data.get(addr_lc) or data.get(address) or []
            if isinstance(arr, list) and arr:
                fid = (arr[0] or {}).get("fid")
                if fid is not None:
                    return int(fid)
    except Exception:
        # Continue to fallback
        pass

    # Fallback: verification-by-address (requires wallet to be verified on profile)
    try:
        headers = {"accept": "application/json", "x-api-key": api_key}
        url = "https://api.neynar.com/v2/farcaster/verification/by-address"
        resp = requests.get(url, headers=headers, params={"address": addr_lc}, timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        payload = resp.json() or {}
        users = payload.get("users") or payload.get("result") or []
        if isinstance(users, dict):
            fid = users.get("fid")
            return int(fid) if fid is not None else None
        if isinstance(users, list) and users:
            u0 = users[0] or {}
            fid = u0.get("fid")
            return int(fid) if fid is not None else None
    except Exception:
        return None
    return None


# On-chain IdRegistry resolution removed by request; wallet→FID relies on Neynar APIs only.
