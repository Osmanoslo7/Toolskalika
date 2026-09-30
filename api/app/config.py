from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    owner_name: str = "Operator"
    owner_email: str = "owner@example.com"

    rp_id: str = "localhost"
    rp_name: str = "Toolskalika"
    origin: str = "http://localhost:8000"

    toolskalika_secret_key: str = ""
    database_url: str = "sqlite:///./toolskalika.db"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Personal access tokens never expire by default (single-operator tool),
    # but callers can request a shorter-lived one at issue time.
    pat_default_ttl_days: int = 3650


@lru_cache
def get_settings() -> Settings:
    return Settings()
