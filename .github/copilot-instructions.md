# Copilot instructions for motify-backend

## What is this? 
This file contains instructions for GitHub Copilot to help it generate relevant code and text for this repository. It includes an overview of the app, its architecture, key routes, conventions, developer workflows, and target architecture for future development.

## Repository info
This is the repository for the backend. The frontend is in a separate repo. The contract is also separte. There is a folder called zold_backend which contains a previous version of the backend that is no longer in use.

## About the App
Motify is a Base-chain (L2 ETH) accountability app. Users stake into on-chain challenges, provide proof (Strava activity, GitHub commits), and receive proportional refunds; the failed portion goes to a predefined wallet (e.g., charity). Platform takes 10% of the failed portion; 5% of that fee fuels $MOTIFY rewards (handled in the contract).

## Architecture & data flow
- Single service in `app.py` using Flask + CORS + `requests`.
- In-memory globals: `challenges: {id -> Challenge}`, `user_stats: {wallet -> {participated, succeeded, total_amount}}`, `challenge_id_counter`.
- `Challenge` holds: `name, description, start_date, end_date, contract_address, goal, participants[{walletAddress, amountUsd}], completed`.
- Background worker `monitor_challenges()` (daemon thread) runs every 5s:
	- When a challenge’s `end_date` passes, marks it `completed` and for each participant calls n8n (`N8N_WEBHOOK_URL`) once to compute final success.
	- Expects n8n to return a list of day objects with `achieved` booleans; success = `all(day.achieved)`.
- CORS is restricted to: `https://motify-nine.vercel.app`, `http://localhost:8080`, `http://localhost:5173`.

## HTTP API (key routes)
- POST `/challenges` → create challenge. Body keys: `name, description, start_date, end_date, contract_address, goal` (ISO8601 dates).
- GET `/challenges` → list challenges.
- POST `/challenges/<int:id>/join` → join challenge. Body: `{ walletAddress, amountUsd }` (wallet deduped).
- POST `/challenges/<int:id>/progress` → on-demand progress for one wallet. Body: `{ goal, walletAddress }`. Returns `{ progress: [from n8n], currentlySucceeded: bool }`.
- GET `/users/<wallet>/stats` → aggregated counters computed when challenges complete.

## Conventions & gotchas
- JSON field style: participant fields use camelCase (`walletAddress`, `amountUsd`). Keep consistency when adding endpoints.
- Dates: parsed with `datetime.fromisoformat()`. Provide timezone-aware values (e.g., `2025-10-17T12:00:00+00:00`) to avoid naive vs aware comparison when checked against `datetime.now(timezone.utc)` in the monitor.
- State is in-memory and resets on process restart; concurrency is single-process, not safe for multi-worker without external store.
- The background thread starts only under `if __name__ == "__main__":` (local dev). If running under a WSGI server (e.g., gunicorn), this thread will NOT start unless explicitly wired.
- External integration: n8n webhook URL is hardcoded as `N8N_WEBHOOK_URL` in `app.py`. Update this constant to switch environments.

## Developer workflows
- Dependencies:
	- Runtime: see `requirements.txt` (Flask, Flask-CORS, requests, gunicorn).
	- Experimental FastAPI sample lives in `test.py`; its deps are in `requirments_test.txt` and are NOT used by the Flask app.
- Run (Windows cmd):
	```cmd
	python -m venv .venv
	.venv\Scripts\activate
	pip install -r requirements.txt
	python app.py
	```
- Example requests (after `python app.py`):
	```cmd
	curl -X POST http://127.0.0.1:5000/challenges -H "Content-Type: application/json" -d "{\"name\":\"Steps\",\"description\":\"10k/day\",\"start_date\":\"2025-10-01T00:00:00+00:00\",\"end_date\":\"2025-10-07T00:00:00+00:00\",\"contract_address\":\"0xabc...\",\"goal\":\"10000 steps/day\"}"
	curl -X POST http://127.0.0.1:5000/challenges/1/join -H "Content-Type: application/json" -d "{\"walletAddress\":\"0xWALLET\",\"amountUsd\":25}"
	```
- Production hint (Linux): `gunicorn app:app -w 2 -k gthread -b 0.0.0.0:8000`. Ensure the monitor thread is started via an app hook if you use WSGI (not auto-started under gunicorn).
 - Database schema changes: when adding/modifying tables, always update `docs/schema.sql` (single source of truth) and apply it in Supabase SQL Editor. Keep DAL methods and payload shapes consistent with the schema and indices (especially idempotency constraints).
 - Environment variables: when adding/updating envs, always reflect them in `.env.example` (document purpose and defaults). Never commit real secrets (`.env` is gitignored).

## Files to know
- `app.py` — entire Flask app, routes, background worker, n8n call logic.
- `requirements.txt` — runtime deps for Flask app.
- `requirments_test.txt` — deps for the sample `test.py` (FastAPI), not part of main service.
- `docs/ARCHITECTURE.md` — living "wiki" of modules, dependencies, inputs/outputs. Keep this updated when adding/changing APIs, payloads, or envs.
 - `docs/schema.sql` — authoritative DB schema for Supabase/Postgres. Update this file with every DB change and re-apply in Supabase.
 - `.env.example` — example environment file. Keep this in sync with required env vars across environments; do NOT commit `.env`.

---

## Target architecture (roadmap)
One-liner: Motify is a Base-chain accountability app. Users stake into on-chain challenges, provide proofs (Strava, GitHub), receive proportional refunds; failed portion goes to a predefined wallet. Platform takes 10% of failed portion; 5% of that fee fuels $MOTIFY rewards (on-chain).

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

Money math (wei integers)
refund=floor(A*p); fail=A-refund; commission=(fail*PLATFORM_FEE_BPS_FAIL)//10_000; charity=fail-commission; reward=(commission*REWARD_BPS_OF_FEE)//10_000

API surface (MVP)
- Users/Challenges/Leaderboards/Stats as listed in the context; proofs via `/webhooks/proofs/{id}` (verify HMAC); settlements preview/execute endpoints; OAuth start/callback and integrations CRUD.

Security & integrity
- Webhook HMAC: verify `X-N8N-Signature` using `N8N_WEBHOOK_SECRET`.
- Idempotency: accept `Idempotency-Key`; dedupe (challenge_id, user_wallet, run_id).
- AuthZ: owner-only for invite/end/execute; only server signer calls on-chain tx.
- Windows: count proofs for `start_at ≤ day_key ≤ end_at` only.

Env vars (indicative)
- Supabase: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `DATABASE_URL`
- Web3/Contract: `WEB3_RPC_URL`, `MOTIFY_CONTRACT_ADDRESS`, `MOTIFY_CONTRACT_ABI_PATH`, `SERVER_SIGNER_PRIVATE_KEY`
- OAuth: STRAVA/GITHUB client ids/secrets and redirect URIs
- n8n: `N8N_WEBHOOK_SECRET`
- Fees: `PLATFORM_FEE_BPS_FAIL` (default 1000), `REWARD_BPS_OF_FEE` (default 500)
- Token encryption: `TOKEN_ENC_KEY`; defaults: stake token/address/decimals

Suggested layout (for refactor)
`app/main.py`, `api/routes_*.py`, `core/config.py`, `core/security.py`, `models/db.py`, `services/{proofs,payouts,web3client,leaderboards,oauth}.py`, `abi/Motify.json`, `tests/`

Implementation guidance
- Strong type hints and Pydantic models; pure functions for proofs/payouts; wei-only arithmetic.
- Never trust client-reported percentages; accept normalized proofs from n8n only.
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
- Events: `ChallengeEnded(challengeId, endedBy, endedAt)`, `UserSettled(challengeId, user, percentPpm, refundWei, charityWei, commissionWei, rewardFromCommissionWei, runId)`
- On-chain math: `refund=stake*percentPpm/1_000_000; fail=stake-refund; commission=fail*PLATFORM_FEE_BPS_FAIL/10_000; charity=fail-commission; rewardFromFee=commission*REWARD_BPS_OF_FEE/10_000`.

5) Supabase schema — keys & indices (essentials)
- users: `wallet TEXT PRIMARY KEY`
- challenges: `id BIGSERIAL PK`, index `owner_wallet`
- stakes: `UNIQUE(challenge_id, user_wallet)`
- proofs: `UNIQUE(challenge_id, user_wallet, provider, metric, day_key)`, `UNIQUE(idempotency_key)`, index `(challenge_id, day_key)`
- payouts: `UNIQUE(challenge_id, user_wallet, run_id)`, index `challenge_id`
- integration_tokens: `PRIMARY KEY(wallet, provider)`, `UNIQUE(provider, provider_user_id)`
- Types: `numeric(78,0)` for wei; `jsonb` for payloads/policies.

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
- OK to log: wallet addresses, `challenge_id`, numeric wei amounts, `run_id`, endpoint/status.
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
