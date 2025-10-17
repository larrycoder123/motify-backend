from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/challenges", tags=["challenges"])


class ChallengeCreate(BaseModel):
    title: str
    start_at: str
    end_at: str
    target_metric: str
    target_value: int
    charity_wallet: Optional[str] = None
    is_private: bool = False
    proof_policy: Optional[dict] = None


class JoinPayload(BaseModel):
    user_wallet: str
    amount_wei: str


@router.get("/")
async def list_challenges():
    return []


@router.post("/")
async def create_challenge(payload: ChallengeCreate):
    if not payload.title:
        raise HTTPException(400, detail={"error": {"code": "VALIDATION_FAILED", "message": "title required", "details": {}}})
    return {"id": 1, **payload.model_dump()}


@router.post("/{challenge_id}/join")
async def join_challenge(challenge_id: int, payload: JoinPayload):
    if int(challenge_id) < 1:
        raise HTTPException(404, detail={"error": {"code": "NOT_FOUND", "message": "challenge not found", "details": {"id": challenge_id}}})
    return {"challenge_id": challenge_id, "user_wallet": payload.user_wallet, "amount_wei": payload.amount_wei}
