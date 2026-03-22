from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    TELEGRAM_BOT_TOKEN: str
    VLLM_BASE_URL: str = "http://vllm:8000/v1"


settings = Settings()
