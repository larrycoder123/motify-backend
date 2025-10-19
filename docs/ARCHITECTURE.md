# Motify backend — minimal architecture

This repository currently hosts a slim FastAPI service used for health monitoring and environment validation. It intentionally excludes previous functionality (on-chain listeners, challenges, webhooks, OAuth).

## Components
- FastAPI app (`app/main.py`) with CORS and a global error handler.
- Health router (`app/api/routes_health.py`) that returns `{ ok: true, db: boolean }`.
- Supabase DAL (`app/models/db.py`) used by health to perform a lightweight query when credentials are configured.
- Chain reader (`app/services/chain_reader.py`) for read-only web3 contract calls.
- Indexer services (`app/services/indexer.py`) expose pure functions for caching challenges/participants and preparing previews.
- CLI (`app/jobs/indexer_cli.py`) to invoke indexer services without HTTP endpoints.

## API
- GET `/health` → `{ ok: true, db: bool }`
	- `db` is true when `SUPABASE_URL` and a key are provided and a simple select against `users` succeeds.

Previously exposed chain and indexer endpoints have been removed in favor of internal services and a CLI.

### CLI (developer-only)
Run these examples from repo root with your virtualenv activated and required env vars set (`WEB3_RPC_URL`, `MOTIFY_CONTRACT_ADDRESS`, `MOTIFY_CONTRACT_ABI_PATH`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`):

```bat
.venv\Scripts\python -m app.jobs.indexer_cli index-challenges --limit 1000
.venv\Scripts\python -m app.jobs.indexer_cli ready --limit 50
.venv\Scripts\python -m app.jobs.indexer_cli index-details 1
.venv\Scripts\python -m app.jobs.indexer_cli preview 1
.venv\Scripts\python -m app.jobs.indexer_cli prepare 1 --default-percent-ppm 500000
```

These commands print JSON to stdout and exit non-zero on errors, suitable for schedulers.

## Configuration
Environment variables are read via pydantic-settings from `.env`:
- `ENV` (default `development`)
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` (optional)

Chain services require:
- `WEB3_RPC_URL`, `MOTIFY_CONTRACT_ADDRESS`, `MOTIFY_CONTRACT_ABI_PATH` (defaults to `./abi/Motify.json`).

Progress token lookup (required for challenges with an `api_type`):
- `USER_TOKENS_TABLE` (e.g., `user_tokens`)
- `USER_TOKENS_WALLET_COL` (e.g., `wallet_address`)
- `USER_TOKENS_PROVIDER_COL` (e.g., `provider`)
- `USER_TOKENS_ACCESS_TOKEN_COL` (e.g., `access_token`)

Security note: Store provider tokens in a restricted table with RLS so only a service role can read. Do not expose via public endpoints. If a challenge has `api_type` set, these envs must be configured or prepare_run will raise.

See `.env.example` for a template.

## Local development
Windows cmd:
1) `python -m venv .venv`
2) `.venv\Scripts\activate`
3) `pip install -r requirements.txt`
4) `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`

## Tests
Run `pytest -q`. The DB connectivity test will skip unless Supabase env vars are set.

## Future work
When re-introducing functionality, keep features modular under `app/services/` and expose job entry points via CLI. Add scheduling (GitHub Actions, cron, or cloud scheduler) to run the CLI periodically. Integrate provider-specific progress fetchers (Strava, etc.) that use per-wallet tokens from `user_tokens`.

## ABI
- The contract ABI is stored under `abi/` (for example `abi/Motify.json`).
- The CLI/services load the ABI path from env and use it for read-only web3 calls.
