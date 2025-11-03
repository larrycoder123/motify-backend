# Motify Backend

The backend service for Motify — a decentralized accountability platform that monitors user progress via external APIs (GitHub, Farcaster, WakaTime) and settles refunds on-chain through automated smart contract interactions.

This repository provides:
- **REST API** for health checks, user statistics, and OAuth token management
- **Background Jobs** for indexing challenges, computing progress, and declaring results on Base (L2 Ethereum)
- **Progress Engines** that integrate with GitHub, Farcaster (via Neynar), and WakaTime to verify goal completion

---

## Table of Contents

- [Overview](#overview)
- [Other Repositories](#other-repositories)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [How It Works](#how-it-works)
- [API Endpoints](#api-endpoints)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Progress Engines](#progress-engines)
- [OAuth Security](#oauth-security)
- [Deployment](#deployment)
- [Scheduled Processing](#scheduled-processing)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

Motify enables users to create and participate in blockchain-verified challenges with real stakes (USDC). The backend automates the entire accountability lifecycle:

1. **Index** ended challenges from the Motify smart contract
2. **Fetch Progress** from external APIs based on each challenge's activity type
3. **Compute Refunds** as percentages based on goal completion (0–100%)
4. **Declare Results** on-chain via `declareResults()` transaction
5. **Archive** processed data for user statistics and historical records

By separating progress verification (off-chain APIs) from settlement (on-chain execution), Motify ensures transparency, trustlessness, and real-world accountability.

---

## Other Repositories

- **[Smart Contracts](https://github.com/etaaa/motify-smart-contracts):** Challenge and token contracts deployed on Base (L2 Ethereum)
- **[Frontend](https://github.com/eliaslehner/Motify):** React-based dApp built as a Base Mini App, providing the user interface for creating, joining, and tracking challenges

---

## Features

- **Multi-Provider Progress Tracking**: Supports GitHub (commits/contributions), Farcaster (casts), and WakaTime (coding time)
- **Automated On-Chain Settlement**: Declares results and processes refunds via EIP-1559 transactions with configurable fee caps
- **OAuth Integration**: Secure token management with wallet signature verification (supports EOA and smart contract wallets)
- **Flexible Fallback Logic**: Protects users during API outages with configurable default refund percentages
- **Real-Time Statistics**: Provides aggregated user stats (challenges participated, success rate, total refunds)
- **Dry-Run Mode**: Test entire pipeline without sending transactions
- **Safety Guards**: Skips sending if all progress is missing or if reconciliation detects on-chain state changes

---

## Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Database**: [Supabase](https://supabase.com/) (Postgres)
- **Blockchain**: [Web3.py](https://web3py.readthedocs.io/) with EIP-1559 support
- **APIs**: GitHub GraphQL, Neynar (Farcaster), WakaTime REST
- **Deployment**: [Render](https://render.com/) for API hosting, [GitHub Actions](https://github.com/features/actions) for scheduled jobs
- **Testing**: [pytest](https://pytest.org/)

---

## How It Works

### Workflow (Every 15 Minutes via GitHub Actions)

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
│     - Use EIP-1559 with MAX_FEE_GWEI cap                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. ARCHIVAL                                                    │
│     - Move processed data to finished_challenges table         │
│     - Store tx hashes, ratios, and refund amounts              │
│     - Clean up working cache                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Safety Mechanisms

- **Progress Missing Guard**: Skips sending if all participants have `progress_ratio=None` (API outage)
- **On-Chain Reconciliation**: Checks contract state to avoid duplicate declares
- **Configurable Fallback**: `DEFAULT_PERCENT_PPM` protects users when individual progress can't be fetched (defaults to 100%)
- **Dry-Run Mode**: Set `SEND_TX=false` to preview payloads without blockchain writes

---

## API Endpoints

### Public
- `GET /health` → Health check with database connectivity status
- `GET /stats/user?address=0x...` → Aggregated statistics for a wallet (challenges participated, success rate, total refunds)
- `GET /oauth/providers` → List available OAuth providers (github, wakatime)

### OAuth (Signature Required)
- `GET /oauth/status/{provider}/{wallet_address}` → Check if wallet has valid credentials
- `GET /oauth/connect/{provider}?wallet_address=0x...&signature=0x...&timestamp=123` → Initiate OAuth flow
- `GET /oauth/callback/{provider}?code=...&state=...` → OAuth callback (redirects to frontend)
- `DELETE /oauth/disconnect/{provider}/{wallet_address}?signature=0x...&timestamp=123` → Remove credentials

*All OAuth connect/disconnect operations require wallet signature verification (supports EOA and smart contract wallets).*

## Installation

### Prerequisites
- Python 3.11+
- Virtual environment tool (venv)
- PostgreSQL database (we use Supabase)
- Base RPC endpoint (for blockchain interactions)

### Local Setup (Windows)

```bash
# 1. Create virtual environment
python -m venv .venv

# 2. Activate environment
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment template
copy .env.example .env

# 5. Configure .env (see Configuration section)

# 6. Start development server
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Running Tests

```bash
pytest -q
```

---

## Configuration

Create a `.env` file in the project root with the following variables:

### Required (Core)
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
```

### Required (OAuth)
```env
# GitHub OAuth
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret

# Neynar (for Farcaster progress)
NEYNAR_API_KEY=your-neynar-api-key

# Frontend URL (for OAuth redirects)
FRONTEND_URL=https://your-frontend-url.com
BACKEND_URL=https://your-backend-url.com
```

### Optional
```env
# EIP-1559 Fee Control
MAX_FEE_GWEI=1.0  # Max fee per gas in Gwei

# Token Configuration
STAKE_TOKEN_DECIMALS=6  # USDC has 6 decimals

# Fallback Behavior
DEFAULT_PERCENT_PPM=1000000  # 100% refund when progress unavailable

# Job Security
CRON_SECRET=random-secret-for-job-endpoints

# WakaTime API
WAKATIME_API_BASE_URL=https://api.wakatime.com/api/v1/

# Token Lookup (auto-configured in GitHub Actions)
USER_TOKENS_TABLE=user_tokens
USER_TOKENS_WALLET_COL=wallet_address
USER_TOKENS_PROVIDER_COL=provider
USER_TOKENS_ACCESS_TOKEN_COL=access_token

# Environment
ENV=development  # or 'production'
```

See `.env.example` for a complete template.

---

## Usage

### Start API Server

```bash
.venv\Scripts\activate
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

API will be available at `http://127.0.0.1:8000`

### Run Background Job Locally

```bash
# Dry-run (no transactions)
python -m app.jobs.process_ready_all

# Live run (sends transactions)
SEND_TX=true python -m app.jobs.process_ready_all
```

### Quick Health Check

```bash
curl http://127.0.0.1:8000/health
```

---

## Deployment

### Render (API Server)

One-click deployment using `render.yaml`:

1. Create a new Web Service from this repository
2. Render will auto-detect `render.yaml` and configure:
   - **Environment**: Python 3.11
   - **Build**: `pip install --upgrade pip && pip install -r requirements.txt`
   - **Start**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

3. Set environment variables in Render dashboard:
   ```
   SUPABASE_URL
   SUPABASE_SERVICE_ROLE_KEY
   WEB3_RPC_URL
   MOTIFY_CONTRACT_ADDRESS
   GITHUB_CLIENT_ID
   GITHUB_CLIENT_SECRET
   NEYNAR_API_KEY
   FRONTEND_URL
   BACKEND_URL
   ```

*Note: For API-only hosting (no transaction signing), you don't need `PRIVATE_KEY`.*

---

## Scheduled Processing

### GitHub Actions (Background Jobs)

The `.github/workflows/process-ready.yml` workflow runs every 15 minutes to:
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
PRIVATE_KEY              # For transaction signing
NEYNAR_API_KEY           # For Farcaster progress
SEND_TX=true             # Enable on-chain writes
MAX_FEE_GWEI             # Optional fee cap
DEFAULT_PERCENT_PPM      # Optional fallback (default: 1000000)
```

**Workflow Features:**
- Runs on schedule (`cron: '*/15 * * * *'`) and manual dispatch
- Captures full logs as downloadable artifacts (14-day retention)
- Preflight checks for token lookup configuration
- Automatic retry on transient failures

**View Logs:**
1. Go to Actions tab in GitHub
2. Select latest "Process ready challenges" run
3. Download `process-ready-log` artifact

---

## OAuth Security

**All OAuth connect and disconnect operations require wallet signature verification** to prevent unauthorized users from linking/unlinking credentials to wallets they don't own.

### Wallet Support

The backend supports both:
- **EOA wallets** (MetaMask, Ledger, etc.) - 65-byte ECDSA signatures
- **Smart contract wallets** (Base Wallet, Coinbase Smart Wallet, etc.) - ERC-1271/ERC-6492 signatures

No changes needed in your frontend - the backend automatically detects and verifies the appropriate signature format.

### Signature Requirements

When calling `/oauth/connect` or `/oauth/disconnect`, you must provide:
1. `wallet_address` - The wallet address
2. `signature` - Wallet signature (supports both EOA and smart wallet formats)
3. `timestamp` - Unix timestamp (must be within 5 minutes)

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

// Signature will be 1000+ bytes (ERC-1271/ERC-6492) - this is normal!
fetch(`/oauth/connect/github?wallet_address=${accounts[0]}&signature=${signature}&timestamp=${timestamp}`);
```

**Using MetaMask (still supported):**
```javascript
const signer = await provider.getSigner();
const timestamp = Math.floor(Date.now() / 1000);
const message = `Connect OAuth provider github to wallet ${address.toLowerCase()} at ${timestamp}`;
const signature = await signer.signMessage(message);

// Signature will be 65 bytes
fetch(`/oauth/connect/github?wallet_address=${address}&signature=${signature}&timestamp=${timestamp}`);
```

See `examples/base_wallet_oauth_integration.js` for complete Base Wallet integration and `examples/frontend_oauth_integration.js` for MetaMask examples.

### Configuration for Smart Wallets

To support smart wallet signatures, set in `.env`:
```bash
WEB3_RPC_URL=https://mainnet.base.org  # or https://sepolia.base.org for testnet
ENV=production  # or 'development' for testnet
```

📖 **For detailed migration guide and troubleshooting, see:** `docs/BASE_WALLET_OAUTH.md`

---

## Progress Engines

The backend supports three activity types for challenge verification:

### GitHub (Commits/Contributions Per Day)
- Uses GitHub GraphQL contributions calendar to count per-day contributions in the challenge window.
- Requires a token per wallet stored in Supabase `user_tokens` with `provider=github` and `access_token` set to the GitHub token.
- Scope: with `user:email`, only public contributions are counted; to include private, request `repo` scope and reconnect.
- Fallback: if a participant has no token or the call fails, their percent defaults to `DEFAULT_PERCENT_PPM` (1_000_000 by default = 100%).

### Farcaster (one cast per day)
- Uses Neynar to count per-day casts in the challenge window.
- User resolution order:
  1) If `user_tokens` has `provider=farcaster` and `access_token` is a numeric string, it's treated as FID and used.
  2) Otherwise, resolve FID from wallet via Neynar bulk API: `/v2/farcaster/user/bulk-by-address/?addresses=0x...`.
  3) If still not found, try verifications API: `/v2/farcaster/verification/by-address?address=0x...` (requires the wallet be verified on profile).
  4) If all fail, the participant falls back to `DEFAULT_PERCENT_PPM`.
- Env: set `NEYNAR_API_KEY`.
 - Optional: if your Neynar plan exposes a different endpoint for listing casts, set `FARCASTER_USER_CASTS_URL` to override the default `https://api.neynar.com/v2/farcaster/feed/user/casts/`.
 - Notes: we request `include_replies=true` and handle pagination via the `next.cursor` value returned by the API.
- Optional: to guarantee resolution without relying on verifications, store the user’s FID in `user_tokens` (`provider=farcaster`, `access_token="<fid>"`).

### Quick testing (Python REPL)
```python
from datetime import date, timedelta
from app.services.progress import _github_ratio_for_user, ratio_to_ppm, _resolve_farcaster_fid_for_address, _farcaster_ratio_for_fid
import os

# GitHub (needs GITHUB_TOKEN)
gtoken = os.getenv('GITHUB_TOKEN')
end = date.today() - timedelta(days=1)
start = end - timedelta(days=13)
if gtoken:
  gr = _github_ratio_for_user(gtoken, start, end, required_per_day=1)
  print('github ratio:', gr, 'ppm:', ratio_to_ppm(gr))
else:
  print('Set GITHUB_TOKEN to test GitHub progress')

# Farcaster (needs NEYNAR_API_KEY)
api_key = os.getenv('NEYNAR_API_KEY')
addr = '0x...'  # set a wallet verified on Farcaster
if api_key:
  fid = _resolve_farcaster_fid_for_address(api_key, addr.lower())
  print('resolved fid:', fid)
  if fid:
    fr = _farcaster_ratio_for_fid(api_key, fid, start, end, required_per_day=1)
    print('farcaster ratio:', fr, 'ppm:', ratio_to_ppm(fr))
  else:
    print('No FID found (no Farcaster verification) → fallback will apply')
else:
  print('Set NEYNAR_API_KEY to test Farcaster progress')

# WakaTime
wakatime_key = 'waka_...'  # Your WakaTime API key
tokens = {addr.lower(): wakatime_key}
participants = [{'participant_address': addr}]
window = (int(start.strftime('%s')), int(end.strftime('%s')))
result = _progress_wakatime(tokens, participants, window=window, goal_type='coding-time', goal_amount=10)
print(f'WakaTime result: {result}')
```

---

## Additional Resources

- **Database Schema**: `docs/schema.sql` - Supabase table definitions
- **Smart Contract ABI**: `abi/Motify.json` - Contract interface for Web3 calls
- **OAuth Examples**:
  - `examples/base_wallet_oauth_integration.js` - Base Wallet signature examples
  - `examples/frontend_oauth_integration.js` - MetaMask integration examples
- **Architecture Docs**: `docs/ARCHITECTURE.md` - Detailed system design
- **Base Wallet Guide**: `docs/BASE_WALLET_OAUTH.md` - Smart wallet migration guide

---

## Notes

- **CORS**: Dev environment allows `localhost`. Production origins are configured in `app/main.py` (currently includes `https://motify.live` and `https://www.motify.live`)
- **Signature Verification**: OAuth operations use EIP-191 (EOA) or ERC-1271/ERC-6492 (smart wallets) for wallet ownership verification
- **Timezone**: All progress engines use UTC for consistency. GitHub and Farcaster use UTC days; WakaTime queries with `timezone=UTC`
- **Fallback Protection**: Set `DEFAULT_PERCENT_PPM=1000000` to protect users during API outages (defaults to 100% refund when progress unavailable)

---

## Contributing

We welcome contributions! Please:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License.
