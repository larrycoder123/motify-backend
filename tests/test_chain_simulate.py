import json
import os
import random
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=_ROOT / ".env")


@pytest.mark.integration
def test_chain_simulate_challenge_created(test_api_base_url):
    base = os.getenv("API_BASE_URL", test_api_base_url)

    # Create a pending challenge first
    with open(_ROOT / "payloads" / "create_challenge.json", "r", encoding="utf-8") as f:
        payload = json.load(f)
    payload["name"] = "Chain Sim Pending"
    r = requests.post(f"{base}/challenges/", json=payload, timeout=10)
    assert r.status_code == 200, r.text
    chal = r.json()
    assert chal.get("status") == "pending"

    # Simulate the on-chain event attaching the id and activating
    ocid = random.randint(10_000, 1_000_000)
    sim = {
        "contract_address": chal["contract_address"],
        "on_chain_challenge_id": ocid,
        "db_challenge_id": chal["id"],
    }
    sr = requests.post(f"{base}/chain/challenges/created", json=sim, timeout=10)
    assert sr.status_code == 200, sr.text
    updated = sr.json()
    assert updated.get("on_chain_challenge_id") == ocid
    assert updated.get("status") == "active"
