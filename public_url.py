"""Canonical browser URL for Smart Pantry (Streamlit).

Set **PUBLIC_APP_URL** once in production (e.g. https://your-app.streamlit.app).
Works in any modern browser; one HTTPS link for Chrome, Safari, Firefox, Edge.
"""

from __future__ import annotations

import os


def get_public_app_url() -> str | None:
    """Return the shareable base URL, or None if not configured."""
    for key in ("PUBLIC_APP_URL", "STREAMLIT_PUBLIC_URL"):
        v = (os.environ.get(key) or "").strip().rstrip("/")
        if v:
            return v
    return None


def is_loopback_public_url(url: str) -> bool:
    """True when PUBLIC_APP_URL is only this machine (not useful to show as a “share this link” banner)."""
    u = url.lower().split("?", 1)[0].rstrip("/")
    return (
        u.startswith("http://127.0.0.1")
        or u.startswith("http://localhost")
        or u.startswith("http://[::1]")
        or u.startswith("https://127.0.0.1")
        or u.startswith("https://localhost")
        or u.startswith("https://[::1]")
    )


def render_browser_access_block(*, compact: bool = False) -> None:
    """Show the official app link for bookmarking / sharing (Streamlit context)."""
    import streamlit as st

    url = get_public_app_url()
    if not url:
        return
    # run_pantryflow.py sets PUBLIC_APP_URL to http://127.0.0.1:8501 for a stable default; on that URL you
    # are already in the browser, so the big card is noise. Still show for real deploy / LAN share links.
    if is_loopback_public_url(url):
        return

    if compact:
        st.caption("Official app link — use in any browser (Chrome, Safari, Firefox, Edge).")
        st.code(url, language=None)
        return

    st.markdown(
        '<div class="pf-card" style="margin-top:0.75rem;">'
        "<strong>Browser access</strong><br/>"
        "One link for all supported browsers. Bookmark or share with your household."
        "</div>",
        unsafe_allow_html=True,
    )
    st.link_button("Open this app in your browser", url, use_container_width=True)
    st.code(url, language=None)
