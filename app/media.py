"""Public media URL helpers.

Images are stored on disk as files under upload_dir and recorded in the DB as
relative paths (/uploads/<file>). Locally the Next.js app typically rewrites
/uploads/* to the API, so relative URLs work. After the API is hosted on
Railway, the web app and API are on different hosts — a browser that uses
src="/uploads/..." requests the *frontend* origin and the image 404s.

These helpers keep relative paths in the database and expand them to an
absolute public URL (https://<railway-domain>/uploads/...) on the way out.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from typing import Any
from urllib.parse import urlparse

from app.config import settings

_request_base_url: ContextVar[str] = ContextVar("request_base_url", default="")


def set_request_base_url(url: str):
    return _request_base_url.set((url or "").rstrip("/"))


def reset_request_base_url(token) -> None:
    _request_base_url.reset(token)


def public_base_url() -> str:
    configured = (settings.public_base_url or "").strip().rstrip("/")
    if configured:
        return configured

    railway = (
        os.environ.get("RAILWAY_PUBLIC_DOMAIN")
        or os.environ.get("RAILWAY_STATIC_URL")
        or ""
    ).strip()
    if railway:
        railway = railway.replace("https://", "").replace("http://", "").split("/")[0]
        if railway:
            return f"https://{railway}"

    return _request_base_url.get("").rstrip("/")


def normalize_stored_media_url(url: str) -> str:
    """Persist portable relative /uploads/... paths, stripping any host."""
    if not url:
        return url
    if url.startswith("data:") or url.startswith("blob:"):
        return url
    if url.startswith("/uploads/"):
        return url
    if url.startswith("uploads/"):
        return "/" + url
    try:
        parsed = urlparse(url)
        path = parsed.path or ""
        if path.startswith("/uploads/"):
            return path
        if path.startswith("uploads/"):
            return "/" + path
    except Exception:
        pass
    return url


def public_media_url(url: str) -> str:
    """Expand a stored /uploads/... path into a URL the browser can load."""
    if not url:
        return url
    if url.startswith("data:") or url.startswith("blob:"):
        return url
    relative = normalize_stored_media_url(url)
    if relative.startswith("/uploads/"):
        base = public_base_url()
        if base:
            return f"{base}{relative}"
    return url


def expand_media_urls(value: Any) -> Any:
    """Recursively expand /uploads/... strings in API response payloads."""
    if isinstance(value, str):
        if "/uploads/" in value or value.startswith("uploads/"):
            return public_media_url(value)
        return value
    if isinstance(value, list):
        return [expand_media_urls(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_media_urls(item) for key, item in value.items()}
    return value
