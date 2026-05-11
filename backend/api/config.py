"""Environment-driven configuration via pydantic-settings."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime config comes from env vars. See .env.example."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_host: str = Field(default="localhost")
    db_port: int = Field(default=5432)
    db_user: str = Field(default="proxy")
    db_password: str
    db_name: str = Field(default="proxy")

    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_db: int = Field(default=0)

    proxy_public_url: str = Field(default="http://localhost:9100")
    pairing_code_ttl_seconds: int = Field(default=7200)
    pairing_code_alphabet: str = Field(default="ABCDEFGHJKLMNPQRSTUVWXYZ23456789")
    pairing_code_length: int = Field(default=8)

    log_level: str = Field(default="info")

    # Operator bearer token. If empty, /admin/* refuses every request.
    # Set via env (ADMIN_TOKEN=...) — never commit a value.
    admin_token: str = Field(default="")

    # -- ACME / Let's Encrypt (Phase 2) --
    # If any of these is empty, /admin/boxes/{id}/issue_cert returns 503
    # and certs are not minted. Box can still pair via the existing
    # rendezvous flow; only the per-box LE cert is gated on this.
    cloudflare_dns_api_token: str = Field(default="")
    cert_base_domain: str = Field(default="")  # e.g. box.filamind.app
    acme_email: str = Field(default="")  # contact email for LE account
    acme_storage_path: str = Field(default="/var/lib/proxy/acme")

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    @property
    def database_url_sync(self) -> str:
        """Sync URL for Alembic."""
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
