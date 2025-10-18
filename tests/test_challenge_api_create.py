import os
import uuid
from pathlib import Path
import json

import pytest
import requests
from dotenv import load_dotenv


_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=_ROOT / ".env")


@pytest.mark.integration
def test_api_create_challenge_persists(test_api_base_url):
    if not (os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY")):
        pytest.skip("Supabase service role env not configured")

    # Allow overriding base URL via env for CI
    base = os.getenv("API_BASE_URL", test_api_base_url)
    url = f"{base}/challenges/"

    # Load base payload from shared file to avoid duplication
    payload_path = _ROOT / "payloads" / "create_challenge.json"
    with open(payload_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    # Make minimal adjustments to ensure uniqueness and a short window
    suffix = uuid.uuid4().hex[:6]
    payload["name"] = f"API flow {suffix}"
    payload["goal"] = "5"

    resp = requests.post(url, json=payload, timeout=10)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data.get("id") is not None and data.get("name", "").startswith("API flow ")

    # Verify persisted via Supabase
    from supabase import create_client
    s_url = os.environ["SUPABASE_URL"]
    s_key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(s_url, s_key)

    sel = (
        client.table("challenges")
        .select("id,name,status,completed")
        .eq("id", data["id"])  # id returned by API should match DB id
        .execute()
    )
    rows = getattr(sel, "data", [])
    assert rows and rows[0]["status"] == "pending" and rows[0]["completed"] is False
