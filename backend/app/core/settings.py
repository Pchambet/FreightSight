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
    # Clerk session tokens carry `azp` (the origin that requested them). When set, only these are accepted.
    clerk_authorized_parties: list[str] = []

    # FX rates: Frankfurter (ECB reference rates), no key needed.
    fx_api_url: str = "https://api.frankfurter.dev/v1"

    # Container tracking. The signing secret alone is enough to receive and verify webhooks; the API
    # key is only needed to subscribe or poll, so a deployment can run webhook-only.
    tracking_webhook_secret_terminal49: str | None = None
    terminal49_api_key: str | None = None
    terminal49_base_url: str = "https://api.terminal49.com/v2"
    tracking_webhook_max_age_seconds: int = 900

    # Alert e-mails. Without both of these the application logs its digests instead of sending them.
    resend_api_key: str | None = None
    alerts_from_email: str | None = None
    resend_base_url: str = "https://api.resend.com"

    # Invoice extraction. Without a key, invoices are read by the pattern extractor only.
    extraction_api_key: str | None = None
    extraction_model: str = "claude-opus-5"
    extraction_api_url: str = "https://api.anthropic.com/v1/messages"

    # Document storage. Without a complete S3 configuration, uploads are kept in Postgres.
    documents_s3_bucket: str | None = None
    documents_s3_region: str = "fr-par"
    documents_s3_endpoint: str = "https://s3.fr-par.scw.cloud"
    documents_s3_access_key: str | None = None
    documents_s3_secret_key: str | None = None

    @property
    def s3_documents_enabled(self) -> bool:
        return bool(
            self.documents_s3_bucket and self.documents_s3_access_key and self.documents_s3_secret_key
        )

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def clerk_enabled(self) -> bool:
        return bool(self.clerk_jwks_url and self.clerk_issuer)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # database_url comes from the environment
