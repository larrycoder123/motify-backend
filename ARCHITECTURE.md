# Motify Backend Architecture

> Last updated: December 2024

## Overview

Motify is a Base-chain (L2 ETH) accountability app that helps users commit to goals with crypto stakes. This backend provides:

- **REST API** for health checks, user statistics, and OAuth token management
- **Background Jobs** for indexing challenges, computing progress, and declaring results on-chain
- **Progress Engines** that integrate with GitHub, Farcaster (via Neynar), and WakaTime to verify goal completion

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | FastAPI (Python 3.11+) |
| Database | Supabase (PostgreSQL) |
| Blockchain | Base L2 (via Web3.py) |
| Auth | Wallet signatures (EIP-191, ERC-1271) |
| API Hosting | Render |
| Scheduled Jobs | GitHub Actions |

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
├── docs/                       # Additional documentation
├── tests/                      # Test suite
├── .env.example                # Environment template
├── requirements.txt            # Python dependencies
└── README.md                   # Quick start guide
```

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

## API Endpoints

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

### Jobs (Protected)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/jobs/index-and-cache` | Trigger challenge indexing |
| POST | `/jobs/declare-preview/{id}` | Preview declare payload |
| GET | `/jobs/debug-config` | Debug environment config |

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
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. ARCHIVAL                                                    │
│     - Move processed data to finished_challenges/participants  │
│     - Clean up cache tables                                     │
└─────────────────────────────────────────────────────────────────┘
```

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

## Security

- **Wallet Authentication**: All sensitive operations require EIP-191 signed messages
- **Smart Wallet Support**: ERC-1271 signature verification for contract wallets
- **CORS**: Restricted to known frontend origins (localhost + production)
- **Secrets**: All credentials via environment variables, never committed
- **OAuth State**: CSRF protection via state tokens with 10-minute expiry
- **Job Protection**: CRON_SECRET header required for job endpoints

## Supported Progress Providers

| Provider | Type | Metrics |
|----------|------|---------|
| GitHub | OAuth | Commits, contributions |
| WakaTime | API Key | Coding time (hours) |
| Farcaster | OAuth | Casts, engagement |

## Environment Configuration

See `.env.example` for all available configuration options.

**Key variable groups:**
- `SUPABASE_*` — Database connection
- `WEB3_RPC_URL`, `MOTIFY_CONTRACT_ADDRESS` — Blockchain
- `PRIVATE_KEY` — Server wallet for signing transactions
- `GITHUB_CLIENT_*` — GitHub OAuth credentials
- `BACKEND_URL`, `FRONTEND_URL` — OAuth redirect URLs
- `CRON_SECRET` — Job endpoint protection
- `DEFAULT_PERCENT_PPM` — Fallback refund percentage

## Development

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run locally
uvicorn app.main:app --reload --port 8000

# Run tests
pytest -q

# Manual job execution
python -m app.jobs.process_ready_all
```

## Related Repositories

- **[Frontend](https://github.com/eliaslehner/Motify)** — React dApp (Base Mini App)
- **[Smart Contracts](https://github.com/etaaa/motify-smart-contracts)** — Solidity contracts on Base L2
