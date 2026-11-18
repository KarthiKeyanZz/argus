"""Application settings, loaded from environment variables and ``argus/.env``.

Every variable is prefixed with ``ARGUS_`` (e.g. ``ARGUS_DATABASE_URL``).
Secrets are typed as ``SecretStr`` so they never appear in reprs or logs.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# app/core/config.py -> parents: core(0) app(1) backend(2) argus(3)
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARGUS_",
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- runtime -----------------------------------------------------------------
    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    # --- HTTP API ----------------------------------------------------------------
    api_host: str = "127.0.0.1"
    api_port: int = Field(8000, ge=1, le=65535)
    allowed_hosts: list[str] = Field(default_factory=lambda: ["127.0.0.1", "localhost"])
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # --- database ----------------------------------------------------------------
    database_url: SecretStr
    db_pool_idle: int = Field(4, ge=0, description="Idle connections kept open for reuse.")
    db_pool_max: int = Field(10, ge=1, le=100, description="Hard cap on open connections.")
    db_pool_acquire_timeout_s: float = Field(10.0, gt=0)
    db_statement_timeout_ms: int = Field(15_000, ge=100)

    # --- storage -----------------------------------------------------------------
    data_dir: Path = Path.home() / ".local" / "share" / "argus"

    # --- local LLM (Ollama) ------------------------------------------------------
    ollama_base_url: str = "http://127.0.0.1:11434"
    llm_chat_model: str = "gemma4:26b-a4b-it-qat"
    llm_embed_model: str = "nomic-embed-text"
    llm_request_timeout_s: float = Field(600.0, gt=0)
    llm_default_num_ctx: int = Field(8192, ge=512)
    llm_keep_alive: str = "15m"
    llm_max_input_chars: int = Field(24_000, ge=1_000)

    # --- worker ------------------------------------------------------------------
    worker_idle_wait_s: float = Field(30.0, gt=0, description="Max wait for a NOTIFY.")
    worker_stale_task_after_s: int = Field(1800, ge=60)

    @property
    def self_origins(self) -> list[str]:
        """Origins under which the API itself (e.g. Swagger UI) is served."""
        return [f"http://{host}:{self.api_port}" for host in self.allowed_hosts]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # database_url comes from the environment / .env
