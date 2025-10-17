from fastapi import APIRouter

router = APIRouter(prefix="/leaderboards", tags=["leaderboards"])


@router.get("/{challenge_id}")
async def leaderboard(challenge_id: int, by: str = "stake"):
    return {"challenge_id": challenge_id, "by": by, "items": []}
