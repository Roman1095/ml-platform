from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    jwt_secret: str

    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30

    artifact_root: Path = Path("/data/models")

    worker_name: str = "ml-platform-worker-1"
    worker_heartbeat_interval: float = 10.0
    worker_poll_interval: float = 2.0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
