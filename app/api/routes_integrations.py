from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/integrations", tags=["integrations"])


class StartResp(BaseModel):
    auth_url: str


@router.get("/{provider}/start", response_model=StartResp)
async def start_integration(provider: str, wallet: str):
    # Stub: return placeholder URL
    return StartResp(auth_url=f"https://auth.example/{provider}?wallet={wallet}")


@router.post("/{provider}/callback")
async def integration_callback(provider: str):
    # Stub: store tokens later
    return {"provider": provider, "linked": True}


#@router.get("")
#async def list_integrations(wallet: str):
    #return {"wallet": wallet, "providers": []}


@router.delete("/{provider}")
async def unlink_integration(provider: str, wallet: str):
    return {"wallet": wallet, "provider": provider, "unlinked": True}
