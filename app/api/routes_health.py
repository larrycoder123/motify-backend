from fastapi import APIRouter
from app.models.db import SupabaseDAL

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    dal = SupabaseDAL.from_env()
    db_ok = False
    if dal:
            # Try a few known tables from our schema; stop at the first success
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
