# Copilot instructions for motify-backend

## What is this?
This file guides GitHub Copilot to generate relevant code and docs for this repository. It summarizes the app’s purpose, current architecture, routes, workflows, conventions, and the target design. Use it as a context primer when adding or modifying code.

## Repository info
- This is the backend repo. The frontend lives in a separate repo. The smart contract is also separate.

## About the app
Motify is a Base-chain (L2 ETH) accountability app. In this slimmed-down backend, we only expose a health endpoint and keep minimal scaffolding to re-introduce features later.

## Current architecture & data flow
- Framework: Minimal FastAPI app in `app/main.py` with health, stats, and OAuth endpoints.
- Data: Supabase (Postgres) via supabase-py is optional; the health route will attempt a lightweight query if env vars are configured. Schema in `docs/schema.sql`.
- OAuth: Modular OAuth service in `app/services/oauth.py` supports GitHub (extensible to other providers). Tokens stored in `user_tokens` table.
- CORS: Allowed dev origins are configured in `app/main.py` for local tooling.

### HTTP API
- GET `/health` → `{ ok: true, db: bool }` (db is true when Supabase URL and key are configured and a simple select succeeds).
- GET `/oauth/status/{provider}/{wallet_address}` → Check if wallet has valid OAuth credentials
- GET `/oauth/connect/{provider}?wallet_address=0x...` → Initiate OAuth flow (returns auth_url)
- GET `/oauth/callback/{provider}?code=...&state=...` → OAuth callback (redirects to frontend)
- DELETE `/oauth/disconnect/{provider}/{wallet_address}` → Remove OAuth credentials
- GET `/oauth/providers` → List available OAuth providers

### Conventions
- JSON fields: snake_case when expanding APIs.
- Dates: UTC and ISO8601 when adding timestamps.
- Security: Don’t log secrets. `.env` is used for configuration via pydantic-settings.

## Developer workflows
- Dependencies: See `requirements.txt` (FastAPI, Uvicorn, Pydantic, requests, supabase, pytest, python-dotenv).
- Local run (Windows cmd):
  1) `python -m venv .venv`
  2) `.venv\Scripts\activate`
  3) `pip install -r requirements.txt`
  4) `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- Tests: `pytest -q`. The Supabase connectivity test will skip unless env vars are set.
- Schema changes: `docs/schema.sql` currently contains a stub. Add concrete DDL as needed by your Supabase project.
- Env vars: When adding/updating envs, also document them in `.env.example` (don’t commit real secrets).

## Files to know
- `app/main.py` — App factory, routers, global error handler.
- `app/api/routes_health.py` — Health endpoint that optionally pings Supabase.
- `app/api/routes_oauth.py` — OAuth endpoints for linking wallet addresses with provider accounts.
- `app/services/oauth.py` — Modular OAuth service supporting multiple providers.
- `app/models/db.py` — Supabase DAL with methods for chain data and OAuth tokens.
- `docs/schema.sql` — Database schema including user_tokens table for OAuth.
- `tests/` — Tests for DB connectivity, server boot, and OAuth flow.
- `examples/frontend_oauth_integration.js` — Frontend integration examples.

## Target architecture (roadmap)
This repository is currently a slim backend intended primarily for health monitoring and environment validation. Future expansions (on-chain listeners, OAuth integrations, proofs ingestion, settlements) can be added back as separate modules and routes.

## Appendix
No appendices in the minimal setup. Refer to `ARCHITECTURE_old.md` for the previous full design if needed.
