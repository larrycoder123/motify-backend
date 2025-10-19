# Motify backend — minimal architecture

This repository currently hosts a slim FastAPI service used for health monitoring and environment validation. It intentionally excludes previous functionality (on-chain listeners, challenges, webhooks, OAuth).

## Components
- FastAPI app (`app/main.py`) with CORS and a global error handler.
- Health router (`app/api/routes_health.py`) that returns `{ ok: true, db: boolean }`.
- Supabase DAL (`app/models/db.py`) used by health to perform a lightweight query when credentials are configured.

## API
- GET `/health` → `{ ok: true, db: bool }`
	- `db` is true when `SUPABASE_URL` and a key are provided and a simple select against `users` succeeds.

### Chain (read-only)
- GET `/chain/challenges?limit=200` → Calls contract `getAllChallenges(limit)` and returns an array of challenges.
- GET `/chain/challenges/{challenge_id}` → Calls `getChallengeById(challenge_id)` and returns details incl. participants.

Requires env:
- `WEB3_RPC_URL`, `MOTIFY_CONTRACT_ADDRESS`, `MOTIFY_CONTRACT_ABI_PATH` (defaults to `./abi/Motify.json`).

### Indexer (DB-backed cache)
- GET `/indexer/challenges?limit=1000&only_ready_to_end=true` → Reads from chain, filters ended-and-not-finalized, upserts into `chain_challenges`.
- POST `/indexer/challenges/{challenge_id}/detail` → Reads participants from chain and upserts into `chain_participants`.
- GET `/indexer/ready` → Returns cached challenges ready to end from `chain_challenges`.
- GET `/indexer/challenges/{challenge_id}/preview` → Returns a placeholder preview based on cached participants.

Apply the DDL in `docs/schema.sql` to create `chain_challenges` and `chain_participants` before using the indexer endpoints.

## Configuration
Environment variables are read via pydantic-settings from `.env`:
- `ENV` (default `development`)
- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` (optional)

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
When re-introducing functionality, keep features modular under `app/api/` and `app/services/` with strong typing and clear boundaries.

## ABI
- The contract ABI can be stored under `abi/` (for example `abi/Motify.json`).
- In this minimal backend, the ABI is not loaded by the server; it’s kept only as a reference for future on-chain integrations.
	- When chain endpoints are enabled (see above), the ABI path is read from env and used by the web3 client.
