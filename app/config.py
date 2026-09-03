from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings managed via environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Voice AI Agent Patient Registration API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    PORT: int = 8000
    HOST: str = "0.0.0.0"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "sqlite:///data/patients.db"

    # Vapi Telephony & Agent
    VAPI_API_KEY: Optional[str] = None
    VAPI_ASSISTANT_ID: Optional[str] = None
    VAPI_PHONE_NUMBER: Optional[str] = None

    # Railway Public Domain (used for webhook registration in Vapi)
    RAILWAY_URL: Optional[str] = None

    # LLM Provider
    OPENAI_API_KEY: Optional[str] = None


settings = Settings()
