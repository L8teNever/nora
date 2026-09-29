from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    nora_database_url: str = "sqlite:///./data/nora.sqlite3"
    nora_encryption_key: str = ""
    nora_tz: str = "UTC"
    claude_routine_fire_url: str = ""
    claude_routine_token: str = ""
    anthropic_version: str = "2023-06-01"
    nora_host: str = "0.0.0.0"
    nora_port: int = 8080


@lru_cache
def get_settings() -> Settings:
    return Settings()
