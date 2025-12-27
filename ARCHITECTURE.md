# Motify Backend — Technical Architecture

> Last updated: December 2025

This document provides comprehensive technical documentation for developers who want to understand, deploy, or contribute to the Motify backend.

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Deployment Architecture](#deployment-architecture)
- [API Reference](#api-reference)
- [Data Flow](#data-flow)
- [Configuration](#configuration)
- [Progress Engines](#progress-engines)
- [OAuth Security](#oauth-security)
- [Deployment Guide](#deployment-guide)
- [Development](#development)

---

## Overview

Motify is a Base-chain (L2 ETH) accountability app that helps users commit to goals with crypto stakes. This backend automates the entire accountability lifecycle:

1. **Index** ended challenges from the Motify smart contract
2. **Fetch Progress** from external APIs based on each challenge's activity type
3. **Compute Refunds** as percentages based on goal completion (0–100%)
4. **Declare Results** on-chain via `declareResults()` transaction
5. **Archive** processed data for user statistics and historical records

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | FastAPI (Python 3.11+) |
| Database | Supabase (PostgreSQL) |
| Blockchain | Base L2 (via Web3.py) |
| Auth | Wallet signatures (EIP-191, ERC-1271) |
| API Hosting | Render |
| Scheduled Jobs | GitHub Actions |
| Testing | pytest |

---

## Project Structure

```
motify-backend/
├── app/
│   ├── api/                    # HTTP endpoints
│   │   ├── routes_health.py    # Health checks
│   │   ├── routes_oauth.py     # OAuth flows (GitHub, WakaTime)
│   │   └── routes_stats.py     # User statistics
│   ├── core/                   # Configuration & utilities
│   │   ├── config.py           # Environment settings (pydantic-settings)
│   │   └── security.py         # Wallet signature verification
│   ├── models/
│   │   └── db.py               # Supabase data access layer
│   ├── services/               # Business logic
│   │   ├── chain_reader.py     # Read from Motify smart contract
│   │   ├── chain_writer.py     # Write to smart contract (declare results)
│   │   ├── indexer.py          # Challenge/participant caching
│   │   ├── oauth.py            # OAuth provider integrations
│   │   └── progress.py         # Progress fetching from providers
│   ├── jobs/                   # Background task entry points
│   │   └── process_ready_all.py # Main job: process due challenges
│   └── main.py                 # FastAPI application entry point
├── abi/
│   └── Motify.json             # Smart contract ABI
├── docs/
│   └── schema.sql              # Database schema
├── tests/                      # Test suite
├── .env.example                # Environment template
├── requirements.txt            # Python dependencies
└── render.yaml                 # Render deployment config
```

---

## Deployment Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              RENDER                                      │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  FastAPI Server (app/main.py)                                    │   │
│  │  - /health, /stats/user, /oauth/*                               │   │
│  │  - /jobs/* (protected by CRON_SECRET)                           │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ REST API
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          GITHUB ACTIONS                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │  process-ready.yml (hourly cron)                                 │   │
│  │  - Runs: python -m app.jobs.process_ready_all                   │   │
│  │  - Indexes challenges, fetches progress, declares results       │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
                    ▼               ▼               ▼
            ┌───────────┐   ┌───────────┐   ┌───────────┐
            │  Supabase │   │  Base L2  │   │ Provider  │
            │  (Postgres)│   │  (Web3)   │   │   APIs    │
            └───────────┘   └───────────┘   └───────────┘
```

---

## API Reference

### Health
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service health + DB connectivity |

### OAuth
| Method | Path | Description |
|--------|------|-------------|
| GET | `/oauth/status/{provider}/{wallet}` | Check OAuth connection status |
| GET | `/oauth/connect/{provider}` | Initiate OAuth flow |
| GET | `/oauth/callback/{provider}` | OAuth callback handler |
| DELETE | `/oauth/disconnect/{provider}/{wallet}` | Remove OAuth connection |
| GET | `/oauth/providers` | List available providers |
| GET | `/oauth/wakatime/api-key/{wallet}` | Get WakaTime API key status |
| POST | `/oauth/wakatime/api-key` | Save WakaTime API key |
| DELETE | `/oauth/wakatime/api-key/{wallet}` | Remove WakaTime API key |

### Statistics
| Method | Path | Description |
|--------|------|-------------|
| GET | `/stats/user?wallet=0x...` | User challenge statistics |

### Jobs (Protected by CRON_SECRET)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/jobs/index-and-cache` | Trigger challenge indexing |
| POST | `/jobs/declare-preview/{id}` | Preview declare payload |
| GET | `/jobs/debug-config` | Debug environment config |

---

## Data Flow

### Challenge Processing (GitHub Actions - Hourly)

```
┌─────────────────────────────────────────────────────────────────┐
│  1. INDEXING                                                    │
│     - Fetch ended challenges from Motify smart contract        │
│     - Cache challenge + participant data in Supabase           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. PROGRESS FETCHING                                           │
│     - Look up OAuth tokens from user_tokens table              │
│     - Call provider API based on challenge api_type:           │
│       • GitHub: GraphQL contributions calendar                 │
│       • Farcaster: Neynar API for casts                        │
│       • WakaTime: Summaries API for coding hours               │
│     - Compute ratio (0.0–1.0) based on goal completion         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. ON-CHAIN DECLARATION                                        │
│     - Convert ratios to refund percentages (parts-per-million) │
│     - Call declareResults(challengeId, participants[], %)      │
│     - Chunk large participant lists (max 200 per tx)           │
│     - Use EIP-1559 with MAX_FEE_GWEI cap                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. ARCHIVAL                                                    │
│     - Move processed data to finished_challenges/participants  │
│     - Store tx hashes, ratios, and refund amounts              │
│     - Clean up cache tables                                     │
└─────────────────────────────────────────────────────────────────┘
```

### Safety Mechanisms

- **Progress Missing Guard**: Skips sending if all participants have `progress_ratio=None` (API outage)
- **On-Chain Reconciliation**: Checks contract state to avoid duplicate declares
- **Configurable Fallback**: `DEFAULT_PERCENT_PPM` protects users when progress can't be fetched (defaults to 100%)
- **Dry-Run Mode**: Set `SEND_TX=false` to preview payloads without blockchain writes

### OAuth Connection Flow

```
┌──────────┐     ┌─────────┐     ┌──────────┐     ┌──────────┐
│ Frontend │────▶│ Backend │────▶│ Provider │────▶│ Supabase │
└──────────┘     └─────────┘     └──────────┘     └──────────┘
     │                │                │                │
     │ 1. Connect     │                │                │
     │───────────────▶│                │                │
     │                │ 2. Auth URL    │                │
     │◀───────────────│                │                │
     │                │                │                │
     │ 3. User authorizes on provider  │                │
     │────────────────────────────────▶│                │
     │                │                │                │
     │                │ 4. Callback    │                │
     │                │◀───────────────│                │
     │                │                │                │
     │                │ 5. Store token │                │
     │                │───────────────────────────────▶│
     │                │                │                │
     │ 6. Redirect    │                │                │
     │◀───────────────│                │                │
```

---

## Configuration

### Required Environment Variables

```env
# Database
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your-service-role-key

# Blockchain
WEB3_RPC_URL=https://mainnet.base.org
MOTIFY_CONTRACT_ADDRESS=0x...
MOTIFY_CONTRACT_ABI_PATH=./abi/Motify.json

# Transaction Signing (only if SEND_TX=true)
PRIVATE_KEY=0x...

# GitHub OAuth
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret

# Neynar (for Farcaster progress)
NEYNAR_API_KEY=your-neynar-api-key

# URLs (for OAuth redirects)
FRONTEND_URL=https://your-frontend-url.com
BACKEND_URL=https://your-backend-url.com
```

### Optional Environment Variables

```env
# EIP-1559 Fee Control
MAX_FEE_GWEI=1.0

# Token Configuration
STAKE_TOKEN_DECIMALS=6  # USDC has 6 decimals

# Fallback Behavior
DEFAULT_PERCENT_PPM=1000000  # 100% refund when progress unavailable

# Job Security
CRON_SECRET=random-secret-for-job-endpoints

# WakaTime API
WAKATIME_API_BASE_URL=https://api.wakatime.com/api/v1/

# Token Lookup
USER_TOKENS_TABLE=user_tokens
USER_TOKENS_WALLET_COL=wallet_address
USER_TOKENS_PROVIDER_COL=provider
USER_TOKENS_ACCESS_TOKEN_COL=access_token

# Environment
ENV=development  # or 'production'
```

See `.env.example` for a complete template.

---

## Progress Engines

### GitHub (Commits/Contributions Per Day)

- Uses GitHub GraphQL contributions calendar to count per-day contributions
- Requires OAuth token stored in `user_tokens` with `provider=github`
- Scope: `user:email` for public contributions, `repo` for private
- Fallback: defaults to `DEFAULT_PERCENT_PPM` if no token

### Farcaster (Casts Per Day)

- Uses Neynar API to count per-day casts in challenge window
- User resolution order:
  1. FID from `user_tokens` table
  2. Neynar bulk API by address
  3. Neynar verifications API
- Env: `NEYNAR_API_KEY` required

### WakaTime (Coding Hours)

- Uses WakaTime Summaries API
- Requires API key stored in `user_tokens` with `provider=wakatime`
- Queries with `timezone=UTC`

### Supported Providers

| Provider | Type | Metrics |
|----------|------|---------|
| GitHub | OAuth | Commits, contributions |
| WakaTime | API Key | Coding time (hours) |
| Farcaster | OAuth | Casts, engagement |

---

## OAuth Security

**All OAuth connect/disconnect operations require wallet signature verification.**

### Wallet Support

- **EOA wallets** (MetaMask, Ledger) — 65-byte ECDSA signatures (EIP-191)
- **Smart contract wallets** (Base Wallet, Coinbase Smart Wallet) — ERC-1271/ERC-6492 signatures

### Signature Requirements

When calling `/oauth/connect` or `/oauth/disconnect`:
1. `wallet_address` — The wallet address
2. `signature` — Wallet signature
3. `timestamp` — Unix timestamp (must be within 5 minutes)

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

fetch(`/oauth/connect/github?wallet_address=${accounts[0]}&signature=${signature}&timestamp=${timestamp}`);
```

**Using MetaMask:**
```javascript
const signer = await provider.getSigner();
const timestamp = Math.floor(Date.now() / 1000);
const message = `Connect OAuth provider github to wallet ${address.toLowerCase()} at ${timestamp}`;
const signature = await signer.signMessage(message);

fetch(`/oauth/connect/github?wallet_address=${address}&signature=${signature}&timestamp=${timestamp}`);
```

---

## Deployment Guide

### Render (API Server)

One-click deployment using `render.yaml`:

1. Create a new Web Service from this repository
2. Render will auto-detect `render.yaml` and configure:
   - **Environment**: Python 3.11
   - **Build**: `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

3. Set environment variables in Render dashboard

### GitHub Actions (Background Jobs)

The `.github/workflows/process-ready.yml` workflow runs hourly to:
1. Fetch ended challenges from the blockchain
2. Compute progress from external APIs
3. Declare results on-chain (if `SEND_TX=true`)
4. Archive processed data

**Required GitHub Secrets:**
```
SUPABASE_URL
SUPABASE_SERVICE_ROLE_KEY
WEB3_RPC_URL
MOTIFY_CONTRACT_ADDRESS
PRIVATE_KEY
NEYNAR_API_KEY
SEND_TX=true
```

**Workflow Features:**
- Runs on schedule (`cron: '*/15 * * * *'`) and manual dispatch
- Captures full logs as downloadable artifacts (14-day retention)
- Automatic retry on transient failures

---

## Development

### Local Setup

```bash
# Setup
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your credentials

# Run locally
uvicorn app.main:app --reload --port 8000

# Run tests
pytest -q

# Manual job execution (dry-run)
python -m app.jobs.process_ready_all

# Manual job execution (live)
SEND_TX=true python -m app.jobs.process_ready_all
```

### Testing Progress Engines

```python
from datetime import date, timedelta
from app.services.progress import _github_ratio_for_user, ratio_to_ppm
import os

# GitHub (needs GITHUB_TOKEN)
gtoken = os.getenv('GITHUB_TOKEN')
end = date.today() - timedelta(days=1)
start = end - timedelta(days=13)
if gtoken:
    gr = _github_ratio_for_user(gtoken, start, end, required_per_day=1)
    print('github ratio:', gr, 'ppm:', ratio_to_ppm(gr))
```

---

## Security

- **Wallet Authentication**: All sensitive operations require EIP-191 signed messages
- **Smart Wallet Support**: ERC-1271 signature verification for contract wallets
- **CORS**: Restricted to known frontend origins (localhost + production)
- **Secrets**: All credentials via environment variables, never committed
- **OAuth State**: CSRF protection via state tokens with 10-minute expiry
- **Job Protection**: CRON_SECRET header required for job endpoints

---

## Notes

- **CORS**: Dev environment allows `localhost`. Production origins configured in `app/main.py`
- **Timezone**: All progress engines use UTC for consistency
- **Fallback Protection**: Set `DEFAULT_PERCENT_PPM=1000000` for 100% refund during API outages

---

## Related Repositories

- **[Frontend](https://github.com/eliaslehner/Motify)** — React dApp (Base Mini App)
- **[Smart Contracts](https://github.com/etaaa/motify-smart-contracts)** — Solidity contracts on Base L2
