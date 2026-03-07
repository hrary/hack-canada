from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """App-wide configuration pulled from environment / .env."""

    # LLM / Blackboard
    openai_api_key: str = ""
    blackboard_api_key: str = ""

    # CORS – origins that may call the API
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
