from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.services.chain_reader import ChainReader

router = APIRouter(prefix="/chain", tags=["chain"])


@router.get("/challenges")
def list_chain_challenges(limit: int = 200):
    if limit <= 0 or limit > 2000:
        raise HTTPException(400, "limit must be between 1 and 2000")
    if not (settings.WEB3_RPC_URL and settings.MOTIFY_CONTRACT_ADDRESS and settings.MOTIFY_CONTRACT_ABI_PATH):
        raise HTTPException(400, "Web3 not configured")
    reader = ChainReader.from_settings()
    if not reader:
        raise HTTPException(500, "Failed to init ChainReader")
    return reader.get_all_challenges(limit=limit)


@router.get("/challenges/{challenge_id}")
def get_chain_challenge_detail(challenge_id: int):
    if challenge_id < 0:
        raise HTTPException(400, "challenge_id must be >= 0")
    if not (settings.WEB3_RPC_URL and settings.MOTIFY_CONTRACT_ADDRESS and settings.MOTIFY_CONTRACT_ABI_PATH):
        raise HTTPException(400, "Web3 not configured")
    reader = ChainReader.from_settings()
    if not reader:
        raise HTTPException(500, "Failed to init ChainReader")
    return reader.get_challenge_detail(challenge_id)
