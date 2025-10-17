import os
import pytest
from dotenv import load_dotenv

# Load .env so SUPABASE_* values are available during test collection
load_dotenv()


@pytest.mark.skipif(
    not (os.getenv("SUPABASE_URL") and (os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY"))),
    reason="Supabase env not configured",
)
def test_supabase_connection():
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.environ["SUPABASE_ANON_KEY"]
    client = create_client(url, key)
    # minimal query to confirm connectivity and schema exists
    resp = client.table("users").select("wallet").limit(1).execute()
    # resp may vary by SDK version; ensure no exception and object has data attr or similar
    assert resp is not None