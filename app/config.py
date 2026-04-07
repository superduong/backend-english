from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Thư mục chứa requirements.txt / Dockerfile (luôn đúng dù cwd khác)
BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _default_sqlite_url() -> str:
    return f"sqlite:///{(BACKEND_ROOT / 'dev.db').resolve()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "English MVP API"
    database_url: str = Field(default_factory=_default_sqlite_url)
    secret_key: str = "dev-secret-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    mock_payments: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("database_url", mode="after")
    @classmethod
    def expand_sqlite_relative(cls, v: str) -> str:
        # Cho phép .env: DATABASE_URL=sqlite:///./dev.db — luôn trỏ vào backend/
        if v.startswith("sqlite:///./"):
            tail = v.removeprefix("sqlite:///./")
            return f"sqlite:///{(BACKEND_ROOT / tail).resolve()}"
        return v


settings = Settings()
