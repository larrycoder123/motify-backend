# Motify Backend — Architecture & Internals

This document explains what each file/module does, how they depend on each other, and the key inputs/outputs so contributors can navigate and extend the codebase quickly.

- Current prototype: FastAPI app in `app/` with modular routers, security helpers, and pure services. Old Flask prototype remains in `old_backend/` for reference.
- Target: FastAPI + Supabase + web3.py (contract on Base) + n8n proofs pipeline; details in `.github/copilot-instructions.md` (Appendix).

## Top-level map
- `app/main.py` — ASGI app factory. Wires routers and sets a uniform error fallback.
  - Depends on: `fastapi`, `app/api/*`.
  - Provides: `app` (ASGI) for Uvicorn/Gunicorn.
  - Outputs: HTTP responses; unexpected errors wrapped into `{ error: { code: "INTERNAL", message, details } }`.

- `app/api/routes_health.py` — Health probe.
  - GET `/health` → `{ ok: true }`.

- `app/api/routes_users.py` — User endpoints (stubs).
  - POST `/users` — Input `{ wallet: str }` → Output `{ wallet }`.
    - Errors: 400 → `{ error: { code: "VALIDATION_FAILED", message, details } }`.
  - GET `/users/{wallet}/stats` — Output aggregate counters (stubbed now).
  - Depends on (future): Supabase DAL (`models/db.py`).

- `app/api/routes_challenges.py` — Challenges CRUD and participation (stubs).
  - GET `/challenges` → `[]` (stub list).
  - POST `/challenges` — Input `ChallengeCreate`:
    - `{ title, start_at, end_at, target_metric, target_value, charity_wallet?, is_private, proof_policy? }` → Output created challenge.
  - POST `/challenges/{id}/join` — Input `{ user_wallet, amount_wei }` → echoes payload with `challenge_id`.
  - Depends on (future): Supabase DAL; window validation; privacy/invite checks.

- `app/api/routes_webhooks.py` — Proof ingestion (n8n → backend).
  - POST `/webhooks/proofs/{challenge_id}` — Verifies HMAC, accepts proof JSON.
    - Headers: `X-N8N-Signature`, `X-N8N-Timestamp`.
    - Body (example): `{ provider, metric, user_wallet, value, day_key, window_start, window_end, source_payload_json, idempotency_key }`.
    - Output: `{ status: "accepted", challenge_id, stored: true }` (stub; will be 202 Accepted).
  - Depends on: `core.security.verify_n8n_hmac`, `core.config.settings.N8N_WEBHOOK_SECRET`.
  - Will use (future): Supabase DAL for idempotent upsert.

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
  - Fields now: `ENV`, `N8N_WEBHOOK_SECRET`. Add Supabase/Web3/OAuth/Fees as you wire them.
  - Used by: `routes_webhooks.py` (secret), others in future.

- `app/core/security.py` — Security helpers.
  - `verify_n8n_hmac(raw: bytes, sig: str|None, ts: str|None, secret: str)` → raises `HTTPException(401)` on failure.
  - Used by: `routes_webhooks.py`.

- `app/services/payouts.py` — Pure money math (wei integers only).
  - `compute_payouts(stake_wei: int, percent_ppm: int, platform_fee_bps_fail=1000, reward_bps_of_fee=500)` → dict with:
    - `refund_wei, fail_wei, commission_wei, charity_wei, reward_from_commission_wei`.
  - Used by: settlement preview/execute endpoints (to mirror/validate on-chain results if needed).

- `app/models/` — Placeholder for Pydantic models/DB access.
  - Next: `models/db.py` with Supabase DAL (users, challenges, stakes, proofs, payouts, integration_tokens).

- `tests/test_payouts.py` — Validates money math (e.g., 90% completion, fee splits, edges). 4 tests pass.
- `tests/test_security.py` — Validates HMAC OK and stale timestamp failure.

- `requirements.txt` — Includes Flask (old prototype), FastAPI/Uvicorn/Pydantic, pydantic-settings, pytest.

- `old_backend/` — Legacy Flask app; not used by the new FastAPI service.

## Data & error contracts (current + target)
- Uniform error envelope (current fallback + stubs): `{ error: { code, message, details } }`.
- Webhook HMAC contract, time windows, settlement PPM, and contract methods are defined in `.github/copilot-instructions.md` Appendix.

## End-to-end flow (target)
1) n8n posts proofs (HMAC) → `/webhooks/proofs/{id}` → Supabase `proofs` (idempotent).
2) `/challenges/{id}/end` → locks challenge with `run_id` (UUID).
3) `/settlements/preview` → computes `percent_ppm` per user from proofs (UTC window-bounded).
4) `/settlements/execute` → web3 client calls `batchSettle`/`settleUser`, store tx hash + logs in `payouts`.

## Inputs/outputs quick reference
- Proof webhook input body: `{ provider, metric, user_wallet, value:int, day_key:date, window_start, window_end, source_payload_json, idempotency_key }`.
- Joins input: `{ user_wallet, amount_wei }`.
- Settlement execute input: `{ run_id: UUID, items:[{ user_wallet, percent_ppm:int }] }`.
- All money amounts are integers in wei. Percent is `percent_ppm` (0..1_000_000).

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
