from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment / `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Env: DATABASE_URL, OPENAI_API_KEY, TELEGRAM_BOT_TOKEN (pydantic-settings naming)
    database_url: str
    openai_api_key: str
    telegram_bot_token: str


@lru_cache
def get_settings() -> Settings:
    return Settings()

