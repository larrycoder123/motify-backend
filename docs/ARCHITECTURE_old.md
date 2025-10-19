# Motify Backend — Architecture & Internals

This document explains what each file/module does, how they depend on each other, and the key inputs/outputs so contributors can navigate and extend the codebase quickly.

- Current prototype: FastAPI app in `app/` with modular routers, security helpers, and pure services. Old Flask prototype remains in `zold_backend/` for reference.
- Target: FastAPI + Supabase + web3.py (contract on Base) + n8n proofs pipeline; details in `.github/copilot-instructions.md` (Appendix).

## Top-level map
- `app/main.py` — ASGI app factory. Wires routers and sets a uniform error fallback.
  - Depends on: `fastapi`, `app/api/*`.
  - Provides: `app` (ASGI) for Uvicorn/Gunicorn.
  - Outputs: HTTP responses; unexpected errors wrapped into `{ error: { code: "INTERNAL", message, details } }`.

- `app/api/routes_health.py` — Health probe.
  - GET `/health` → `{ ok: true, db: bool }` where `db` indicates a successful lightweight query using the configured Supabase client.

- `app/api/routes_users.py` — User endpoints (stubs).
  - POST `/users` — Input `{ wallet: str }` → Output `{ wallet }`.
    - Errors: 400 → `{ error: { code: "VALIDATION_FAILED", message, details } }`.
  - GET `/users/{wallet}/stats` — Output aggregate counters (stubbed now).
  - Depends on (future): Supabase DAL (`models/db.py`).

- `app/api/routes_challenges.py` — Challenges list/create/fetch and participation (wired to Supabase).
  - GET `/challenges` → returns latest challenges; selects `*` to remain forward-compatible with schema changes. Includes `created_tx_hash` and `created_block_number` when present.
  - GET `/challenges/{id}` → returns a single challenge by id.
  - POST `/challenges` — Input `ChallengeCreate` (FE shape, snake_case aliases):
    - `{ name, description, start_date, end_date, contract_address, goal, service_type?, activity_type?, api_provider?, is_charity?, charity_wallet?, owner_wallet?, on_chain_challenge_id?, description_hash? }`.
    - Behavior: inserts a new row with `status='pending'`, `completed=false`. If `on_chain_challenge_id` is provided, upsert is used with conflict target `(contract_address, on_chain_challenge_id)` for idempotency.
  - POST `/challenges/{id}/join` — Input `{ user_wallet, amount_minor_units }` (back-compat: `amount_wei` accepted and mapped) — ensures the user exists and upserts into `stakes` on `(challenge_id, user_wallet)`.
  - Depends on: Supabase DAL. Privacy/invite checks are not implemented yet.

- `app/api/routes_webhooks.py` — Proof ingestion (n8n → backend).
  - POST `/webhooks/proofs/{challenge_id}` — Verifies HMAC, accepts proof JSON.
    - Headers: `X-N8N-Signature`, `X-N8N-Timestamp`.
    - Body (example): `{ provider, metric, user_wallet, value, day_key, window_start, window_end, source_payload_json, idempotency_key }`.
    - Output: `{ status: "accepted", challenge_id, stored: true|false }`. When the backend lacks a `SUPABASE_SERVICE_ROLE_KEY`, it returns `stored=false` to avoid RLS violations; otherwise it performs an idempotent upsert into `proofs` using `idempotency_key`.
  - Depends on: `core.security.verify_n8n_hmac`, `core.config.settings.N8N_WEBHOOK_SECRET`, Supabase DAL.

- `app/api/routes_integrations.py` — OAuth start/callback and provider links (stubs).
  - GET `/integrations/{provider}/start?wallet=0x...` → `{ auth_url }`.
  - POST `/integrations/{provider}/callback` → `{ linked: true }`.
  - GET `/integrations?wallet=0x...` → `{ providers: [] }`.
  - DELETE `/integrations/{provider}?wallet=0x...` → `{ unlinked: true }`.
  - Depends on (future): OAuth client, token encryption, Supabase `integration_tokens`.

- `app/api/routes_leaderboards.py` — Leaderboards (stub).
  - GET `/leaderboards/{challenge_id}?by=stake|complete|donation` → `{ items: [] }`.
  - Depends on (future): Supabase aggregates.

- `app/core/config.py` — Centralized settings via Pydantic.
  - Reads from environment/`.env`.
  - Fields now: `ENV`, `N8N_WEBHOOK_SECRET`, Supabase (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`), optional `DATABASE_URL`, fee knobs, and Web3 placeholders for future settlement.
  - Used by: `routes_webhooks.py` (secret), models/db (Supabase), others.

- `app/core/security.py` — Security helpers.
  - `verify_n8n_hmac(raw: bytes, sig: str|None, ts: str|None, secret: str)` → raises `HTTPException(401)` on failure.
  - Used by: `routes_webhooks.py`.

- `app/services/payouts.py` — Pure money math using token smallest units (e.g., USDC has 6 decimals).
  - `compute_payouts(stake_amount: int, percent_ppm: int, platform_fee_bps_fail=1000, reward_bps_of_fee=500)` → dict with:
    - `refund_amount, fail_amount, commission_amount, charity_amount, reward_from_commission_amount`.
  - Used by: settlement preview/execute endpoints (to mirror/validate on-chain results if needed).
- `app/services/chain_handlers.py` — Handlers for on-chain events (e.g., ChallengeCreated).
  - Attaches `on_chain_challenge_id`, marks `status='active'`, sets `owner_wallet`, and stores `created_tx_hash` + `created_block_number` on the corresponding DB row.
  - Matches by explicit DB id or by `(contract_address, description_hash)` with safe fallback.

- `app/models/` — Pydantic models/DB access.
  - `models/db.py` provides a small Supabase DAL and a `Proof` model. DAL binds from env and exposes `insert_proof()` with upsert semantics.

- `tests/test_payouts.py` — Validates money math (e.g., 90% completion, fee splits, edges).
- `tests/test_security.py` — Validates HMAC OK and stale timestamp failure.
- `tests/test_challenge_db_insert.py` — Direct Supabase insert/select for the new `challenges` schema.
- `tests/test_challenge_api_create.py` — End-to-end API flow: posts `payloads/create_challenge.json` (with minor tweaks for uniqueness) to `/challenges` and verifies persistence in Supabase. Uses the `test_api_base_url` fixture from `tests/conftest.py`.

- `requirements.txt` — Includes FastAPI, Uvicorn, Pydantic, pydantic-settings, pytest, requests, python-dotenv, Supabase client, web3.

- `zold_backend/` — Legacy Flask app; not used by the new FastAPI service.

## Data & error contracts (current + target)
- Uniform error envelope (current fallback + stubs): `{ error: { code, message, details } }`.
- Webhook HMAC contract, time windows, settlement PPM, and contract methods are defined in `.github/copilot-instructions.md` Appendix.

## End-to-end flow (current + target)
1) FE posts `/challenges` to create a pending row (include `description_hash` that matches on-chain `metadataHash`).
2) User submits the on-chain create tx; the chain listener detects `ChallengeCreated` and updates the row: sets `on_chain_challenge_id`, `status='active'`, `owner_wallet`, `created_tx_hash`, `created_block_number`.
3) n8n posts proofs (HMAC) → `/webhooks/proofs/{id}` → Supabase `proofs` (idempotent on `idempotency_key`).
4) Target: `/challenges/{id}/end` (lock with `run_id`), `/settlements/preview` (compute PPM), `/settlements/execute` (web3 batchSettle/settleUser). Store tx hash + logs in `payouts`.

## Inputs/outputs quick reference
- Proof webhook input body: `{ provider, metric, user_wallet, value:int, day_key:date, window_start, window_end, source_payload_json, idempotency_key }`.
- Joins input: `{ user_wallet, amount_minor_units }` (legacy `amount_wei` still accepted).
- Settlement execute input: `{ run_id: UUID, items:[{ user_wallet, percent_ppm:int }] }`.
- All money amounts are integers in token minor units (e.g., USDC 6 decimals). Percent precision is `percent_ppm` (0..1_000_000).

## Dev commands
- Install: `.venv\Scripts\python -m pip install -r requirements.txt`
- Run API: `.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000`
- Run tests: `.venv\Scripts\python -m pytest -q`

## Maintenance rules
- When adding/renaming routes or changing payloads/contracts:
  - Update this document’s section for the modified module.
  - Keep the payload shapes and error envelope examples in sync.
  - Reflect new env variables in `core/config.py` and list them here.
- Keep secrets in env; never log private keys, tokens, or webhook secrets.

## Notable fields and indices
- Challenges include `created_tx_hash` and `created_block_number` (persisted on chain events). Ensure index creation occurs after corresponding ALTERs in migrations to avoid `42703` errors.
