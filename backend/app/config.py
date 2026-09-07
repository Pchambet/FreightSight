"""12-factor configuration. No defaults for anything secret: the app refuses to boot without them."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["dev", "test", "preview", "prod"] = "dev"
    database_url: str = Field(description="postgresql+psycopg://user:pass@host:5432/db")
    cors_origins: list[str] = ["http://localhost:3000"]
    default_base_currency: str = "EUR"

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


def get_settings() -> Settings:
    return Settings()  # database_url comes from the environment
