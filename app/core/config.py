from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str = Field(default="development")
    # n8n
    N8N_WEBHOOK_SECRET: str = Field(default="dev-secret")
    # Supabase
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    DATABASE_URL: str | None = None
    # Fees
    PLATFORM_FEE_BPS_FAIL: int = 1000
    REWARD_BPS_OF_FEE: int = 500
    # Web3
    WEB3_RPC_URL: str | None = None
    MOTIFY_CONTRACT_ADDRESS: str | None = None
    MOTIFY_CONTRACT_ABI_PATH: str | None = None
    SERVER_SIGNER_PRIVATE_KEY: str | None = None

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
