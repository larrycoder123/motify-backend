from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.models.db import SupabaseDAL
from app.services.chain_handlers import handle_challenge_created_event


router = APIRouter(prefix="/chain", tags=["chain"], include_in_schema=True)


class ChallengeCreatedSim(BaseModel):
    contract_address: str
    on_chain_challenge_id: int
    db_challenge_id: Optional[int] = None
    owner_wallet: Optional[str] = None
    description_hash: Optional[str] = None
    created_tx_hash: Optional[str] = None
    created_block_number: Optional[int] = None


@router.post("/challenges/created")
async def simulate_challenge_created(payload: ChallengeCreatedSim):
    """Dev-only simulate endpoint: attach an on-chain id to a pending challenge and mark it active.
    Matching priority:
      1) db_challenge_id if provided
      2) latest pending with same contract_address and (optional) description_hash
    """
    dal = SupabaseDAL.from_env()
    if not dal:
        raise HTTPException(503, detail={"error": {"code": "SERVICE_UNAVAILABLE", "message": "DB not configured", "details": {}}})

    try:
        updated = handle_challenge_created_event(
            dal,
            contract_address=payload.contract_address,
            on_chain_challenge_id=payload.on_chain_challenge_id,
            db_challenge_id=payload.db_challenge_id,
            owner_wallet=payload.owner_wallet,
            description_hash=payload.description_hash,
            created_tx_hash=payload.created_tx_hash,
            created_block_number=payload.created_block_number,
        )
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, detail={
            "error": {"code": "INTERNAL", "message": "Chain simulate failed", "details": {"type": type(e).__name__, "message": str(e)}}
        })
