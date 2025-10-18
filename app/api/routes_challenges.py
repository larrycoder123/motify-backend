from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from app.models.db import SupabaseDAL
from app.core.config import settings

router = APIRouter(prefix="/challenges", tags=["challenges"])


class ChallengeCreate(BaseModel):
    # FE shape (snake_case keys)
    name: str
    description: str
    start_at: str = Field(alias="start_date")
    end_at: str = Field(alias="end_date")
    contract_address: str
    goal: str
    owner_wallet: Optional[str] = None
    service_type: Optional[str] = None
    is_charity: Optional[bool] = False
    activity_type: Optional[str] = None
    charity_wallet: Optional[str] = None
    api_provider: Optional[str] = None
    description_hash: Optional[str] = None
    on_chain_challenge_id: Optional[int] = None


class JoinPayload(BaseModel):
    user_wallet: str
    # Primary (USDC or other ERC20): token smallest unit amount (e.g., USDC 6 decimals)
    amount_minor_units: Optional[str] = None
    # Back-compat: accept legacy ETH naming; if provided and primary is missing, we use this value
    amount_wei: Optional[str] = None


@router.get("/")
async def list_challenges():
    dal = SupabaseDAL.from_env()
    if not dal:
        return []
    try:
        resp = dal.client.table("challenges").select("*").order("id", desc=True).limit(50).execute()
        return getattr(resp, "data", [])
    except Exception as e:
        raise HTTPException(500, detail={"error": {"code": "INTERNAL", "message": "DB error", "details": {"type": type(e).__name__}}})


@router.get("/{challenge_id}")
async def get_challenge(challenge_id: int):
    dal = SupabaseDAL.from_env()
    if not dal:
        raise HTTPException(503, detail={"error": {"code": "SERVICE_UNAVAILABLE", "message": "DB not configured", "details": {}}})
    try:
        resp = dal.client.table("challenges").select("*").eq("id", challenge_id).limit(1).execute()
        rows = getattr(resp, "data", [])
        if not rows:
            raise HTTPException(404, detail={"error": {"code": "NOT_FOUND", "message": "challenge not found", "details": {"id": challenge_id}}})
        return rows[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail={"error": {"code": "INTERNAL", "message": "DB error", "details": {"type": type(e).__name__}}})


@router.post("/")
async def create_challenge(payload: ChallengeCreate):
    if not payload.name:
        raise HTTPException(400, detail={"error": {"code": "VALIDATION_FAILED", "message": "name required", "details": {}}})
    dal = SupabaseDAL.from_env()
    if not dal:
        # fallback stub when DB isn't configured
        model = payload.model_dump(by_alias=True)
        return {"id": 1, **model, "completed": False, "status": "pending"}
    try:
        model = payload.model_dump(by_alias=True)
        # No hashing for now (contract/frontend not live). If client provides description_hash, store it, else leave null.
        desc_hash = model.get("description_hash")

        # Map fields to DB shape
        db_row = {
            "name": model["name"],
            "description": model["description"],
            "description_hash": desc_hash,
            "contract_address": model["contract_address"],
            "goal": model["goal"],
            "owner_wallet": model.get("owner_wallet"),
            "service_type": model.get("service_type"),
            "activity_type": model.get("activity_type"),
            "api_provider": model.get("api_provider"),
            "is_charity": bool(model.get("is_charity", False)),
            "charity_wallet": model.get("charity_wallet"),
            "start_at": model["start_date"],
            "end_at": model["end_date"],
            "on_chain_challenge_id": model.get("on_chain_challenge_id"),
            "status": "pending",
            "completed": False,
        }
        table = dal.client.table("challenges")
        # If the client provides on_chain_challenge_id, use upsert to make this idempotent across retries
        if db_row.get("on_chain_challenge_id") is not None:
            insert_resp = table.upsert(db_row, on_conflict="contract_address,on_chain_challenge_id").execute()
        else:
            insert_resp = table.insert(db_row).execute()
        data = getattr(insert_resp, "data", [])
        if not data:
            raise HTTPException(500, detail={"error": {"code": "INTERNAL", "message": "No data returned from insert", "details": {}}})
        return data[0]
    except Exception as e:
        raise HTTPException(
            500,
            detail={
                "error": {
                    "code": "INTERNAL",
                    "message": "DB insert failed",
                    "details": {"type": type(e).__name__, "message": str(e)},
                }
            },
        )


@router.post("/{challenge_id}/join")
async def join_challenge(challenge_id: int, payload: JoinPayload):
    if int(challenge_id) < 1:
        raise HTTPException(404, detail={"error": {"code": "NOT_FOUND", "message": "challenge not found", "details": {"id": challenge_id}}})
    dal = SupabaseDAL.from_env()
    if not dal:
        # Fallback echo without DB
        amt = payload.amount_minor_units or payload.amount_wei
        return {"challenge_id": challenge_id, "user_wallet": payload.user_wallet, "amount_minor_units": amt}
    try:
        # ensure user exists (idempotent upsert into users)
        dal.client.table("users").upsert({"wallet": payload.user_wallet}).execute()
        amt = payload.amount_minor_units or payload.amount_wei
        if amt is None:
            raise HTTPException(400, detail={"error": {"code": "VALIDATION_FAILED", "message": "amount required", "details": {}}})
        stake_payload = {
            "challenge_id": challenge_id,
            "user_wallet": payload.user_wallet,
            "amount_minor_units": amt,
        }
        insert_resp = dal.client.table("stakes").upsert(stake_payload, on_conflict="challenge_id,user_wallet").execute()
        data = getattr(insert_resp, "data", [])
        return data[0] if data else stake_payload
    except Exception as e:
        raise HTTPException(500, detail={"error": {"code": "INTERNAL", "message": "DB upsert failed", "details": {"type": type(e).__name__}}})
