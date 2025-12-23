"""
Health check endpoint for service monitoring.

Provides basic health status and optional database connectivity check.
"""

from fastapi import APIRouter

from app.models.db import SupabaseDAL

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    """
    Check service health and database connectivity.
    
    Returns:
        ok: Always true if the service is running
        db: True if Supabase is configured and reachable
    """
    dal = SupabaseDAL.from_env()
    db_ok = False
    
    if dal:
        # Probe known tables until one succeeds
        probes = [
            ("user_tokens", "wallet_address"),
            ("chain_challenges", "contract_address"),
            ("finished_challenges", "contract_address"),
        ]
        for table, col in probes:
            try:
                dal.client.table(table).select(col).limit(1).execute()
                db_ok = True
                break
            except Exception:
                continue
    
    return {"ok": True, "db": db_ok}
