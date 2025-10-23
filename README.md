# Motify Backend (Minimal)

A slim FastAPI backend exposing health and stats endpoints, plus internal jobs and services to index on-chain data, compute progress off-chain, declare results on-chain, and archive.

## Endpoints
- GET `/health` → `{ ok: true, db: bool }`
- GET `/stats/user?address=0x...` → Aggregated archived stats for a wallet

### OAuth Endpoints (Signature Required)
- GET `/oauth/status/{provider}/{wallet_address}` → Check if wallet has valid OAuth credentials (no signature required)
- GET `/oauth/connect/{provider}?wallet_address=0x...&signature=0x...&timestamp=123` → Initiate OAuth flow (requires wallet signature)
- GET `/oauth/callback/{provider}?code=...&state=...` → OAuth callback (redirects to frontend)
- DELETE `/oauth/disconnect/{provider}/{wallet_address}?signature=0x...&timestamp=123` → Remove OAuth credentials (requires wallet signature)
- GET `/oauth/providers` → List available OAuth providers (no signature required)

## Local development (Windows)
1. python -m venv .venv
2. .venv\Scripts\activate
3. pip install -r requirements.txt
4. python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

Run tests:
- pytest -q

## Required env (vary by use)
- SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY (server only)
- WEB3_RPC_URL (for jobs that read/write chain)
- MOTIFY_CONTRACT_ADDRESS
- PRIVATE_KEY (only if sending transactions)
- MAX_FEE_GWEI (optional EIP-1559 fee cap)
- STAKE_TOKEN_DECIMALS (default 6)
- DEFAULT_PERCENT_PPM (optional default progress)
- CRON_SECRET (optional, to secure any job endpoints)
- GITHUB_CLIENT_ID (for GitHub OAuth)
- GITHUB_CLIENT_SECRET (for GitHub OAuth)
- FRONTEND_URL (for OAuth redirects, default: http://localhost:8080)
- NEYNAR_API_KEY (for Farcaster progress checks)

See `.env.example` for placeholders (do not commit real secrets).

## Deploy to Render
One-click with `render.yaml`:
- Create a new Web Service from this repo.
- Environment: Python
- Build Command: `pip install --upgrade pip && pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Set env vars: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, MOTIFY_CONTRACT_ADDRESS, WEB3_RPC_URL.
  - For API-only hosting, you don't need PRIVATE_KEY.

## Scheduled processing
A GitHub Actions workflow runs end-to-end processing every 15 minutes, capturing logs as artifacts. Update secrets in repo settings for: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, WEB3_RPC_URL, MOTIFY_CONTRACT_ADDRESS, PRIVATE_KEY (if SEND_TX=true), MAX_FEE_GWEI (optional).

## OAuth Security

**All OAuth connect and disconnect operations require wallet signature verification** to prevent unauthorized users from linking/unlinking credentials to wallets they don't own.

### Wallet Support

The backend supports both:
- **EOA wallets** (MetaMask, Ledger, etc.) - 65-byte ECDSA signatures
- **Smart contract wallets** (Base Wallet, Coinbase Smart Wallet, etc.) - ERC-1271/ERC-6492 signatures

No changes needed in your frontend - the backend automatically detects and verifies the appropriate signature format.

### Signature Requirements

When calling `/oauth/connect` or `/oauth/disconnect`, you must provide:
1. `wallet_address` - The wallet address
2. `signature` - Wallet signature (supports both EOA and smart wallet formats)
3. `timestamp` - Unix timestamp (must be within 5 minutes)

### Message Format

**For connecting:**
```
Connect OAuth provider {provider} to wallet {wallet_address} at {timestamp}
```

**For disconnecting:**
```
Disconnect OAuth provider {provider} from wallet {wallet_address} at {timestamp}
```

### Frontend Examples

**Using Base Wallet:**
```javascript
import { createBaseAccountSDK } from '@base-org/account';

const provider = createBaseAccountSDK().getProvider();
const accounts = await provider.request({ method: 'eth_requestAccounts' });
const timestamp = Math.floor(Date.now() / 1000);
const message = `Connect OAuth provider github to wallet ${accounts[0].toLowerCase()} at ${timestamp}`;
const signature = await provider.request({
  method: 'personal_sign',
  params: [message, accounts[0]]
});

// Signature will be 1000+ bytes (ERC-1271/ERC-6492) - this is normal!
fetch(`/oauth/connect/github?wallet_address=${accounts[0]}&signature=${signature}&timestamp=${timestamp}`);
```

**Using MetaMask (still supported):**
```javascript
const signer = await provider.getSigner();
const timestamp = Math.floor(Date.now() / 1000);
const message = `Connect OAuth provider github to wallet ${address.toLowerCase()} at ${timestamp}`;
const signature = await signer.signMessage(message);

// Signature will be 65 bytes
fetch(`/oauth/connect/github?wallet_address=${address}&signature=${signature}&timestamp=${timestamp}`);
```

See `examples/base_wallet_oauth_integration.js` for complete Base Wallet integration and `examples/frontend_oauth_integration.js` for MetaMask examples.

### Configuration for Smart Wallets

To support smart wallet signatures, set in `.env`:
```bash
WEB3_RPC_URL=https://mainnet.base.org  # or https://sepolia.base.org for testnet
ENV=production  # or 'development' for testnet
```

📖 **For detailed migration guide and troubleshooting, see:** `docs/BASE_WALLET_OAUTH.md`

## Notes
- CORS for dev allows localhost. Add your production frontend origin in `app/main.py` if needed.
- Supabase schema stub lives in `docs/schema.sql`.
- ABI at `abi/Motify.json`.
- OAuth operations use EIP-191 signatures for wallet ownership verification.

## Progress engines

### GitHub (contribution per day)
- Uses GitHub GraphQL contributions calendar to count per-day contributions in the challenge window.
- Requires a token per wallet stored in Supabase `user_tokens` with `provider=github` and `access_token` set to the GitHub token.
- Scope: with `user:email`, only public contributions are counted; to include private, request `repo` scope and reconnect.
- Fallback: if a participant has no token or the call fails, their percent defaults to `DEFAULT_PERCENT_PPM` (1_000_000 by default = 100%).

### Farcaster (one cast per day)
- Uses Neynar to count per-day casts in the challenge window.
- User resolution order:
  1) If `user_tokens` has `provider=farcaster` and `access_token` is a numeric string, it's treated as FID and used.
  2) Otherwise, resolve FID from wallet via Neynar bulk API: `/v2/farcaster/user/bulk-by-address/?addresses=0x...`.
  3) If still not found, try verifications API: `/v2/farcaster/verification/by-address?address=0x...` (requires the wallet be verified on profile).
  4) If all fail, the participant falls back to `DEFAULT_PERCENT_PPM`.
- Env: set `NEYNAR_API_KEY`.
 - Optional: if your Neynar plan exposes a different endpoint for listing casts, set `FARCASTER_USER_CASTS_URL` to override the default `https://api.neynar.com/v2/farcaster/feed/user/casts/`.
 - Notes: we request `include_replies=true` and handle pagination via the `next.cursor` value returned by the API.
- Optional: to guarantee resolution without relying on verifications, store the user’s FID in `user_tokens` (`provider=farcaster`, `access_token="<fid>"`).

### Quick testing (Python REPL)
```python
from datetime import date, timedelta
from app.services.progress import _github_ratio_for_user, ratio_to_ppm, _resolve_farcaster_fid_for_address, _farcaster_ratio_for_fid
import os

# GitHub (needs GITHUB_TOKEN)
gtoken = os.getenv('GITHUB_TOKEN')
end = date.today() - timedelta(days=1)
start = end - timedelta(days=13)
if gtoken:
  gr = _github_ratio_for_user(gtoken, start, end, required_per_day=1)
  print('github ratio:', gr, 'ppm:', ratio_to_ppm(gr))
else:
  print('Set GITHUB_TOKEN to test GitHub progress')

# Farcaster (needs NEYNAR_API_KEY)
api_key = os.getenv('NEYNAR_API_KEY')
addr = '0x...'  # set a wallet verified on Farcaster
if api_key:
  fid = _resolve_farcaster_fid_for_address(api_key, addr.lower())
  print('resolved fid:', fid)
  if fid:
    fr = _farcaster_ratio_for_fid(api_key, fid, start, end, required_per_day=1)
    print('farcaster ratio:', fr, 'ppm:', ratio_to_ppm(fr))
  else:
    print('No FID found (no Farcaster verification) → fallback will apply')
else:
  print('Set NEYNAR_API_KEY to test Farcaster progress')
```
