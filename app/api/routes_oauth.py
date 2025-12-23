"""
OAuth routes for linking user wallet addresses with provider accounts.

Supports GitHub OAuth and WakaTime API key authentication for progress tracking.

Flow:
1. Frontend checks status: GET /oauth/status/{provider}/{wallet_address}
2. If no credentials, initiate: GET /oauth/connect/{provider}?wallet_address=...
   - Returns auth_url to redirect user to provider
3. User authorizes on provider site
4. Provider redirects to: GET /oauth/callback/{provider}?code=...&state=...
   - Backend exchanges code for token and stores in DB
   - Redirects user back to frontend with success/error
5. Optional disconnect: DELETE /oauth/disconnect/{provider}/{wallet_address}
"""

import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.core.security import verify_wallet_signature
from app.models.db import SupabaseDAL
from app.services.oauth import oauth_service

router = APIRouter(prefix="/oauth", tags=["oauth"])

# In-memory state storage for OAuth CSRF protection
# Note: For multi-instance deployments, use Redis or database storage
_state_store: dict[str, dict] = {}


# =============================================================================
# WakaTime API Key Endpoints
# =============================================================================

@router.get("/wakatime/api-key/{wallet_address}")
async def get_wakatime_api_key_status(wallet_address: str):
    """Check if a wallet address has a WakaTime API key stored."""
    db = SupabaseDAL.from_env()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")

    token_data = db.get_user_token(wallet_address, "wakatime")
    has_api_key = token_data is not None and token_data.get("access_token") is not None

    return {
        "has_api_key": has_api_key,
        "provider": "wakatime",
        "wallet_address": wallet_address.lower(),
    }


@router.post("/wakatime/api-key")
async def save_wakatime_api_key(request: dict):
    """
    Save or update the WakaTime API key for a wallet address.
    
    Request body: {"wallet_address": "0x...", "api_key": "waka_..."}
    """
    wallet_address = request.get("wallet_address")
    api_key = request.get("api_key")

    if not wallet_address or not api_key:
        raise HTTPException(status_code=400, detail="wallet_address and api_key are required")

    if not api_key.startswith("waka_"):
        raise HTTPException(status_code=400, detail="Invalid WakaTime API key format")

    db = SupabaseDAL.from_env()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")

    now = datetime.utcnow()
    db.upsert_user_token({
        "wallet_address": wallet_address.lower(),
        "provider": "wakatime",
        "access_token": api_key,
        "refresh_token": None,
        "expires_at": None,
        "scopes": ["read_stats"],
        "updated_at": now.isoformat(),
    })

    return {
        "success": True,
        "provider": "wakatime",
        "wallet_address": wallet_address.lower(),
    }


@router.delete("/wakatime/api-key/{wallet_address}")
async def remove_wakatime_api_key(wallet_address: str):
    """Remove the WakaTime API key for a wallet address."""
    db = SupabaseDAL.from_env()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")

    db.delete_user_token(wallet_address, "wakatime")

    return {
        "success": True,
        "provider": "wakatime",
        "wallet_address": wallet_address.lower(),
    }


# =============================================================================
# OAuth Status & Connection Endpoints
# =============================================================================

@router.get("/status/{provider}/{wallet_address}")
async def check_oauth_status(provider: str, wallet_address: str):
    """
    Check if a wallet address has valid OAuth credentials for a provider.
    
    Returns:
        has_credentials: Whether valid credentials exist
        provider: The provider name
        wallet_address: The wallet address
    """
    db = SupabaseDAL.from_env()
    if not db:
        raise HTTPException(status_code=503, detail="Database not configured")

    if not oauth_service.get_provider(provider):
        raise HTTPException(status_code=400, detail=f"Provider '{provider}' not supported")

    token_data = db.get_user_token(wallet_address, provider)

    has_credentials = False
    if token_data:
        if token_data.get("expires_at"):
            expires_at = datetime.fromisoformat(
                token_data["expires_at"].replace("Z", "+00:00")
            )
            has_credentials = expires_at > datetime.utcnow()
        else:
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
    Returns HTML that communicates with the frontend without causing a full page reload.
    """
    # Validate state
    state_data = _state_store.pop(state, None)
    if not state_data:
        return _render_oauth_result_html(
            success=False,
            error="invalid_state",
            provider=provider
        )

    # Check state expiry (10 minutes)
    created_at = state_data["created_at"]
    if (datetime.utcnow() - created_at).total_seconds() > 600:
        return _render_oauth_result_html(
            success=False,
            error="expired_state",
            provider=provider
        )

    wallet_address = state_data["wallet_address"]
    provider_name = state_data["provider"]

    # Get OAuth provider
    oauth_provider = oauth_service.get_provider(provider_name)
    if not oauth_provider:
        return _render_oauth_result_html(
            success=False,
            error="invalid_provider",
            provider=provider_name
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
            return _render_oauth_result_html(
                success=False,
                error="database_error",
                provider=provider_name
            )

        # Prepare data for storage
        now = datetime.utcnow()
        expires_at = None
        if token_data.get("expires_in"):
            expires_at = (now + timedelta(seconds=token_data["expires_in"])).isoformat()

        db.upsert_user_token({
            "wallet_address": wallet_address.lower(),
            "provider": provider_name,
            "access_token": token_data["access_token"],
            "refresh_token": token_data.get("refresh_token"),
            "expires_at": expires_at,
            "scopes": token_data.get("scopes", []),
            "updated_at": now.isoformat(),
        })

        return _render_oauth_result_html(
            success=True,
            provider=provider_name,
            wallet_address=wallet_address
        )

    except Exception as e:
        logging.error(f"OAuth callback error: {e}")
        return _render_oauth_result_html(
            success=False,
            error="token_exchange_failed",
            provider=provider_name
        )


def _render_oauth_result_html(
    success: bool,
    provider: str,
    error: str | None = None,
    wallet_address: str | None = None
) -> HTMLResponse:
    """
    Render HTML page that communicates OAuth result back to the main app.
    Uses localStorage to pass data between this page and the main app.
    """
    result_data = {
        "success": success,
        "provider": provider,
        "timestamp": int(datetime.utcnow().timestamp() * 1000)
    }
    if error:
        result_data["error"] = error
    if wallet_address:
        result_data["wallet_address"] = wallet_address

    import json
    result_json = json.dumps(result_data)
    
    # Determine status class for styling
    status_class = "success" if success else "error"
    status_text = "Authentication Successful!" if success else "Authentication Failed"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>OAuth {'Success' if success else 'Error'}</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}

            body {{
                font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                background: hsl(222.2 84% 4.9%);
                color: hsl(210 40% 98%);
                padding: 1rem;
            }}

            .container {{
                max-width: 28rem;
                width: 100%;
                text-align: center;
            }}

            .card {{
                background: linear-gradient(to bottom right, 
                    hsl(222.2 47.4% 11.2%), 
                    hsl(222.2 47.4% 11.2% / 0.5));
                border: 1px solid hsl(217.2 32.6% 17.5% / 0.5);
                border-radius: 0.75rem;
                padding: 2rem;
                box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1);
                transition: border-color 0.2s;
            }}

            .icon-container {{
                width: 4rem;
                height: 4rem;
                margin: 0 auto 1.5rem;
                border-radius: 0.75rem;
                display: flex;
                align-items: center;
                justify-content: center;
            }}

            .icon-container.success {{
                background: hsl(142.1 76.2% 36.3% / 0.1);
            }}

            .icon-container.error {{
                background: hsl(0 84.2% 60.2% / 0.1);
            }}

            .spinner {{
                border: 3px solid hsl(217.2 32.6% 17.5%);
                border-radius: 50%;
                border-top-color: hsl(210 40% 98%);
                width: 2.5rem;
                height: 2.5rem;
                animation: spin 1s linear infinite;
            }}

            .checkmark, .cross {{
                width: 2.5rem;
                height: 2.5rem;
            }}

            .checkmark {{
                color: hsl(142.1 76.2% 36.3%);
            }}

            .cross {{
                color: hsl(0 84.2% 60.2%);
            }}

            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}

            h2 {{
                font-size: 1.875rem;
                font-weight: 700;
                margin-bottom: 0.75rem;
                line-height: 1.2;
            }}

            p {{
                color: hsl(215 20.2% 65.1%);
                font-size: 1rem;
                line-height: 1.5;
            }}

            .success-text {{
                color: hsl(142.1 76.2% 36.3%);
            }}

            .error-text {{
                color: hsl(0 84.2% 60.2%);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <div class="icon-container {status_class}">
                    <div class="spinner"></div>
                </div>
                <h2 class="{status_class}-text">
                    {status_text}
                </h2>
                <p>Redirecting back to Motify...</p>
            </div>
        </div>
        <script>
            (function() {{
                const result = {result_json};
                
                // Store result in localStorage so the main app can read it
                localStorage.setItem('oauth_result', JSON.stringify(result));
                
                // Update icon after a moment
                setTimeout(() => {{
                    const spinner = document.querySelector('.spinner');
                    if (spinner) {{
                        const success = {str(success).lower()};
                        spinner.outerHTML = success 
                            ? '<svg class="checkmark" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>'
                            : '<svg class="cross" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>';
                    }}
                }}, 500);
                
                // Redirect back to the main app
                setTimeout(() => {{
                    window.location.href = '{settings.FRONTEND_URL}/oauth/result';
                }}, 1500);
            }})();
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


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
