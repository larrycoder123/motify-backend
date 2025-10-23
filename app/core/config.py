from pydantic import Field, AliasChoices, field_validator
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
    # Accept either PRIVATE_KEY or legacy SERVER_SIGNER_PRIVATE_KEY from env
    PRIVATE_KEY: str | None = Field(default=None, validation_alias=AliasChoices(
        "PRIVATE_KEY", "SERVER_SIGNER_PRIVATE_KEY"))
    # EIP-1559 fee controls (preferred). If set, will use these values instead of auto-estimate.
    MAX_FEE_GWEI: float | None = None
    GAS_LIMIT: int | None = None
    # Toke n decimals for stake values (e.g., USDC=6)
    STAKE_TOKEN_DECIMALS: int = 6
    # Progress token lookup (optional, for provider API calls)
    USER_TOKENS_TABLE: str | None = None
    USER_TOKENS_WALLET_COL: str | None = None  # e.g., "wallet_address"
    USER_TOKENS_PROVIDER_COL: str | None = None  # e.g., "provider" or "api_type"
    USER_TOKENS_ACCESS_TOKEN_COL: str | None = None  # e.g., "access_token"
    # Optional: secret to protect job endpoints (used by Vercel Cron)
    CRON_SECRET: str | None = None
    # OAuth providers
    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET: str | None = None
    BACKEND_URL: str = Field(default="https://motify-backend-3k55.onrender.com")
    FRONTEND_URL: str = Field(default="https://motify.live")
    # Default fallback percent (in PPM) when progress cannot be fetched
    # 1_000_000 PPM = 100%
    DEFAULT_PERCENT_PPM: int = 1_000_000
    # Farcaster/Neynar API
    NEYNAR_API_KEY: str | None = None
    # (Removed) Farcaster IdRegistry on Optimism settings
    # Optional override for Neynar "casts by user" endpoint URL
    FARCASTER_USER_CASTS_URL: str | None = None
    # Wakatime
    WAKATIME_API_BASE_URL: str = "https://api.wakatime.com/api/v1/" # Default base URL

    # --- Validators to handle blank env values from CI ---
    @field_validator("MAX_FEE_GWEI", mode="before")
    def _blank_to_none_float(cls, v):  # noqa: N805
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("GAS_LIMIT", mode="before")
    def _blank_to_none_int(cls, v):  # noqa: N805
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("STAKE_TOKEN_DECIMALS", mode="before")
    def _blank_decimals_default(cls, v):  # noqa: N805
        if v is None:
            return 6
        if isinstance(v, str) and not v.strip():
            return 6
        return v

    @field_validator("DEFAULT_PERCENT_PPM", mode="before")
    def _default_percent_ppm(cls, v):  # noqa: N805
        # Accept blank as default 1_000_000
        if v is None:
            return 1_000_000
        if isinstance(v, str) and not v.strip():
            return 1_000_000
        # Coerce to int and clamp to [0, 1_000_000]
        try:
            iv = int(v)
        except Exception:
            iv = 1_000_000
        if iv < 0:
            iv = 0
        if iv > 1_000_000:
            iv = 1_000_000
        return iv

    @field_validator("MOTIFY_CONTRACT_ABI_PATH", mode="before")
    def _blank_abi_default(cls, v):  # noqa: N805
        if v is None:
            return "./abi/Motify.json"
        if isinstance(v, str) and not v.strip():
            return "./abi/Motify.json"
        return v

    @field_validator(
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "WEB3_RPC_URL",
        "MOTIFY_CONTRACT_ADDRESS",
        "PRIVATE_KEY",
        "USER_TOKENS_TABLE",
        "USER_TOKENS_WALLET_COL",
        "USER_TOKENS_PROVIDER_COL",
        "USER_TOKENS_ACCESS_TOKEN_COL",
        "CRON_SECRET",
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
        "NEYNAR_API_KEY",
        "FARCASTER_USER_CASTS_URL",
        # BACKEND_URL is left out intentionally to allow default when blank
        mode="before",
    )
    def _blank_to_none_str(cls, v):  # noqa: N805
        if v is None:
            return None
        if isinstance(v, str) and not v.strip():
            return None
        return v

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
