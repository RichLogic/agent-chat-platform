"""Centralized configuration via pydantic-settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AC_")

    # Server
    host: str = "0.0.0.0"
    port: int = 8301
    cors_origins: list[str] = ["http://localhost:8300"]

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "agent_chat"

    # File Storage
    data_dir: str = "data"
    max_upload_size_mb: int = 50

    # LLM
    llm_provider: str = "poe"  # "poe" | "kimi"
    poe_api_key: str = ""
    poe_model: str = "Gemini-3-Flash"
    poe_base_url: str = "https://api.poe.com/v1"
    kimi_api_key: str = ""
    kimi_model: str = "kimi-k2.5"
    kimi_base_url: str = "https://kimi-k2.ai/api/v1"

    # Search (SerpAPI primary, Brave fallback)
    serpapi_key: str = ""
    brave_search_key: str = ""

    # NewsAPI
    newsapi_key: str = ""

    # GitHub OAuth
    github_client_id: str = ""
    github_client_secret: str = ""

    # JWT
    jwt_secret: str = ""
    jwt_expiry_minutes: int = 60 * 24 * 7  # 7 days

    # Frontend
    frontend_url: str = "http://localhost:8300"

    # Logging
    log_level: str = "INFO"


# Module-level settings singleton (avoids circular imports with main.py)
_settings: Settings | None = None


def set_settings(s: Settings) -> None:
    global _settings
    _settings = s


def get_settings() -> Settings:
    if _settings is None:
        raise RuntimeError("Settings not initialized")
    return _settings
