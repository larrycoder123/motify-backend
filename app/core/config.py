from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENV: str = Field(default="development")
    # Supabase (optional; health will report db connectivity if configured)
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    # Web3 indexer (optional)
    WEB3_RPC_URL: str | None = None
    MOTIFY_CONTRACT_ADDRESS: str | None = None
    MOTIFY_CONTRACT_ABI_PATH: str | None = "./abi/Motify.json"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
