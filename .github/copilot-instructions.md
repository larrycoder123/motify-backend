# Copilot instructions for motify-backend

## What is this?
This file guides GitHub Copilot to generate relevant code and docs for this repository. It summarizes the app’s purpose, current architecture, routes, workflows, conventions, and the target design. Use it as a context primer when adding or modifying code.

## Repository info
- This is the backend repo. The frontend lives in a separate repo. The smart contract is also separate.
- `zold_backend/` contains an earlier Flask prototype that is no longer in use. The active service is FastAPI under `app/`.

## About the app
Motify is a Base-chain (L2 ETH) accountability app. Users stake into on-chain challenges, provide proofs (Strava/GitHub), and receive proportional refunds; the failed portion goes to a predefined wallet (e.g., charity). The platform takes 10% of the failed portion; 5% of that fee fuels $MOTIFY rewards (handled on-chain).

## Current architecture & data flow
- Framework: FastAPI app in `app/main.py` with modular routers in `app/api/` and service layers in `app/services/`.
- Data: Supabase (Postgres) via supabase-py with RLS. Schema is defined in `docs/schema.sql`.
- Chain: Optional listener (web3.py) that tails the Motify contract for events; updates challenges when on-chain `ChallengeCreated` fires.
- Workflows: n8n handles OAuth/provider fetching/normalization and posts proofs to the backend webhook with HMAC.
- CORS: Allowed dev origins are configured in `app/main.py` and widened per environment.

### HTTP API (key routes)
- POST `/challenges/` → create a challenge (status=pending). Body keys: `name, description, start_date, end_date, contract_address, goal, owner_wallet?, on_chain_challenge_id?, description_hash?`.
- GET `/challenges/` → list challenges (selects `*` to be schema-forward-compatible). Includes `created_tx_hash` and `created_block_number` when present.
- GET `/challenges/{id}` → fetch a single challenge by id.
- POST `/challenges/{id}/join` → join challenge. Body: `{ user_wallet, amount_minor_units }` (backward-compatible: accepts `amount_wei` and maps it to `amount_minor_units`); idempotent upsert on `(challenge_id, user_wallet)`.
- POST `/webhooks/proofs/{challenge_id}` → n8n webhook; verifies HMAC; upserts proof by `idempotency_key` when service-role key is present. Responds `{ status: "accepted", stored: bool }`.
- GET `/health` → `{ ok: true, db: bool }`.

### Chain listener
- Configured by env: `ENABLE_CHAIN_LISTENER`, `WEB3_RPC_URL`, `MOTIFY_CONTRACT_ADDRESS`, `MOTIFY_CONTRACT_ABI_PATH`, `CHAIN_CONFIRMATIONS`, `CHAIN_POLL_SECONDS`.
- Uses web3.py v6. Polls logs in safe chunks (e.g., 250 blocks) with `from_block`/`to_block` to avoid provider limits. Each `ChallengeCreated` event triggers a handler that attaches `on_chain_challenge_id`, marks `status='active'`, sets `owner_wallet`, and stores `created_tx_hash` + `created_block_number`.
- The listener is optional and won’t crash the API on failures.

### Conventions & gotchas
- JSON fields: API generally uses snake_case; when interacting with FE payloads, keep consistent shapes as documented in routes and tests.
- Dates: UTC everywhere. Use ISO8601 with timezone (e.g., `2025-10-17T12:00:00+00:00`).
- Security: Never trust client-reported percentages; accept normalized proofs from n8n only. Verify proofs webhook with HMAC.
- State: All state is persisted in Supabase. The service is stateless; listener uses DB to correlate rows.

## Developer workflows
- Dependencies: See `requirements.txt` (FastAPI, Uvicorn, Pydantic, requests, supabase, web3, pytest, python-dotenv). The legacy Flask app lives in `zold_backend/` and has its own `requirements.txt`.
- Local run (Windows cmd):
  1) `python -m venv .venv`
  2) `.venv\Scripts\activate`
  3) `pip install -r requirements.txt`
  4) `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- Tests: `pytest -q`. Some integration tests skip unless Supabase env vars are set.
- Schema changes: Update `docs/schema.sql` and apply in Supabase. Keep DAL and payloads in sync.
- Env vars: When adding/updating envs, also document them in `.env.example` (don’t commit real secrets).

## Files to know
- `app/main.py` — App factory, routers, global error handler, optional chain listener boot.
- `app/api/routes_*.py` — Routers: `health`, `challenges`, `webhooks`, `users`, `integrations`, `leaderboards`, `chain` (simulate).
- `app/services/web3client.py` — Web3 listener with chunked polling; decodes events and invokes callbacks.
- `app/services/chain_handlers.py` — Attaches on-chain ids, updates `status`, `owner_wallet`, and tx metadata.
- `app/models/db.py` — Supabase DAL and small data models.
- `docs/schema.sql` — Authoritative DB schema with RLS and policies. Includes `created_tx_hash` and `created_block_number` in `challenges`.
- `scripts/watch_listener.py`, `scripts/scan_events.py` — Dev tools for monitoring or diagnosing chain events.
- `tests/` — API and unit tests: creation flow, webhook HMAC, payouts math, DB connectivity, chain simulation.
- `zold_backend/` — Legacy Flask app (not used by the FastAPI service).

---

## Target architecture (roadmap)
One-liner: Motify is a Base-chain accountability app. Users stake into on-chain challenges, provide proofs (Strava/GitHub), receive proportional refunds; failed portion goes to a predefined wallet. Platform takes 10% of failed portion; 5% of that fee fuels $MOTIFY rewards (on-chain).

Tech stack target
- Backend: Python 3.11+, FastAPI, Uvicorn, Pydantic, pytest
- DB: Supabase (Postgres) via supabase-py
- Web3: web3.py → Motify contract on Base (server signer)
- Workflows: n8n (OAuth, refresh, provider fetch, normalize → webhook to backend)

High-level flow
Frontend ↔ REST/JSON ↔ FastAPI
FastAPI → Supabase (users, challenges, stakes, proofs, payouts, tokens, stats)
  → web3.py (refund/sendTo/end via server signer)
  ↔ n8n (providers) → posts proofs to `/webhooks/proofs/{id}` with HMAC

Core concepts
- Challenges on-chain, mirrored in DB; users stake (USDC on Base).
- n8n fetches proofs using stored OAuth tokens; backend ingests and aggregates per day.
- Percent complete p = completed_days / total_days (≤ 1.0). Settlement prorates refund.

Money math (token minor units, integers)
refund=floor(A*p); fail=A-refund; commission=(fail*PLATFORM_FEE_BPS_FAIL)//10_000; charity=fail-commission; reward=(commission*REWARD_BPS_OF_FEE)//10_000

API surface (MVP)
- Users/Challenges/Leaderboards/Stats as listed; proofs via `/webhooks/proofs/{id}` (verify HMAC); settlements preview/execute endpoints; OAuth start/callback and integrations CRUD.

Security & integrity
- Webhook HMAC: verify `X-N8N-Signature` using `N8N_WEBHOOK_SECRET`.
- Idempotency: accept `Idempotency-Key`; dedupe (challenge_id, user_wallet, run_id).
- AuthZ: owner-only for invite/end/execute; only server signer calls on-chain tx.
- Windows: count proofs for `start_at ≤ day_key ≤ end_at` only.

Env vars (indicative)
- Supabase: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`
- Web3/Contract: `WEB3_RPC_URL`, `MOTIFY_CONTRACT_ADDRESS`, `MOTIFY_CONTRACT_ABI_PATH`, `SERVER_SIGNER_PRIVATE_KEY`
- OAuth: STRAVA/GITHUB client ids/secrets and redirect URIs
- n8n: `N8N_WEBHOOK_SECRET`
- Fees: `PLATFORM_FEE_BPS_FAIL` (default 1000), `REWARD_BPS_OF_FEE` (default 500)
- Token encryption: `TOKEN_ENC_KEY`; defaults: stake token/address/decimals

Suggested layout
`app/main.py`, `api/routes_*.py`, `core/config.py`, `core/security.py`, `models/db.py`, `services/{proofs,payouts,web3client,leaderboards,oauth}.py`, `abi/Motify.json`, `tests/`

Implementation guidance
- Strong type hints and Pydantic models; pure functions for proofs/payouts; integer arithmetic in token minor units.
- Never trust client-provided percentages; accept normalized proofs from n8n only.
- Keep secrets in env; never log private keys or tokens.

If anything above is unclear (e.g., HMAC format, exact Supabase schema, contract method names), call it out and we’ll refine quickly.

---

## Appendix — Precise contracts & on-chain percent settlement

1) n8n → backend webhook (proofs)
- Endpoint: POST `/webhooks/proofs/{challenge_id}`
- Headers: `Content-Type: application/json`, `X-N8N-Signature: <hex HMAC-SHA256(raw_body)>`, `X-N8N-Timestamp: <unix seconds>`
- HMAC: Algorithm HMAC-SHA256; Secret `N8N_WEBHOOK_SECRET`; Message = raw request body bytes. Reject if |now − timestamp| > 300s or signature mismatch.
- Request JSON example:
  `{ "provider":"strava", "metric":"activity_minutes", "user_wallet":"0xAbC...", "value":87, "day_key":"2025-10-16", "window_start":"2025-10-16T00:00:00Z", "window_end":"2025-10-16T23:59:59Z", "source_payload_json":{...}, "idempotency_key":"proof:strava:0xabc...:2025-10-16" }`
- Responses: `202 Accepted → { "status":"accepted", "challenge_id": 42, "stored": true }`; Errors use uniform error contract below.
- Optional progress ping: POST `/challenges/{id}/progress` with `{ user_wallet, percent_complete_hint, as_of, idempotency_key }`.
- Verify helper (FastAPI reference):
  ```python
  import hmac, hashlib, time
  from fastapi import Header, HTTPException
  def verify_n8n_hmac(raw: bytes, sig: str|None, ts: str|None, secret: str):
      if not sig or not ts: raise HTTPException(401, "Missing signature headers")
      if abs(int(time.time()) - int(ts)) > 300: raise HTTPException(401, "Stale timestamp")
      digest = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
      if not hmac.compare_digest(digest, (sig or "").lower()): raise HTTPException(401, "Bad signature")
  ```

2) Time windows & day bucketing
- Timezone: UTC everywhere (DB timestamps, `day_key`, windows).
- Bucket rule: event counts toward the UTC calendar day it occurred in.
- Inclusivity: include `start_at 00:00:00Z` and `end_at 23:59:59.999Z`.
- Daily success: success if aggregated metric for `day_key` ≥ `proof_policy.per_day_target`.
- Example `challenge.proof_policy`: `{ "metric":"activity_minutes", "per_day_target":30, "min_success_days":90 }`.
- Percent complete: `completed_days / total_days` capped at 1.0; missing days = 0.

3) Settlement semantics (preview vs execute)
- Preview (POST `/challenges/{id}/settlements/preview`): pure compute; no state change.
- Lock (POST `/challenges/{id}/end`): marks status locked; records `settlement_run_id` (UUID); no further proofs/deposits.
- Execute (POST `/challenges/{id}/settlements/execute`): requires locked; header `Idempotency-Key: settle:<challenge_id>:<run_id>`; body `{ run_id, items:[{ user_wallet, percent_ppm }] }`.
- Precision: PPM integers; `percent_ppm = round(percent * 1_000_000)`; validate `0 ≤ percent_ppm ≤ 1_000_000`.
- Backend never accepts client-provided percentages—derive from verified proofs only.

4) Contract interface (Base)
- ABI path: `./abi/Motify.json` (env-scoped address).
- Methods:
  - `endChallenge(uint256 challengeId)`
  - `settleUser(uint256 challengeId, address user, uint32 percentPpm, bytes32 runId)`
  - `batchSettle(uint256 challengeId, address[] users, uint32[] percentsPpm, bytes32 runId)`
- Events: `ChallengeEnded(challengeId, endedBy, endedAt)`, `UserSettled(challengeId, user, percentPpm, refundAmount, charityAmount, commissionAmount, rewardFromCommissionAmount, runId)`
- On-chain math: `refund=stake*percentPpm/1_000_000; fail=stake-refund; commission=fail*PLATFORM_FEE_BPS_FAIL/10_000; charity=fail-commission; rewardFromFee=commission*REWARD_BPS_OF_FEE/10_000`.

5) Supabase schema — keys & indices (essentials)
- users: `wallet TEXT PRIMARY KEY`
- challenges: `id BIGSERIAL PK`, index `owner_wallet`
- stakes: `UNIQUE(challenge_id, user_wallet)`
- proofs: `UNIQUE(challenge_id, user_wallet, provider, metric, day_key)`, `UNIQUE(idempotency_key)`, index `(challenge_id, day_key)`
- payouts: `UNIQUE(challenge_id, user_wallet, run_id)`, index `challenge_id`
- integration_tokens: `PRIMARY KEY(wallet, provider)`, `UNIQUE(provider, provider_user_id)`
- Types: `numeric(78,0)` for token minor-unit amounts; `jsonb` for payloads/policies.

6) OAuth scopes & redirects
- Strava scopes: `read,activity:read_all`; Redirects: Dev `http://localhost:8000/integrations/strava/callback`, Staging `https://staging-api.motify.app/integrations/strava/callback`, Prod `https://api.motify.app/integrations/strava/callback`.
- GitHub scopes: `read:user,public_repo` (add `repo,read:org` if needed); Redirects: Dev `http://localhost:8000/integrations/github/callback`, Staging `https://staging-api.motify.app/integrations/github/callback`, Prod `https://api.motify.app/integrations/github/callback`.
- Token storage: table `integration_tokens` (encrypted `access_token_enc`, `refresh_token_enc`, `expires_at`); n8n refreshes and posts proofs.

7) CORS & environments (allowed origins)
- Local: `http://localhost:3000`, `http://localhost:5173`, `http://127.0.0.1:3000`
- Staging: `https://staging.motify.app`, `https://staging-api.motify.app`
- Prod: `https://app.motify.app`, `https://api.motify.app`
- (Optional) n8n UI per env: `https://n8n.motify.app`

8) Error response contract (uniform)
```json
{ "error": { "code": "STRING_CODE", "message": "Human readable", "details": { } } }
```
Common: BAD_REQUEST, UNAUTHORIZED, FORBIDDEN, NOT_FOUND, IDEMPOTENT, VALIDATION_FAILED, CONFLICT, PROVIDER_ERROR, CHAIN_TX_FAILED, RATE_LIMITED, INTERNAL.

9) Logging & PII
- OK to log: wallet addresses, `challenge_id`, numeric minor-unit amounts, `run_id`, endpoint/status.
- Do NOT log: access/refresh tokens, private keys, webhook secrets, full `source_payload_json` (log hash/size only), HMACs.
- Provider IDs: store full in DB; redact in logs: `gh:****{last4}`, `strava:****{last4}`.

10) Rate limits & backoff
- Provider 429: exponential backoff + jitter (1s, 2s, 4s; +0–300ms), max 3 retries.
- On-chain: serialize tx per signer; handle nonce conflicts with small retry; surface revert reasons.

11) Web3 client signatures (backend)
- Python signatures:
  - `def settle_user(self, challenge_id: int, user: str, percent_ppm: int, run_id: bytes) -> str: ...`
  - `def batch_settle(self, challenge_id: int, users: list[str], percents_ppm: list[int], run_id: bytes) -> str: ...`
  - `def end_challenge(self, challenge_id: int) -> str: ...`
- Validation: `0 ≤ percent_ppm ≤ 1_000_000`; `len(users) == len(percents_ppm)`; `run_id` is 32 bytes (UUID → bytes32).
- Backend computes `percent_ppm` from verified proofs; enforce cap `≤ 1_000_000`.
