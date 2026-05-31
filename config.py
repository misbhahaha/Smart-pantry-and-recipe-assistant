"""Application settings (env-driven)."""

from __future__ import annotations

import os
from pathlib import Path

# backend/app/core/config.py → repo root is parents[3]
REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

_default_sqlite = f"sqlite:///{DATA_DIR / 'pantry.db'}"


def _default_cors_origins() -> str:
    """Streamlit dev ports (8501–8515) on localhost."""
    pairs = []
    for port in range(8501, 8516):
        pairs.append(f"http://localhost:{port}")
        pairs.append(f"http://127.0.0.1:{port}")
    return ",".join(pairs)


def dev_cors_origin_regex() -> str | None:
    """Optional RFC1918 + localhost (any port) for LAN browsers (e.g. phone → http://192.168.x.x:8501).

    Enable with SMART_PANTRY_DEV_CORS_REGEX=1 (or true/yes). Do not set in production.
    """
    v = os.environ.get("SMART_PANTRY_DEV_CORS_REGEX", "").strip().lower()
    if v not in ("1", "true", "yes"):
        return None
    return (
        r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3}|"
        r"10\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
        r"172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(:\d+)?$"
    )


class Settings:
    secret_key: str = os.environ.get("PANTRY_SECRET", "dev-change-me-in-production")
    database_url: str = os.environ.get("DATABASE_URL", _default_sqlite)
    openai_api_key: str = os.environ.get("OPENAI_API_KEY", "")
    openai_model: str = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    spoonacular_api_key: str = os.environ.get("SPOONACULAR_API_KEY", "")
    cors_origins: list[str] = os.environ.get("CORS_ORIGINS", _default_cors_origins()).split(",")
    # Long default so users stay signed in until they sign out (cookie holds the token).
    # Override with ACCESS_TOKEN_MAX_AGE if you need shorter-lived tokens.
    access_token_max_age_seconds: int = int(
        os.environ.get("ACCESS_TOKEN_MAX_AGE", str(400 * 24 * 3600))
    )


settings = Settings()
