# Motify Backend (Minimal)

A slim FastAPI backend exposing health and stats endpoints, plus internal jobs and services to index on-chain data, compute progress off-chain, declare results on-chain, and archive.

## Endpoints
- GET `/health` → `{ ok: true, db: bool }`
- GET `/stats/user?address=0x...` → Aggregated archived stats for a wallet
- GET `/oauth/status/{provider}/{wallet_address}` → Check if wallet has valid OAuth credentials
- GET `/oauth/connect/{provider}?wallet_address=0x...` → Initiate OAuth flow (returns auth_url)
- GET `/oauth/callback/{provider}?code=...&state=...` → OAuth callback (redirects to frontend)
- DELETE `/oauth/disconnect/{provider}/{wallet_address}` → Remove OAuth credentials
- GET `/oauth/providers` → List available OAuth providers

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
- FRONTEND_URL (for OAuth redirects, default: http://localhost:3000)

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

## Notes
- CORS for dev allows localhost. Add your production frontend origin in `app/main.py` if needed.
- Supabase schema stub lives in `docs/schema.sql`.
- ABI at `abi/Motify.json`.
