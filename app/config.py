from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_decisions_url: str = "https://openrouter.ai/api/alpha/decisions"
    jev_model: str = "typesafe/jev-1.13"
    openrouter_chat_model: str = "typesafe/jev-router"
    openrouter_http_referer: str = "http://localhost:8000"
    openrouter_app_title: str = "ChronoGuard"
    openrouter_timeout_seconds: float = 45.0
    openrouter_max_retries: int = 2

    jev_confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    jev_malicious_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    max_retries: int = Field(default=3, ge=0, le=10)

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: SecretStr = SecretStr("chronoguard")

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "chronoguard_knowledge"

    embedding_provider: Literal["hashing", "openai_compatible"] = "hashing"
    embedding_dim: int = 384
    openai_compat_base_url: str = ""
    openai_compat_api_key: SecretStr = SecretStr("")
    openai_compat_embedding_model: str = "text-embedding-3-small"

    log_level: str = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    demo_incident_time: str = "2026-09-27T02:14:00Z"


@lru_cache
def get_settings() -> Settings:
    return Settings()
