# Copilot Instructions for motify-backend

## Overview

This is the backend for **Motify**, a Base-chain (L2 ETH) accountability app. Users commit to goals with crypto stakes, and this backend handles OAuth integration, progress tracking, and on-chain result declaration.

**Related repos:**
- Frontend: [Motify](https://github.com/eliaslehner/Motify)
- Smart Contracts: [motify-smart-contracts](https://github.com/etaaa/motify-smart-contracts)

## Tech Stack

- **Framework:** FastAPI (Python 3.11+)
- **Database:** Supabase (PostgreSQL)
- **Blockchain:** Base L2 via Web3.py
- **Auth:** Wallet signatures (EIP-191, ERC-1271)
- **Deployment:** Render (API) + GitHub Actions (scheduled jobs)

## Project Structure

```
app/
├── api/                 # HTTP route handlers
│   ├── routes_health.py # Health checks
│   ├── routes_oauth.py  # OAuth flows (GitHub, WakaTime)
│   └── routes_stats.py  # User statistics
├── core/
│   ├── config.py        # Environment configuration (pydantic-settings)
│   └── security.py      # Wallet signature verification
├── models/
│   └── db.py            # Supabase data access layer
├── services/
│   ├── chain_reader.py  # Read from Motify contract
│   ├── chain_writer.py  # Write to Motify contract (declare results)
│   ├── indexer.py       # Challenge/participant caching
│   ├── oauth.py         # OAuth provider implementations
│   └── progress.py      # Fetch progress from external APIs
├── jobs/
│   └── process_ready_all.py  # Main job: process due challenges
└── main.py              # FastAPI app entry point
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check with DB status |
| GET | `/oauth/status/{provider}/{wallet}` | Check OAuth connection |
| GET | `/oauth/connect/{provider}` | Start OAuth flow |
| GET | `/oauth/callback/{provider}` | OAuth callback |
| DELETE | `/oauth/disconnect/{provider}/{wallet}` | Remove OAuth |
| GET | `/oauth/providers` | List providers |
| GET | `/stats/user?wallet=0x...` | User statistics |
| POST | `/jobs/index-and-cache` | Trigger indexing (protected) |
| POST | `/jobs/declare-preview/{id}` | Preview declare payload |

## Coding Conventions

- **Style:** PEP 8, type hints on all functions
- **Imports:** stdlib → third-party → local (alphabetized within groups)
- **Docstrings:** Google style for modules and public functions
- **Naming:** snake_case for variables/functions, PascalCase for classes
- **JSON fields:** snake_case
- **Dates:** UTC, ISO8601 format
- **Secrets:** Never log or commit; use environment variables

## Common Patterns

### Adding a new endpoint:
1. Create route in `app/api/routes_*.py`
2. Add business logic in `app/services/`
3. Include router in `app/main.py` if new file
4. Add tests in `tests/`

### Adding a new OAuth provider:
1. Add provider class in `app/services/oauth.py`
2. Add env vars to `app/core/config.py` and `.env.example`
3. Update documentation

### Database operations:
- Use `SupabaseDAL` from `app/models/db.py`
- Handle connection errors gracefully
- Return `None` or empty results on failure, don't raise

## Development Commands

```bash
# Setup
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Run locally
uvicorn app.main:app --reload --port 8000

# Run tests
pytest -q

# Run processing job manually
python -m app.jobs.process_ready_all
```

## Environment Variables

See `.env.example` for all configuration options. Key groups:
- `SUPABASE_*` — Database
- `WEB3_RPC_URL`, `MOTIFY_CONTRACT_ADDRESS`, `PRIVATE_KEY` — Blockchain
- `GITHUB_CLIENT_*` — OAuth
- `BACKEND_URL`, `FRONTEND_URL` — Redirect URLs
- `CRON_SECRET` — Job endpoint protection
