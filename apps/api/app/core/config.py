"""Application configuration, loaded from environment / .env.

Kept intentionally small in Phase 0. VAT domain constants live here too so they can
be overridden without code changes if UAE law changes (e.g. a rate change).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_env: str = "development"
    app_name: str = "UAE VAT Compliance Platform"
    secret_key: str = "change-me"
    api_cors_origins: str = "http://localhost:3000"

    # Data
    database_url: str = "sqlite:///./data/vat.sqlite3"
    storage_backend: str = "local"
    local_storage_dir: str = "./storage"
    redis_url: str = "redis://localhost:6379/0"

    # AI
    ai_provider: str = "none"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    ai_model: str = "claude-sonnet-5"

    # Auth
    auth_enabled: bool = True
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 720  # 12h
    admin_email: str = "admin@vat.local"
    admin_password: str = "ChangeMe!123"  # bootstrap only; change on first login

    # VAT domain constants (current UAE law defaults)
    vat_standard_rate: float = 0.05
    vat_mandatory_reg_threshold_aed: float = 375_000
    vat_voluntary_reg_threshold_aed: float = 187_500
    vat_simplified_invoice_max_aed: float = 10_000

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
