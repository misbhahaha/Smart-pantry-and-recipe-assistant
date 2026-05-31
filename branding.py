"""App icon and branding paths (Streamlit frontend)."""

from __future__ import annotations

from pathlib import Path

_STREAMLIT_APP_DIR = Path(__file__).resolve().parent.parent
APP_ICON_FILE = _STREAMLIT_APP_DIR / "assets" / "app_icon.png"

APP_DISPLAY_NAME = "Smart Pantry"
APP_TAGLINE = "Your personal kitchen companion"


def app_icon_path() -> Path | None:
    if APP_ICON_FILE.is_file():
        return APP_ICON_FILE
    return None


def page_icon_argument() -> str | None:
    """Optional app icon path for ``st.set_page_config(page_icon=...)`` (no emoji fallback)."""
    p = app_icon_path()
    return str(p) if p else None
