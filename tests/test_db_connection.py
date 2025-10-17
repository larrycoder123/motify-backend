import os
import pytest
from dotenv import load_dotenv
from pathlib import Path

# Load .env from repo root explicitly so env vars are available at runtime
_ROOT_ENV = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=_ROOT_ENV)


def test_supabase_connection():
    if not (
        os.getenv("SUPABASE_URL")
        and (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY"))
    ):
        pytest.skip("Supabase env not configured")
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_ANON_KEY"]
    client = create_client(url, key)
    # minimal query to confirm connectivity and schema exists
    resp = client.table("users").select("wallet").limit(1).execute()
    # resp may vary by SDK version; ensure no exception and object has data attr or similar
    assert resp is not None