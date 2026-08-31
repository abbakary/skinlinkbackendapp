import os
from pathlib import Path
from pydantic_settings import BaseSettings

_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _ROOT / ".env"


def _default_upload_dir() -> str:
    """Prefer a Railway persistent volume at /data when present."""
    if Path("/data").is_dir():
        return "/data/uploads"
    return str(_ROOT / "uploads")


class Settings(BaseSettings):
    app_name: str = "SkinLink API"
    secret_key: str = "skinlink-dev-secret-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    database_url: str = "sqlite:///./data/skinlink.db"
    upload_dir: str = _default_upload_dir()
    # Public origin of this API, e.g. https://skinlink-api.up.railway.app
    # Used so case images are returned as absolute URLs the web app can load.
    public_base_url: str = ""
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

# If UPLOAD_DIR was left as a relative path, pin it to the project (or /data).
if not os.path.isabs(settings.upload_dir):
    if Path("/data").is_dir():
        settings.upload_dir = "/data/uploads"
    else:
        settings.upload_dir = str(_ROOT / settings.upload_dir)

# Honour Railway's public domain when PUBLIC_BASE_URL is not set explicitly.
if not (settings.public_base_url or "").strip():
    railway_domain = (
        os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        or os.environ.get("RAILWAY_STATIC_URL")
        or ""
    ).strip()
    if railway_domain:
        railway_domain = (
            railway_domain.replace("https://", "").replace("http://", "").split("/")[0]
        )
        settings.public_base_url = f"https://{railway_domain}"

os.makedirs(settings.upload_dir, exist_ok=True)
