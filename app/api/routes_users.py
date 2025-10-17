from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/users", tags=["users"])


class UserCreate(BaseModel):
    wallet: str


@router.post("/")
async def create_user(payload: UserCreate):
    # Stub: in future store in Supabase
    if not payload.wallet:
        raise HTTPException(status_code=400, detail={
            "error": {"code": "VALIDATION_FAILED", "message": "wallet required", "details": {}}
        })
    return {"wallet": payload.wallet}


@router.get("/{wallet}/stats")
async def get_user_stats(wallet: str):
    # Stub response; replace with aggregation from DB later
    return {
        "wallet": wallet,
        "challenges_joined": 0,
        "challenges_completed": 0,
        "total_staked_wei": "0",
        "total_refunded_wei": "0",
        "total_donated_wei": "0",
        "last_active_at": None,
    }
