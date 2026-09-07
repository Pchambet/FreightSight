"""12-factor configuration. Nothing secret has a default: the app refuses to boot without it."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["dev", "test", "preview", "prod"] = "dev"
    database_url: str = Field(description="postgresql+psycopg://user:pass@host:5432/db")
    cors_origins: list[str] = ["http://localhost:3000"]
    default_base_currency: str = "EUR"

    # Clerk (Phase 1 auth). When unset outside prod, the X-Org-Id dev header is accepted instead.
    clerk_jwks_url: str | None = None
    clerk_issuer: str | None = None
    clerk_audience: str | None = None

    # FX rates: Frankfurter (ECB reference rates), no key needed.
    fx_api_url: str = "https://api.frankfurter.app"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def clerk_enabled(self) -> bool:
        return bool(self.clerk_jwks_url and self.clerk_issuer)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # database_url comes from the environment
