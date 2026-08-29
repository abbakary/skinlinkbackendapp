from pathlib import Path
from pydantic_settings import BaseSettings

_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    app_name: str = "SkinLink API"
    secret_key: str = "skinlink-dev-secret-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    database_url: str = "sqlite:///./data/skinlink.db"
    upload_dir: str = "uploads"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://10.0.2.2:8000",
    ]

    platform_admin_email: str = "ops@skinlink.io"
    platform_admin_password: str = "platform123"

    # AI API configuration
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.7-flash"
    gemini_temperature: float = 0.2

    class Config:
        env_file = str(_ENV_FILE)
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
