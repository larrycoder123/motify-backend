"""
Application configuration via environment variables.

Uses pydantic-settings to load and validate configuration from .env files.
All sensitive values should be set via environment variables, never committed.
"""

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Settings are grouped by feature area. Optional features gracefully degrade
    when their required environment variables are not configured.
    """

    # =========================================================================
    # General
    # =========================================================================
    ENV: str = Field(default="development")

    # =========================================================================
    # Supabase Database
    # =========================================================================
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None

    # =========================================================================
    # Blockchain (Base L2)
    # =========================================================================
    WEB3_RPC_URL: str | None = None
    MOTIFY_CONTRACT_ADDRESS: str | None = None
    MOTIFY_CONTRACT_ABI_PATH: str | None = "./abi/Motify.json"

    # Server wallet for signing transactions (accepts PRIVATE_KEY or legacy name)
    PRIVATE_KEY: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PRIVATE_KEY", "SERVER_SIGNER_PRIVATE_KEY"),
    )

    # EIP-1559 gas settings (uses auto-estimate if not set)
    MAX_FEE_GWEI: float | None = None
    GAS_LIMIT: int | None = None

    # Token decimals for stake values (default: 6 for USDC)
    STAKE_TOKEN_DECIMALS: int = 6

    # =========================================================================
    # OAuth Configuration
    # =========================================================================
    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET: str | None = None

    # URLs for OAuth redirect flows
    BACKEND_URL: str = Field(default="https://motify-backend-3k55.onrender.com")
    FRONTEND_URL: str = Field(default="https://motify.live")

    # =========================================================================
    # Progress Provider APIs
    # =========================================================================
    NEYNAR_API_KEY: str | None = None
    FARCASTER_USER_CASTS_URL: str | None = None
    WAKATIME_API_BASE_URL: str = "https://api.wakatime.com/api/v1/"

    # =========================================================================
    # Database Column Mapping
    # =========================================================================
    USER_TOKENS_TABLE: str | None = None
    USER_TOKENS_WALLET_COL: str | None = None
    USER_TOKENS_PROVIDER_COL: str | None = None
    USER_TOKENS_ACCESS_TOKEN_COL: str | None = None

    # =========================================================================
    # Security
    # =========================================================================
    CRON_SECRET: str | None = None

    # Default refund percentage (PPM) when progress cannot be fetched
    # 1,000,000 PPM = 100% refund
    DEFAULT_PERCENT_PPM: int = 1_000_000

    # =========================================================================
    # Validators
    # =========================================================================

    @field_validator("MAX_FEE_GWEI", mode="before")
    @classmethod
    def _blank_to_none_float(cls, v):
        """Convert blank string to None for optional float fields."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v

    @field_validator("GAS_LIMIT", mode="before")
    @classmethod
    def _blank_to_none_int(cls, v):
        """Convert blank string to None for optional int fields."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v

    @field_validator("STAKE_TOKEN_DECIMALS", mode="before")
    @classmethod
    def _blank_decimals_default(cls, v):
        """Use default value for blank token decimals."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return 6
        return v

    @field_validator("DEFAULT_PERCENT_PPM", mode="before")
    @classmethod
    def _default_percent_ppm(cls, v):
        """Validate and clamp percent PPM to valid range [0, 1_000_000]."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return 1_000_000
        try:
            iv = int(v)
        except Exception:
            return 1_000_000
        return max(0, min(iv, 1_000_000))

    @field_validator("MOTIFY_CONTRACT_ABI_PATH", mode="before")
    @classmethod
    def _blank_abi_default(cls, v):
        """Use default ABI path for blank values."""
        if v is None or (isinstance(v, str) and not v.strip()):
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
        mode="before",
    )
    @classmethod
    def _blank_to_none_str(cls, v):
        """Convert blank strings to None for optional string fields."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return None
        return v

    # =========================================================================
    # Model Configuration
    # =========================================================================
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
