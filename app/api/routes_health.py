from fastapi import APIRouter
from app.models.db import SupabaseDAL

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    dal = SupabaseDAL.from_env()
    db_ok = False
    if dal:
        try:
            # lightweight query against a small table
            dal.client.table("users").select("wallet").limit(1).execute()
            db_ok = True
        except Exception:
            db_ok = False
    return {"ok": True, "db": db_ok}
