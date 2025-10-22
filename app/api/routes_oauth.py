"""
OAuth routes for linking user wallet addresses with provider accounts.

Flow:
1. Frontend checks status: GET /oauth/status/{provider}/{wallet_address}
2. If no credentials, initiate: GET /oauth/connect/{provider}?wallet_address=0x...
   - Returns auth_url to redirect user to provider (e.g., GitHub)
3. User authorizes on provider site
4. Provider redirects to: GET /oauth/callback/{provider}?code=...&state=...
   - Backend exchanges code for token and stores in DB
   - Redirects user back to frontend with success/error
5. Optional disconnect: DELETE /oauth/disconnect/{provider}/{wallet_address}
"""
from fastapi import APIRouter, HTTPException, Query, Header
from fastapi.responses import RedirectResponse
from typing import Optional
from datetime import datetime, timedelta
import secrets
import logging

from app.models.db import SupabaseDAL
from app.services.oauth import oauth_service
from app.core.config import settings
from app.core.security import verify_wallet_signature

router = APIRouter(prefix="/oauth", tags=["oauth"])

# Simple in-memory state storage (for production, use Redis or DB)
_state_store: dict[str, dict] = {}

@router.get("/wakatime/api-key/{wallet_address}") # Get API key status
async def get_wakatime_api_key_status(
    wallet_address: str,
):
    """
    Check if a wallet address has a Wakatime API key stored.
    """
    db = SupabaseDAL.from_env()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Look up token in database (stored as 'wakatime' provider)
    token_data = db.get_user_token(wallet_address, "wakatime")
    has_api_key = token_data is not None and token_data.get("access_token") is not None

    return {
        "has_api_key": has_api_key,
        "provider": "wakatime",
        "wallet_address": wallet_address.lower(),
    }

@router.post("/wakatime/api-key") # Save or update API key
async def save_wakatime_api_key(
    request: dict, # Using dict for simplicity, could define a Pydantic model
):
    """
    Save or update the Wakatime API key for a wallet address.
    Request body should contain 'wallet_address' and 'api_key'.
    """
    wallet_address = request.get("wallet_address")
    api_key = request.get("api_key")

    if not wallet_address or not api_key:
         raise HTTPException(status_code=400, detail="wallet_address and api_key are required")

    # Basic validation of API key format (starts with 'waka_')
    if not api_key.startswith("waka_"):
        raise HTTPException(status_code=400, detail="Invalid Wakatime API key format")

    db = SupabaseDAL.from_env()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Prepare data for storage
    now = datetime.utcnow()
    # Store the API key in the 'access_token' field for the 'wakatime' provider
    # Wakatime keys don't expire like OAuth tokens, so we don't set expires_at
    db.upsert_user_token({
        "wallet_address": wallet_address.lower(),
        "provider": "wakatime", # Use 'wakatime' as the provider string
        "access_token": api_key, # Store the raw API key string
        "refresh_token": None, # API keys don't have refresh tokens
        "expires_at": None, # API keys don't expire
        "scopes": ["read_stats"], # Define scopes if relevant, otherwise leave empty or as default
        "updated_at": now.isoformat(),
    })

    return {
        "success": True,
        "provider": "wakatime",
        "wallet_address": wallet_address.lower(),
    }

# Optional: Add a route to delete the API key
@router.delete("/wakatime/api-key/{wallet_address}")
async def remove_wakatime_api_key(
    wallet_address: str,
):
    """
    Remove the Wakatime API key for a wallet address.
    """
    db = SupabaseDAL.from_env()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Delete token entry for 'wakatime' provider
    db.delete_user_token(wallet_address, "wakatime")

    return {
        "success": True,
        "provider": "wakatime",
        "wallet_address": wallet_address.lower(),
    }

@router.get("/status/{provider}/{wallet_address}")
async def check_oauth_status(provider: str, wallet_address: str):
    """
    Check if a wallet address has valid OAuth credentials for a provider.

    Returns:
        - has_credentials: bool - whether valid credentials exist
        - provider: str - the provider name
        - wallet_address: str - the wallet address
    """
    db = SupabaseDAL.from_env()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Check if provider is supported
    if not oauth_service.get_provider(provider):
        raise HTTPException(
            status_code=400, detail=f"Provider '{provider}' not supported")

    # Look up token in database
    token_data = db.get_user_token(wallet_address, provider)

    has_credentials = False
    if token_data:
        # Check if token is still valid (if expires_at is set)
        if token_data.get("expires_at"):
            expires_at = datetime.fromisoformat(
                token_data["expires_at"].replace("Z", "+00:00"))
            has_credentials = expires_at > datetime.utcnow()
        else:
            # No expiry means token is valid (like GitHub)
            has_credentials = True

    return {
        "has_credentials": has_credentials,
        "provider": provider,
        "wallet_address": wallet_address.lower(),
    }


@router.get("/connect/{provider}")
async def initiate_oauth(
    provider: str,
    wallet_address: str = Query(..., description="User's wallet address"),
    signature: str = Query(...,
                           description="Signature proving wallet ownership"),
    timestamp: int = Query(...,
                           description="Unix timestamp when signature was created"),
):
    """
    Initiate OAuth flow for a provider.

    Requires signature verification to prevent unauthorized credential linking.

    The signature should be created by signing this message:
    "Connect OAuth provider {provider} to wallet {wallet_address} at {timestamp}"

    Returns a redirect URL that the frontend should navigate to.
    """
    oauth_provider = oauth_service.get_provider(provider)
    if not oauth_provider:
        raise HTTPException(
            status_code=400, detail=f"Provider '{provider}' not supported")

    # Verify wallet ownership via signature
    message = f"Connect OAuth provider {provider} to wallet {wallet_address.lower()} at {timestamp}"
    verify_wallet_signature(wallet_address, message, signature, timestamp)

    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)

    # Store state with wallet address (expires in 10 minutes)
    _state_store[state] = {
        "wallet_address": wallet_address.lower(),
        "provider": provider.lower(),
        "created_at": datetime.utcnow(),
    }

    # Generate authorization URL
    auth_url = oauth_provider.get_authorization_url(state)

    return {
        "auth_url": auth_url,
        "state": state,
    }


@router.get("/callback/{provider}")
async def oauth_callback(
    provider: str,
    code: str = Query(..., description="Authorization code from provider"),
    state: str = Query(..., description="State token for CSRF protection"),
):
    """
    OAuth callback endpoint. Exchanges code for token and stores credentials.

    This endpoint will redirect the user back to the frontend with success/error status.
    """
    # Validate state
    state_data = _state_store.pop(state, None)
    if not state_data:
        # Redirect to frontend with error
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/oauth/result?success=false&error=invalid_state"
        )

    # Check state expiry (10 minutes)
    created_at = state_data["created_at"]
    if (datetime.utcnow() - created_at).total_seconds() > 600:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/oauth/result?success=false&error=expired_state"
        )

    wallet_address = state_data["wallet_address"]
    provider_name = state_data["provider"]

    # Get OAuth provider
    oauth_provider = oauth_service.get_provider(provider_name)
    if not oauth_provider:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/oauth/result?success=false&error=invalid_provider"
        )

    try:
        # Exchange code for token
        token_data = oauth_provider.exchange_code_for_token(code)

        # Get user info (optional, for logging/verification)
        user_info = oauth_provider.get_user_info(token_data["access_token"])
        logging.info(
            f"OAuth successful for {provider_name} user: {user_info.get('login', 'unknown')}")

        # Store token in database
        db = SupabaseDAL.from_env()
        if not db:
            raise Exception("Database not configured")

        # Prepare data for storage
        now = datetime.utcnow()
        expires_at = None
        if token_data.get("expires_in"):
            expires_at = now + timedelta(seconds=token_data["expires_in"])

        db.upsert_user_token({
            "wallet_address": wallet_address,
            "provider": provider_name,
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": expires_at.isoformat() if expires_at else None,
            "scopes": token_data.get("scopes", []),
            "updated_at": now.isoformat(),
        })

        # Redirect to frontend with success
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/oauth/result?success=true&provider={provider_name}"
        )

    except Exception as e:
        logging.error(f"OAuth callback error: {e}")
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/oauth/result?success=false&error=token_exchange_failed"
        )


@router.delete("/disconnect/{provider}/{wallet_address}")
async def disconnect_oauth(
    provider: str,
    wallet_address: str,
    signature: str = Query(...,
                           description="Signature proving wallet ownership"),
    timestamp: int = Query(...,
                           description="Unix timestamp when signature was created"),
):
    """
    Disconnect OAuth credentials for a wallet address and provider.

    Requires signature verification to prevent unauthorized credential removal.

    The signature should be created by signing this message:
    "Disconnect OAuth provider {provider} from wallet {wallet_address} at {timestamp}"
    """
    db = SupabaseDAL.from_env()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")

    # Check if provider is supported
    if not oauth_service.get_provider(provider):
        raise HTTPException(
            status_code=400, detail=f"Provider '{provider}' not supported")

    # Verify wallet ownership via signature
    message = f"Disconnect OAuth provider {provider} from wallet {wallet_address.lower()} at {timestamp}"
    verify_wallet_signature(wallet_address, message, signature, timestamp)

    # Delete token
    db.delete_user_token(wallet_address, provider)

    return {
        "success": True,
        "provider": provider,
        "wallet_address": wallet_address.lower(),
    }


@router.get("/providers")
async def list_providers():
    """List all available OAuth providers."""
    return {
        "providers": oauth_service.list_providers(),
    }
