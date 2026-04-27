"""Configuration via environment variables and .env file."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Loads from environment + .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="SINAPZE_",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM
    anthropic_api_key: str = Field(..., alias="ANTHROPIC_API_KEY")
    llm_model: str = "claude-sonnet-4-6"
    llm_temperature: float = 0.3
    llm_max_tokens: int = 8192

    # Storage
    data_dir: Path = Path(".sinapze")

    # Behavior
    default_language: Literal["auto", "pt-BR", "en"] = "auto"
    verify_cards: bool = True
    chunk_size_chars: int = 4000  # ~1000 tokens, fits semantic units
    chunk_overlap_chars: int = 400


def get_settings() -> Settings:
    """Lazy-load settings so import doesn't require an API key."""
    return Settings()  # type: ignore[call-arg]
