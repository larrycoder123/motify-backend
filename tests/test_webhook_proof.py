import hmac
import hashlib
import json
import os
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=_ROOT / ".env")


def _sign(secret: str, raw: bytes) -> str:
    return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()


@pytest.mark.integration
def test_webhook_proof_ingest(test_api_base_url):
    base = os.getenv("API_BASE_URL", test_api_base_url)

    # Create a challenge first to have an id
    with open(_ROOT / "payloads" / "create_challenge.json", "r", encoding="utf-8") as f:
        payload = json.load(f)
    payload["name"] = "Webhook Test"
    resp = requests.post(f"{base}/challenges/", json=payload, timeout=10)
    assert resp.status_code == 200, resp.text
    challenge = resp.json()
    cid = challenge["id"]

    secret = os.getenv("N8N_WEBHOOK_SECRET", "dev-secret")

    proof_body = {
        "provider": "github",
        "metric": "activity_minutes",
        "user_wallet": "0xAaA0000000000000000000000000000000000001",
        "value": 42,
        "day_key": "2025-10-16",
        "window_start": "2025-10-16T00:00:00Z",
        "window_end": "2025-10-16T23:59:59Z",
        "source_payload_json": {"demo": True},
        "idempotency_key": "proof:test:0xaaa...:2025-10-16",
    }
    raw = json.dumps(proof_body).encode()
    sig = _sign(secret, raw)
    headers = {
        "X-N8N-Signature": sig,
        "X-N8N-Timestamp": str(int(__import__("time").time())),
        "Content-Type": "application/json",
    }

    r = requests.post(f"{base}/webhooks/proofs/{cid}", data=raw, headers=headers, timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "accepted"
    # stored is True only when service role key is configured in env
    expected_stored = bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY"))
    assert data.get("stored") == expected_stored
