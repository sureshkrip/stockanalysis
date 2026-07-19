"""Typed application configuration — the single source of truth for env vars.

No module in this codebase should read os.environ directly; everything goes
through get_settings().
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:////data/app.db"
    # Default is a placeholder only — production/CI must set EDGAR_USER_AGENT to a
    # real "<AppName> <contact-email>" string (see .env.example / RESEARCH.md Pitfall 3).
    # Defaulted (not required) so schema-only operations like `alembic upgrade head`
    # don't need it set.
    edgar_user_agent: str = "DataCenterStocks unset@example.com"
    backend_url: str = "http://backend:8000"


@lru_cache
def get_settings() -> Settings:
    return Settings()
