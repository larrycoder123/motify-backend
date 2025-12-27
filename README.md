# Motify Backend

> **A Web3 Accountability App Built on Base**

[![Demo Video](https://img.shields.io/badge/YouTube-Demo_Video-red?logo=youtube)](https://youtu.be/7yhsUFMNui4?si=MOPQ7W9MtYeelZBL)
[![Live Product](https://img.shields.io/badge/🌐-motify.live-blue)](https://motify.live/)
[![Devfolio](https://img.shields.io/badge/Devfolio-Project_Page-purple)](https://devfolio.co/projects/test-a97f)

---

## 🎬 Demo Video

<a href="https://youtu.be/7yhsUFMNui4?si=MOPQ7W9MtYeelZBL" target="_blank">
  <img src="https://img.youtube.com/vi/7yhsUFMNui4/maxresdefault.jpg" alt="Motify Demo" width="100%">
</a>

*Click to watch the full demo on YouTube*

---

## 🏆 Project Overview

**Motify** is a Web3 application built on **Base (Coinbase's L2)** that leverages smart contracts and wallet integrations to enable on-chain execution and token-based accountability incentives.

Users commit to goals with crypto stakes (USDC), and this backend handles OAuth integration, progress tracking via external APIs, and automated on-chain result declaration.

| | |
|---|---|
| **Domain** | Web3 · Smart Contracts · Wallet Integration · On-chain Incentives |
| **Tech Stack** | FastAPI · Supabase · Web3.py · React · Solidity |
| **Blockchain** | Base (L2 Ethereum by Coinbase) |

---

## 🔗 Links & Resources

| Resource | Link |
|----------|------|
| 🎬 Demo Video | [YouTube](https://youtu.be/7yhsUFMNui4?si=MOPQ7W9MtYeelZBL) |
| 🌐 Live Product | [motify.live](https://motify.live/) |
| 📋 Devfolio Application | [Project Page](https://devfolio.co/projects/test-a97f) |
| 💻 Frontend Repo | [GitHub](https://github.com/eliaslehner/Motify) |
| 📜 Smart Contracts | [GitHub](https://github.com/etaaa/motify-smart-contracts) |

---

## 🎯 Key Achievements

| Achievement | Description |
|-------------|-------------|
| 🏆 **Hackathon Winner** | Winner of Start Hackathon Vienna |
| 🌍 **Top 50 Global** | Selected from 900+ teams in Base Global Buildathon |
| 💰 **$5,000 Grant** | Base Builder Grant from Coinbase |
| 🔗 **Live MVP** | Deployed and running on Base mainnet |
| 🎤 **International Pitch** | Presented to a global Web3 audience |

---

## 📈 Project Lifecycle

### 1️⃣ Ideation & Prototype (Start Hackathon Vienna)

The project started during **Start Hackathon Vienna**, where Base (by Coinbase) provided a real-world case challenge to work on in **36 hours**:

> **Build a meaningful product on the Base ecosystem.**

- Developed the **core idea and product vision**
- Designed the **on-chain logic and incentive structure**
- Built a **working prototype** and pitch deck
- **Outcome:** 🏆 **Winner Overall** of the Hackathon (Base / Coinbase Case Challenge)

### 2️⃣ Validation & Scaling (Base Global Buildathon)

- Motivated by the local win, we applied to the **global Base Buildathon**
- Competing against **900+ teams worldwide**
- Expanded from prototype → **functional MVP**
- Implemented live smart contracts, wallet execution, and full backend + frontend integration
- **Outcome:** 🎖 **Top 50 globally** + 💰 **$5,000 Builder Grant**

<p align="center">
  <img src="images/Buildathon.jpg" width="50%" alt="Buildathon Photo" />
</p>

### 3️⃣ MVP & Live Product

- Fully integrated **frontend, backend, and on-chain components**
- End-to-end flow: wallet connection → smart contract interaction → token execution
- Focus on **stability, demo-readiness, and real usage**

---

## 👥 Team

| **Michi** | **Lenny** | **Gabriel** |
|-----------|-----------|-------------|
| Backend & Integration | Frontend & Wallet Integration | Smart Contracts & On-Chain Logic |
| FastAPI, OAuth, Web3.py | React, Base Wallet | Solidity, Contract Deployment |

---

## 📸 Hackathon Gallery

<p align="center">
  <img src="images/Hackathon1.jpg" width="45%" alt="Hackathon Photo 1" />
  <img src="images/Hackathon2.jpg" width="45%" alt="Hackathon Photo 2" />
</p>

<p align="center">
  <img src="images/Hackathon3.jpg" width="45%" alt="Hackathon Photo 3" />
  <img src="images/Hackathon4.jpg" width="45%" alt="Hackathon Photo 4" />
</p>

<p align="center">
  <img src="images/Hackathon5.jpg" width="45%" alt="Hackathon Photo 5" />
</p>

---

## 💬 Final Takeaway

> Motify evolved from a **hackathon idea into a funded MVP**, demonstrating how fast an idea and experimentation can lead to real outcomes. It was a pleasure going on this journey, learning new things on the technical side, but also from a business perspective.

---

# Technical Documentation

## Features

- **Multi-Provider Progress Tracking**: GitHub (commits), Farcaster (casts), WakaTime (coding time)
- **Automated On-Chain Settlement**: EIP-1559 transactions with configurable fee caps
- **OAuth Integration**: Secure token management with wallet signature verification
- **Safety Guards**: Fallback logic, dry-run mode, on-chain reconciliation

## Quick Start

```bash
# 1. Clone and setup
git clone https://github.com/larrycoder123/motify-backend.git
cd motify-backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your credentials

# 4. Run the server
uvicorn app.main:app --reload --port 8000

# 5. Run tests
pytest -q
```

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│  RENDER (FastAPI Server)                                                │
│  - /health, /stats/user, /oauth/*                                      │
│  - /jobs/* (protected by CRON_SECRET)                                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    ▼               ▼               ▼
            ┌───────────┐   ┌───────────┐   ┌───────────┐
            │  Supabase │   │  Base L2  │   │ Provider  │
            │ (Postgres)│   │  (Web3)   │   │   APIs    │
            └───────────┘   └───────────┘   └───────────┘
```

**Background Jobs** run via GitHub Actions (hourly):
1. Index ended challenges from smart contract
2. Fetch progress from OAuth providers
3. Declare results on-chain
4. Archive processed data

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check + DB status |
| GET | `/stats/user?address=0x...` | User statistics |
| GET | `/oauth/providers` | List OAuth providers |
| GET | `/oauth/connect/{provider}` | Start OAuth flow |
| DELETE | `/oauth/disconnect/{provider}/{wallet}` | Remove OAuth |

## Documentation

For detailed technical documentation, see:

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Full system design, data flows, deployment, configuration
- **[docs/schema.sql](docs/schema.sql)** — Database schema
- **[.env.example](.env.example)** — Environment variables reference

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the MIT License.
