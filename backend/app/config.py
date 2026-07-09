from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "ProductShot AI Backend"
    environment: str = "local"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = "sqlite:///./storage/app.db"
    storage_dir: str = "./storage"
    public_base_url: str = "http://localhost:8000"
    max_upload_mb: int = 20
    auth_secret: str = "change-me-in-production-productshot-auth-secret"
    auth_token_expire_hours: int = 168

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def storage_path(self) -> Path:
        path = Path(self.storage_dir)
        path.mkdir(parents=True, exist_ok=True)
        (path / "uploads").mkdir(parents=True, exist_ok=True)
        (path / "outputs").mkdir(parents=True, exist_ok=True)
        return path

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
