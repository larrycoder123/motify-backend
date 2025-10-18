import os
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv


_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=_ROOT / ".env")


@pytest.mark.integration
def test_insert_challenge_new_schema():
    if not (os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY")):
        pytest.skip("Supabase service role env not configured")

    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    client = create_client(url, key)

    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"FE-flow test {suffix}",
        "description": "Test challenge created by integration test.",
        "description_hash": None,  # backend may compute later; DB allows null
        "contract_address": "0x2222222222222222222222222222222222222222",
        "goal": "42",
        "service_type": "github",
        "activity_type": "COMMITS",
        "api_provider": "github",
        "is_charity": False,
        "charity_wallet": None,
        "start_at": "2025-10-20T00:00:00Z",
        "end_at": "2025-10-21T00:00:00Z",
        "status": "pending",
        "completed": False,
    }

    ins = client.table("challenges").insert(payload).execute()
    data = getattr(ins, "data", [])
    assert data and data[0]["name"].startswith("FE-flow test")
    row_id = data[0]["id"]

    sel = client.table("challenges").select("id,name,contract_address,goal,status,completed").eq("id", row_id).execute()
    rd = getattr(sel, "data", [])
    assert rd and rd[0]["status"] == "pending" and rd[0]["completed"] is False
