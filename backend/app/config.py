"""Runtime settings loaded from environment variables.

Every value is resolved via `pydantic-settings` so the same code runs in unit
tests (with a `.env` or explicit overrides) and in Cloud Run (where the
environment is populated by `--set-env-vars` / `--set-secrets`).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

AppEnv = Literal["production", "dev", "test"]


class Settings(BaseSettings):
    """Strongly-typed runtime configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: AppEnv = Field(default="production")
    log_level: str = Field(default="INFO")

    agent_id: str = Field(default="example-expert")
    schema_path: str | Path = Field(default=Path("/app/schema/agent_schema.yaml"))

    gemini_api_key: SecretStr = Field(default=SecretStr(""))
    admin_key: SecretStr = Field(default=SecretStr(""))

    gcp_project: str = Field(default="")
    docs_bucket: str = Field(default="")
    backups_bucket: str = Field(default="")

    mempalace_chroma_host: str = Field(default="localhost")
    mempalace_chroma_port: int = Field(default=8000)
    mempalace_chroma_ssl: bool = Field(default=False)
    mempalace_chroma_collection: str = Field(default="")

    allow_cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    @property
    def chroma_collection_name(self) -> str:
        """Default collection name is namespaced by `agent_id` when not set."""
        return self.mempalace_chroma_collection or f"agent_{self.agent_id}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings factory; safe to call from FastAPI dependencies."""
    return Settings()


__all__ = ["AppEnv", "Settings", "get_settings"]
