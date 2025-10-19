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
    # Chain writer (declare results)
    PRIVATE_KEY: str | None = None
    GAS_PRICE_GWEI: float | None = None
    GAS_LIMIT: int | None = None
    # Progress token lookup (optional, for provider API calls)
    USER_TOKENS_TABLE: str | None = None
    USER_TOKENS_WALLET_COL: str | None = None  # e.g., "wallet_address"
    USER_TOKENS_PROVIDER_COL: str | None = None  # e.g., "provider" or "api_type"
    USER_TOKENS_ACCESS_TOKEN_COL: str | None = None  # e.g., "access_token"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
