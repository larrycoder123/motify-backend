# Frontend-Backend Endpoint Flow Analysis

## Overview
This document provides a complete end-to-end analysis of all endpoints that the frontend interacts with on the Render-hosted backend. Each endpoint's full flow, requirements, error cases, and troubleshooting steps are documented.

---

## Table of Contents
1. [Health Endpoint](#1-health-endpoint)
2. [Stats Endpoint](#2-stats-endpoint)
3. [OAuth Endpoints](#3-oauth-endpoints)
   - [OAuth Status](#3a-oauth-status)
   - [OAuth Connect](#3b-oauth-connect)
   - [OAuth Callback](#3c-oauth-callback)
   - [OAuth Disconnect](#3d-oauth-disconnect)
   - [OAuth Providers List](#3e-oauth-providers-list)

---

## 1. Health Endpoint

### Endpoint
```
GET /health
```

### Purpose
Quick health check to verify backend is running and database is accessible.

### Frontend Usage
```javascript
// Check if backend is alive
const response = await fetch('https://your-service.onrender.com/health');
const data = await response.json();
// { ok: true, db: true }
```

### Complete Flow

#### Step 1: Request Received
```
Frontend → GET /health → FastAPI app
```

#### Step 2: CORS Processing
**File:** `app/main.py`

```python
# CORS middleware checks origin
origin = request.headers.get("origin")

# Allowed origins:
- http://localhost:3000, http://localhost:5173, http://localhost:8080
- https://motify-nine.vercel.app
- https://*.vercel.app (any Vercel preview deployment)

# If origin matches:
- Sets Access-Control-Allow-Origin header
- Sets Access-Control-Allow-Credentials: true
```

**⚠️ Common Issue:** If frontend origin not in allowed list, CORS error occurs.

#### Step 3: Route Handler
**File:** `app/api/routes_health.py`

```python
@router.get("/health")
async def health():
    # 1. Try to create Supabase client
    dal = SupabaseDAL.from_env()
    db_ok = False
    
    if dal:
        # 2. Probe multiple tables to verify DB connectivity
        probes = [
            ("user_tokens", "wallet_address"),
            ("chain_challenges", "contract_address"),
            ("finished_challenges", "contract_address"),
        ]
        
        # 3. Try each table until one succeeds
        for table, col in probes:
            try:
                dal.client.table(table).select(col).limit(1).execute()
                db_ok = True
                break  # Success! Stop probing
            except Exception:
                continue  # Try next table
    
    # 4. Return result
    return {"ok": True, "db": db_ok}
```

#### Step 4: Database Connection
**File:** `app/models/db.py`

```python
@classmethod
def from_env(cls) -> Optional["SupabaseDAL"]:
    # Requires either SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY
    # Or SUPABASE_URL + SUPABASE_ANON_KEY
    if settings.SUPABASE_URL and (settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY):
        key = settings.SUPABASE_SERVICE_ROLE_KEY or settings.SUPABASE_ANON_KEY
        return cls(settings.SUPABASE_URL, key)
    return None  # Not configured
```

#### Step 5: Response to Frontend
```json
{
  "ok": true,
  "db": true
}
```

### Environment Variables Required
```bash
# Optional but recommended for db:true:
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...  # OR SUPABASE_ANON_KEY
```

### Success Scenarios
| Case | Response |
|------|----------|
| Backend up, DB configured and accessible | `{"ok": true, "db": true}` |
| Backend up, DB not configured | `{"ok": true, "db": false}` |
| Backend up, DB configured but unreachable | `{"ok": true, "db": false}` |

### Error Scenarios
| Case | Status | Response |
|------|--------|----------|
| Backend down | - | Connection timeout/refused |
| CORS error | 200 | Response blocked by browser |
| Unhandled exception | 500 | `{"error": {...}}` |

### Troubleshooting

#### Problem: `db: false` but env vars are set
**Check:**
1. **Supabase URL format:** Must be `https://xxxxx.supabase.co` (no trailing slash)
2. **Service role key format:** Should be a long JWT starting with `eyJhbGci...`
3. **Network:** Render can reach Supabase (check Render logs for connection errors)
4. **Tables exist:** Run SQL in Supabase dashboard:
   ```sql
   SELECT * FROM user_tokens LIMIT 1;
   SELECT * FROM chain_challenges LIMIT 1;
   SELECT * FROM finished_challenges LIMIT 1;
   ```

#### Problem: CORS error in browser console
**Check:**
1. **Frontend origin:** Must be in `allow_origins` list in `app/main.py`
2. **Render URL:** Ensure BACKEND_URL env var matches actual Render service URL
3. **Browser console:** Look for exact origin being sent
4. **Fix:** Add origin to allowed list and redeploy

---

## 2. Stats Endpoint

### Endpoint
```
GET /stats/user?wallet=0x1234...
```

### Purpose
Fetch user statistics from completed challenges (wagered amount, success rate, donations).

### Frontend Usage
```javascript
const wallet = "0x1234567890123456789012345678901234567890";
const response = await fetch(
  `https://your-service.onrender.com/stats/user?wallet=${wallet}`
);
const data = await response.json();
// {
//   wallet: "0x1234...",
//   challenges_completed: 5,
//   success_percentage_overall: 75.5,
//   total_wagered: 100.50,
//   total_donations: 25.00
// }
```

### Complete Flow

#### Step 1: Request Validation
**File:** `app/api/routes_stats.py`

```python
@router.get("/user")
def get_user_stats(wallet: str = Query(..., description="User wallet address")):
    # 1. Validate wallet parameter present
    if not wallet:
        raise HTTPException(status_code=400, detail="wallet is required")
    
    # 2. Try to create Supabase client
    dal = SupabaseDAL.from_env()
    if not dal:
        raise HTTPException(status_code=500, detail="Supabase not configured")
```

**⚠️ Required Query Param:** `wallet` must be provided, otherwise 400 error.

#### Step 2: Database Query
```python
# 3. Normalize wallet address to lowercase for case-insensitive match
w = wallet.lower()

# 4. Query finished_participants table
resp = (
    dal.client
    .table("finished_participants")
    .select("challenge_id,contract_address,stake_minor_units,percent_ppm")
    .ilike("contract_address", settings.MOTIFY_CONTRACT_ADDRESS)  # Case-insensitive match
    .ilike("participant_address", w)  # Case-insensitive match
    .limit(5000)
    .execute()
)

# 5. Extract data from response (handles different supabase-py versions)
data = resp.data if hasattr(resp, "data") else (resp.model_dump().get("data") if hasattr(resp, "model_dump") else [])
```

**Database Table:** `finished_participants`
- **Purpose:** Archived results for completed challenges
- **Filter:** Only rows matching the contract address and participant wallet
- **Limit:** 5000 rows (enough for most users)

#### Step 3: Empty Data Handling
```python
if not data:
    # User has no completed challenges yet
    return {
        "wallet": wallet,
        "challenges_completed": 0,
        "success_percentage_overall": 0.0,
        "total_wagered": 0.0,
        "total_donations": 0.0,
    }
```

#### Step 4: Aggregation Logic
```python
# Get token decimals from settings (e.g., 6 for USDC)
dec = int(settings.STAKE_TOKEN_DECIMALS or 0)
denom = float(10 ** dec)  # e.g., 1_000_000 for 6 decimals

total_stake_minor = 0
total_donation_minor = 0
perc_list = []
seen = set()

for row in data:
    # Deduplicate by (contract_address, challenge_id)
    key = (row.get("contract_address"), int(row.get("challenge_id", 0)))
    if key in seen:
        continue  # Skip duplicate
    seen.add(key)
    
    # Extract values
    stake_minor = int(row.get("stake_minor_units") or 0)
    ppm = int(row.get("percent_ppm") or 0)
    
    # Accumulate totals
    total_stake_minor += stake_minor
    
    # Donation = stake * (1 - percent)
    # If percent_ppm = 750000 (75%), user gets 75% refund, 25% goes to donation
    donation = stake_minor * (1 - (ppm / 1_000_000))
    total_donation_minor += int(donation)
    
    # Collect percentage for averaging
    perc_list.append(ppm)
```

**Key Calculation:**
- `percent_ppm` is parts-per-million: 1,000,000 = 100%
- User refund = stake × (percent_ppm / 1,000,000)
- Donation = stake × (1 - percent_ppm / 1,000,000)

#### Step 5: Response Computation
```python
challenges_completed = len(seen)

# Average success percentage: convert PPM to percentage (0-100)
# sum(perc_list) / len(perc_list) gives average PPM
# Divide by 10,000 to convert to percentage (0-100)
success_percentage_overall = (sum(perc_list) / (len(perc_list) * 10_000)) if perc_list else 0.0

# Convert minor units to display units
total_wagered = total_stake_minor / denom
total_donations = total_donation_minor / denom

return {
    "wallet": wallet,
    "challenges_completed": challenges_completed,
    "success_percentage_overall": round(success_percentage_overall, 2),
    "total_wagered": float(total_wagered),
    "total_donations": float(total_donations),
}
```

### Environment Variables Required
```bash
# Required:
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...

# Required:
MOTIFY_CONTRACT_ADDRESS=0x53Da03A36Aa9333C41C5521A113d0f8BA028bC43

# Required:
STAKE_TOKEN_DECIMALS=6  # For USDC (6 decimals)
```

### Success Response
```json
{
  "wallet": "0x1234567890123456789012345678901234567890",
  "challenges_completed": 5,
  "success_percentage_overall": 75.50,
  "total_wagered": 100.50,
  "total_donations": 25.00
}
```

### Error Scenarios
| Case | Status | Response |
|------|--------|----------|
| Missing `wallet` param | 400 | `{"detail": "wallet is required"}` |
| Supabase not configured | 500 | `{"detail": "Supabase not configured"}` |
| Invalid wallet format | 200 | Returns zeros (no matches) |
| Database query error | 500 | Exception handled by global handler |

### Troubleshooting

#### Problem: Always returns zeros
**Check:**
1. **Wallet address format:** Should be checksummed or lowercase (backend handles both)
2. **Contract address:** Must match `MOTIFY_CONTRACT_ADDRESS` in env
3. **Database data:**
   ```sql
   SELECT * FROM finished_participants 
   WHERE LOWER(participant_address) = LOWER('0xYourWallet')
   LIMIT 10;
   ```
4. **Challenge archival:** Stats only show for challenges that have been archived via `archive_and_cleanup()`

#### Problem: Wrong amounts
**Check:**
1. **STAKE_TOKEN_DECIMALS:** Should be `6` for USDC, `18` for ETH
2. **Calculation verification:**
   ```python
   # If stake_minor_units = 1000000 and STAKE_TOKEN_DECIMALS = 6:
   # Display amount = 1000000 / 10^6 = 1.0 USDC
   ```

---

## 3. OAuth Endpoints

### Purpose
Enable users to link their wallet addresses with provider accounts (GitHub, Farcaster) to enable progress tracking for challenges.

### OAuth Flow Overview
```
1. Frontend: User clicks "Connect GitHub"
   ↓
2. Frontend: Signs message with wallet to prove ownership
   ↓
3. Frontend: Calls /oauth/connect/github with signature
   ↓
4. Backend: Verifies signature, generates state token, returns auth_url
   ↓
5. Frontend: Redirects user to GitHub authorization page
   ↓
6. User: Authorizes app on GitHub
   ↓
7. GitHub: Redirects to /oauth/callback/github?code=...&state=...
   ↓
8. Backend: Exchanges code for token, stores in DB, redirects to frontend
   ↓
9. Frontend: Receives success/error and updates UI
```

---

## 3a. OAuth Status

### Endpoint
```
GET /oauth/status/{provider}/{wallet_address}
```

### Purpose
Check if a wallet address has valid OAuth credentials for a provider.

### Frontend Usage
```javascript
const provider = "github";
const wallet = "0x1234...";
const response = await fetch(
  `https://your-service.onrender.com/oauth/status/${provider}/${wallet}`
);
const data = await response.json();
// { has_credentials: true, provider: "github", wallet_address: "0x1234..." }
```

### Complete Flow

#### Step 1: Route Parsing
**File:** `app/api/routes_oauth.py`

```python
@router.get("/status/{provider}/{wallet_address}")
async def check_oauth_status(provider: str, wallet_address: str):
    # 1. Parse path parameters
    # provider = "github"
    # wallet_address = "0x1234..."
```

#### Step 2: Database Check
```python
# 2. Get Supabase client
db = SupabaseDAL.from_env()
if not db:
    raise HTTPException(status_code=503, detail="Database not configured")

# 3. Verify provider is supported
if not oauth_service.get_provider(provider):
    raise HTTPException(
        status_code=400, detail=f"Provider '{provider}' not supported")

# 4. Look up token in database
token_data = db.get_user_token(wallet_address, provider)
```

**Database Query:** `app/models/db.py`
```python
def get_user_token(self, wallet_address: str, provider: str) -> Optional[Dict[str, Any]]:
    result = (
        self.client
        .table("user_tokens")
        .select("*")
        .eq("wallet_address", wallet_address.lower())  # Lowercased!
        .eq("provider", provider.lower())
        .execute()
    )
    return result.data[0] if result.data else None
```

**⚠️ Important:** Wallet addresses are stored **lowercased** in database for consistency.

#### Step 3: Token Validation
```python
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
```

**Token Expiry Logic:**
- GitHub tokens: No expiry (valid until revoked)
- Future providers may have `expires_at` field

#### Step 4: Response
```python
return {
    "has_credentials": has_credentials,
    "provider": provider,
    "wallet_address": wallet_address.lower(),  # Normalized
}
```

### Environment Variables Required
```bash
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...
```

### Success Response
```json
{
  "has_credentials": true,
  "provider": "github",
  "wallet_address": "0x1234567890123456789012345678901234567890"
}
```

### Error Scenarios
| Case | Status | Response |
|------|--------|----------|
| Provider not supported | 400 | `{"detail": "Provider 'xxx' not supported"}` |
| Database not configured | 503 | `{"detail": "Database not configured"}` |
| Token expired | 200 | `{"has_credentials": false, ...}` |
| No token found | 200 | `{"has_credentials": false, ...}` |

---

## 3b. OAuth Connect

### Endpoint
```
GET /oauth/connect/{provider}?wallet_address=0x...&signature=0x...&timestamp=1234567890
```

### Purpose
Initiate OAuth flow by generating authorization URL after verifying wallet ownership.

### Frontend Usage
```javascript
// Step 1: Create message to sign
const timestamp = Math.floor(Date.now() / 1000);
const message = `Connect OAuth provider github to wallet ${wallet.toLowerCase()} at ${timestamp}`;

// Step 2: Sign message with wallet
const signature = await signer.signMessage(message);

// Step 3: Call backend
const response = await fetch(
  `https://your-service.onrender.com/oauth/connect/github?` +
  `wallet_address=${wallet}&signature=${signature}&timestamp=${timestamp}`
);
const data = await response.json();
// { auth_url: "https://github.com/login/oauth/authorize?...", state: "abc123..." }

// Step 4: Redirect user to auth_url
window.location.href = data.auth_url;
```

### Complete Flow

#### Step 1: Parameter Validation
**File:** `app/api/routes_oauth.py`

```python
@router.get("/connect/{provider}")
async def initiate_oauth(
    provider: str,
    wallet_address: str = Query(..., description="User's wallet address"),
    signature: str = Query(..., description="Signature proving wallet ownership"),
    timestamp: int = Query(..., description="Unix timestamp when signature was created"),
):
    # 1. Parse all required parameters
    # All must be present or 422 error
```

#### Step 2: Provider Check
```python
# 2. Verify provider is supported
oauth_provider = oauth_service.get_provider(provider)
if not oauth_provider:
    raise HTTPException(
        status_code=400, detail=f"Provider '{provider}' not supported")
```

**Provider Registration:** `app/services/oauth.py`
```python
def _register_providers(self):
    # Only registers if env vars are set
    if settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET:
        self._providers["github"] = GitHubOAuthProvider()
```

**⚠️ Critical:** GitHub provider only available if `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` are set in environment.

#### Step 3: Signature Verification
**File:** `app/core/security.py`

```python
# 3. Verify wallet ownership via signature
message = f"Connect OAuth provider {provider} to wallet {wallet_address.lower()} at {timestamp}"
verify_wallet_signature(wallet_address, message, signature, timestamp)
```

**Signature Verification Process:**
```python
def verify_wallet_signature(wallet_address, message, signature, timestamp, max_age_seconds=300):
    # A. Check timestamp freshness (within 5 minutes)
    now = int(time.time())
    if abs(now - timestamp) > max_age_seconds:
        raise HTTPException(401, "Signature timestamp is too old or in the future")
    
    # B. Normalize wallet address to checksum format
    wallet_address = Web3.to_checksum_address(wallet_address)
    
    # C. Encode message (EIP-191 format)
    message_hash = encode_defunct(text=message)
    
    # D. Recover signer address from signature
    recovered_address = Account.recover_message(message_hash, signature=signature)
    
    # E. Compare addresses (case-insensitive)
    if recovered_address.lower() != wallet_address.lower():
        raise HTTPException(401, "Signature does not match wallet address")
    
    return True
```

**⚠️ Security Requirements:**
1. **Message format must match exactly:**
   ```
   Connect OAuth provider {provider} to wallet {wallet_lowercase} at {timestamp}
   ```
2. **Timestamp must be within 5 minutes** (prevents replay attacks)
3. **Signature must be created by wallet owner** (prevents unauthorized linking)

#### Step 4: State Token Generation
```python
import secrets

# 4. Generate state token for CSRF protection (32 bytes = 43 chars base64url)
state = secrets.token_urlsafe(32)

# 5. Store state with wallet address (expires in 10 minutes)
_state_store[state] = {
    "wallet_address": wallet_address.lower(),
    "provider": provider.lower(),
    "created_at": datetime.utcnow(),
}
```

**⚠️ In-Memory Storage:** Currently uses in-memory dict. For production with multiple workers, consider Redis or database.

#### Step 5: Authorization URL Generation
**File:** `app/services/oauth.py` (GitHubOAuthProvider)

```python
def get_authorization_url(self, state: str) -> str:
    # Build redirect_uri from BACKEND_URL
    base = settings.BACKEND_URL or "http://localhost:8000"
    self.redirect_uri = f"{base.rstrip('/')}/oauth/callback/github"
    
    # Build GitHub authorization URL
    params = {
        "client_id": self.client_id,
        "redirect_uri": self.redirect_uri,  # MUST match GitHub OAuth App setting!
        "scope": self.scope,  # "user:email" for public contributions
        "state": state,  # CSRF protection
    }
    return f"https://github.com/login/oauth/authorize?{urlencode(params)}"
```

**⚠️ Critical Alignment:**
```
settings.BACKEND_URL = "https://motify-backend.onrender.com"
                         ↓
redirect_uri = "https://motify-backend.onrender.com/oauth/callback/github"
                         ↓
MUST EXACTLY MATCH GitHub OAuth App callback URL setting!
```

#### Step 6: Response
```python
return {
    "auth_url": auth_url,  # User will be redirected here
    "state": state,        # Frontend can store for verification (optional)
}
```

### Environment Variables Required
```bash
# Required:
GITHUB_CLIENT_ID=Ov23liT3dBZYgNsoydbR
GITHUB_CLIENT_SECRET=692d8ee0cd17955bc46f97167a6ffbc703becb45

# Critical - must match OAuth app callback exactly:
BACKEND_URL=https://motify-backend.onrender.com  # NO trailing slash!

# For redirecting back to frontend after OAuth:
FRONTEND_URL=https://motify.live
```

### Success Response
```json
{
  "auth_url": "https://github.com/login/oauth/authorize?client_id=Ov23li...&redirect_uri=https%3A%2F%2Fmotify-backend.onrender.com%2Foauth%2Fcallback%2Fgithub&scope=user%3Aemail&state=abc123xyz...",
  "state": "abc123xyz..."
}
```

### Error Scenarios
| Case | Status | Response |
|------|--------|----------|
| Missing query params | 422 | Validation error |
| Provider not supported | 400 | `{"detail": "Provider 'xxx' not supported"}` |
| Invalid signature | 401 | `{"detail": "Signature does not match wallet address"}` |
| Signature too old | 401 | `{"detail": "Signature timestamp is too old..."}` |
| Invalid signature format | 400 | `{"detail": "Invalid signature format: ..."}` |

### Troubleshooting

#### Problem: "Provider 'github' not supported"
**Root Cause:** GitHub provider not registered because env vars missing.

**Check:**
```bash
# In Render dashboard, verify these are set:
GITHUB_CLIENT_ID=Ov23liT3dBZYgNsoydbR
GITHUB_CLIENT_SECRET=692d8ee0cd17955bc46f97167a6ffbc703becb45
```

**Verification:** Check logs during startup for provider registration.

#### Problem: "Signature does not match wallet address"
**Root Cause:** Message format mismatch or wrong wallet signed.

**Check:**
1. **Message format exact:** `Connect OAuth provider github to wallet 0xabc... at 1234567890`
2. **Wallet address lowercase:** Must use `wallet.toLowerCase()` in message
3. **Provider name lowercase:** Must use `"github"` not `"GitHub"`
4. **Signer:** Must be the same wallet address in the message

**Frontend Fix:**
```javascript
const message = `Connect OAuth provider ${provider.toLowerCase()} to wallet ${wallet.toLowerCase()} at ${timestamp}`;
```

#### Problem: "Signature timestamp is too old"
**Root Cause:** More than 5 minutes elapsed between signature creation and API call.

**Fix:** Generate timestamp and signature right before API call, not earlier.

---

## 3c. OAuth Callback

### Endpoint
```
GET /oauth/callback/{provider}?code=abc123&state=xyz789
```

### Purpose
Receive authorization code from OAuth provider, exchange for access token, store in database, and redirect user back to frontend.

### Flow (GitHub redirects here)
```
User authorizes on GitHub
   ↓
GitHub redirects to: https://your-backend.onrender.com/oauth/callback/github?code=abc123&state=xyz789
   ↓
Backend processes callback
   ↓
Backend redirects to: https://motify.live/oauth/result?success=true&provider=github
```

### Complete Flow

#### Step 1: State Validation
**File:** `app/api/routes_oauth.py`

```python
@router.get("/callback/{provider}")
async def oauth_callback(
    provider: str,
    code: str = Query(..., description="Authorization code from provider"),
    state: str = Query(..., description="State token for CSRF protection"),
):
    # 1. Validate state token exists
    state_data = _state_store.pop(state, None)
    if not state_data:
        # State not found (expired or invalid)
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/oauth/result?success=false&error=invalid_state"
        )
    
    # 2. Check state expiry (10 minutes from creation)
    created_at = state_data["created_at"]
    if (datetime.utcnow() - created_at).total_seconds() > 600:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/oauth/result?success=false&error=expired_state"
        )
    
    # 3. Extract wallet and provider from state
    wallet_address = state_data["wallet_address"]
    provider_name = state_data["provider"]
```

**⚠️ CSRF Protection:** State token ensures callback matches the original connect request.

#### Step 2: Provider Lookup
```python
# 4. Get OAuth provider instance
oauth_provider = oauth_service.get_provider(provider_name)
if not oauth_provider:
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/oauth/result?success=false&error=invalid_provider"
    )
```

#### Step 3: Token Exchange
**File:** `app/services/oauth.py` (GitHubOAuthProvider)

```python
def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
    # POST to GitHub token endpoint
    response = requests.post(
        "https://github.com/login/oauth/access_token",
        headers={"Accept": "application/json"},
        data={
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,  # Must match!
        },
    )
    response.raise_for_status()
    data = response.json()
    
    return {
        "access_token": data.get("access_token"),
        "refresh_token": None,  # GitHub doesn't provide
        "expires_in": None,     # GitHub tokens don't expire
        "scopes": data.get("scope", "").split(",") if data.get("scope") else [],
    }
```

**⚠️ Common Error:** If `redirect_uri` doesn't match what was sent in authorization URL, GitHub returns error.

#### Step 4: User Info Retrieval (Optional)
```python
# Get user info for logging/verification
user_info = oauth_provider.get_user_info(token_data["access_token"])
logging.info(f"OAuth successful for {provider_name} user: {user_info.get('login', 'unknown')}")
```

**GitHub API Call:**
```python
def get_user_info(self, access_token: str) -> Dict[str, Any]:
    response = requests.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
    )
    response.raise_for_status()
    return response.json()  # Contains: login, id, email, etc.
```

#### Step 5: Database Storage
```python
# Prepare data for storage
now = datetime.utcnow()
expires_at = None
if token_data.get("expires_in"):
    expires_at = now + timedelta(seconds=token_data["expires_in"])

db.upsert_user_token({
    "wallet_address": wallet_address,  # Lowercased
    "provider": provider_name,
    "access_token": token_data["access_token"],
    "refresh_token": token_data.get("refresh_token"),
    "expires_at": expires_at.isoformat() if expires_at else None,
    "scopes": token_data.get("scopes", []),
    "updated_at": now.isoformat(),
})
```

**Database Table:** `user_tokens`
```sql
-- Primary key: (wallet_address, provider)
-- Upsert replaces existing token if user reconnects
```

#### Step 6: Success Redirect
```python
# Redirect to frontend with success
return RedirectResponse(
    url=f"{settings.FRONTEND_URL}/oauth/result?success=true&provider={provider_name}"
)
```

**Frontend receives:** `https://motify.live/oauth/result?success=true&provider=github`

#### Error Handling
```python
except Exception as e:
    logging.error(f"OAuth callback error: {e}")
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/oauth/result?success=false&error=token_exchange_failed"
    )
```

### Environment Variables Required
```bash
# Required:
GITHUB_CLIENT_ID=Ov23liT3dBZYgNsoydbR
GITHUB_CLIENT_SECRET=692d8ee0cd17955bc46f97167a6ffbc703becb45
BACKEND_URL=https://motify-backend.onrender.com
FRONTEND_URL=https://motify.live

# Required:
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...
```

### Success Flow
```
1. User clicks "Connect GitHub" on frontend
2. Frontend calls /oauth/connect/github with signature
3. Backend returns auth_url
4. Frontend redirects user to GitHub
5. User authorizes app
6. GitHub redirects to: /oauth/callback/github?code=abc&state=xyz
7. Backend exchanges code for token
8. Backend stores token in user_tokens table
9. Backend redirects to: https://motify.live/oauth/result?success=true&provider=github
10. Frontend shows success message and updates UI
```

### Error Scenarios
| Case | Redirect To |
|------|-------------|
| Invalid/expired state | `FRONTEND_URL/oauth/result?success=false&error=invalid_state` |
| State expired (>10 min) | `FRONTEND_URL/oauth/result?success=false&error=expired_state` |
| Provider not found | `FRONTEND_URL/oauth/result?success=false&error=invalid_provider` |
| Token exchange fails | `FRONTEND_URL/oauth/result?success=false&error=token_exchange_failed` |
| Database error | `FRONTEND_URL/oauth/result?success=false&error=token_exchange_failed` |

### Troubleshooting

#### Problem: "redirect_uri_mismatch" from GitHub
**Root Cause:** Mismatch between callback URL and GitHub OAuth App setting.

**Check GitHub OAuth App Settings:**
1. Go to https://github.com/settings/developers
2. Click your OAuth App
3. Check "Authorization callback URL"

**Must match exactly:**
```
GitHub OAuth App setting: https://motify-backend.onrender.com/oauth/callback/github
                            ↓ must match exactly ↓
Render env var BACKEND_URL: https://motify-backend.onrender.com
```

**Common mistakes:**
- Trailing slash: `https://motify-backend.onrender.com/` ❌
- Wrong scheme: `http://` instead of `https://` ❌
- Localhost in GitHub: `http://localhost:8000/oauth/callback/github` (for local dev only)

**Fix:**
1. **For local dev:**
   ```bash
   # .env file:
   BACKEND_URL=http://localhost:8000
   
   # GitHub OAuth App callback:
   http://localhost:8000/oauth/callback/github
   ```

2. **For production (Render):**
   ```bash
   # Render env var:
   BACKEND_URL=https://motify-backend.onrender.com
   
   # GitHub OAuth App callback:
   https://motify-backend.onrender.com/oauth/callback/github
   ```

#### Problem: User redirected with "invalid_state"
**Root Causes:**
1. **State expired (>10 minutes):** User took too long to authorize
2. **Server restart:** In-memory state store cleared
3. **Multiple workers:** State stored on different worker

**Solutions:**
1. **Short-term:** Users should complete OAuth flow within 10 minutes
2. **Long-term:** Use Redis or database for state storage (production-ready)

#### Problem: Token not saved in database
**Check:**
1. **Supabase connection:** Verify `SUPABASE_SERVICE_ROLE_KEY` is set
2. **Table exists:**
   ```sql
   SELECT * FROM user_tokens LIMIT 1;
   ```
3. **Logs:** Check Render logs for database errors
4. **RLS policies:** Ensure service role can write to user_tokens (should bypass RLS)

---

## 3d. OAuth Disconnect

### Endpoint
```
DELETE /oauth/disconnect/{provider}/{wallet_address}?signature=0x...&timestamp=1234567890
```

### Purpose
Remove OAuth credentials for a wallet address and provider.

### Frontend Usage
```javascript
// Step 1: Create message to sign
const timestamp = Math.floor(Date.now() / 1000);
const message = `Disconnect OAuth provider github from wallet ${wallet.toLowerCase()} at ${timestamp}`;

// Step 2: Sign message
const signature = await signer.signMessage(message);

// Step 3: Call backend
const response = await fetch(
  `https://your-service.onrender.com/oauth/disconnect/github/${wallet}?` +
  `signature=${signature}&timestamp=${timestamp}`,
  { method: 'DELETE' }
);
const data = await response.json();
// { success: true, provider: "github", wallet_address: "0x1234..." }
```

### Complete Flow

#### Step 1: Validation
```python
@router.delete("/disconnect/{provider}/{wallet_address}")
async def disconnect_oauth(
    provider: str,
    wallet_address: str,
    signature: str = Query(...),
    timestamp: int = Query(...),
):
    # 1. Get database client
    db = SupabaseDAL.from_env()
    if not db:
        raise HTTPException(503, "Database not configured")
    
    # 2. Verify provider supported
    if not oauth_service.get_provider(provider):
        raise HTTPException(400, f"Provider '{provider}' not supported")
```

#### Step 2: Signature Verification
```python
# 3. Verify wallet ownership
message = f"Disconnect OAuth provider {provider} from wallet {wallet_address.lower()} at {timestamp}"
verify_wallet_signature(wallet_address, message, signature, timestamp)
```

**⚠️ Security:** Prevents unauthorized removal of credentials.

#### Step 3: Database Deletion
```python
# 4. Delete token from database
db.delete_user_token(wallet_address, provider)
```

**Database Query:** `app/models/db.py`
```python
def delete_user_token(self, wallet_address: str, provider: str) -> Any:
    return (
        self.client
        .table("user_tokens")
        .delete()
        .eq("wallet_address", wallet_address.lower())
        .eq("provider", provider.lower())
        .execute()
    )
```

#### Step 4: Response
```python
return {
    "success": True,
    "provider": provider,
    "wallet_address": wallet_address.lower(),
}
```

### Success Response
```json
{
  "success": true,
  "provider": "github",
  "wallet_address": "0x1234567890123456789012345678901234567890"
}
```

### Error Scenarios
Same as OAuth Connect for signature verification.

---

## 3e. OAuth Providers List

### Endpoint
```
GET /oauth/providers
```

### Purpose
List all available OAuth providers.

### Frontend Usage
```javascript
const response = await fetch('https://your-service.onrender.com/oauth/providers');
const data = await response.json();
// { providers: ["github"] }
```

### Complete Flow

```python
@router.get("/providers")
async def list_providers():
    return {
        "providers": oauth_service.list_providers(),
    }
```

**Provider Registration:** Only includes providers with env vars configured.

### Success Response
```json
{
  "providers": ["github"]
}
```

**If GitHub not configured:** `{"providers": []}`

---

## Summary: Critical Environment Variables

### For All Endpoints
```bash
# Supabase (required for health, stats, oauth)
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=eyJhbGci...
```

### For Stats Endpoint
```bash
MOTIFY_CONTRACT_ADDRESS=0x53Da03A36Aa9333C41C5521A113d0f8BA028bC43
STAKE_TOKEN_DECIMALS=6
```

### For OAuth Endpoints
```bash
# GitHub OAuth credentials
GITHUB_CLIENT_ID=Ov23liT3dBZYgNsoydbR
GITHUB_CLIENT_SECRET=692d8ee0cd17955bc46f97167a6ffbc703becb45

# URLs (CRITICAL - must match OAuth app callback exactly!)
BACKEND_URL=https://motify-backend.onrender.com  # NO trailing slash!
FRONTEND_URL=https://motify.live
```

---

## Common OAuth Issues & Fixes

### Issue 1: "redirect_uri_mismatch"
**Symptom:** GitHub shows error page after user clicks authorize.

**Root Cause:** BACKEND_URL doesn't match GitHub OAuth App callback URL.

**Fix:**
1. Check Render env var: `BACKEND_URL=https://motify-backend.onrender.com`
2. Check GitHub OAuth App: Callback URL = `https://motify-backend.onrender.com/oauth/callback/github`
3. Ensure exact match (no trailing slash, same scheme/host/port/path)

### Issue 2: "Provider 'github' not supported"
**Symptom:** Frontend can't initiate OAuth flow.

**Root Cause:** `GITHUB_CLIENT_ID` or `GITHUB_CLIENT_SECRET` not set in Render.

**Fix:**
1. Go to Render dashboard → Environment tab
2. Add both secrets
3. Redeploy service

### Issue 3: CORS errors
**Symptom:** Browser blocks requests from frontend.

**Root Cause:** Frontend origin not in allowed list.

**Fix:**
1. Check `app/main.py` → `allow_origins` list
2. Add your frontend URL
3. Redeploy

### Issue 4: Signature verification fails
**Symptom:** "Signature does not match wallet address"

**Root Cause:** Message format mismatch.

**Fix:**
Ensure frontend uses exact format:
```javascript
// For connect:
const message = `Connect OAuth provider ${provider.toLowerCase()} to wallet ${wallet.toLowerCase()} at ${timestamp}`;

// For disconnect:
const message = `Disconnect OAuth provider ${provider.toLowerCase()} from wallet ${wallet.toLowerCase()} at ${timestamp}`;
```

---

**Generated:** 2025-10-22  
**Status:** ✅ Production-ready endpoint documentation  
**Next Steps:** Deploy with all env vars, test OAuth flow end-to-end
