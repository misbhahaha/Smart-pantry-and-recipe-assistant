"""Shared UI styling and layout helpers for Smart Pantry."""

from __future__ import annotations

import streamlit as st
from lib.api_client import PantryAPI

CUSTOM_CSS = """
html, body, [class*="css"]  {
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
    color: #1e293b;
}

.stApp {
    background: #f1f5f9 !important;
}

.block-container {
    padding-top: 1.75rem !important;
    padding-bottom: 3rem !important;
    max-width: 1120px !important;
}

.pf-hero {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.35rem 1.5rem;
    margin-bottom: 1.35rem;
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
}
.pf-hero h1 {
    color: #0f172a !important;
    font-weight: 700 !important;
    font-size: 1.65rem !important;
    margin: 0 0 0.4rem 0 !important;
    letter-spacing: -0.02em;
}
.pf-hero p {
    color: #475569;
    margin: 0;
    font-size: 0.95rem;
    line-height: 1.45;
}

.pf-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.1rem 1.25rem;
    margin: 0.65rem 0;
    box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.pf-alert-expired {
    border-left: 4px solid #dc2626;
    background: #fef2f2;
    padding: 0.75rem 1rem;
    border-radius: 0 10px 10px 0;
    margin: 0.4rem 0;
}
.pf-alert-warn {
    border-left: 4px solid #d97706;
    background: #fffbeb;
    padding: 0.75rem 1rem;
    border-radius: 0 10px 10px 0;
    margin: 0.4rem 0;
}
.pf-alert-info {
    border-left: 4px solid #0d9488;
    background: #f0fdfa;
    padding: 0.75rem 1rem;
    border-radius: 0 10px 10px 0;
    margin: 0.4rem 0;
}

.stButton > button {
    border-radius: 8px !important;
    border: 1px solid #0f766e !important;
    font-weight: 600 !important;
    background: #0d9488 !important;
    color: #ffffff !important;
    padding: 0.45rem 1.15rem !important;
    box-shadow: none !important;
    transition: background 0.15s ease, border-color 0.15s ease;
}
.stButton > button:hover {
    background: #0f766e !important;
    border-color: #115e59 !important;
    color: #ffffff !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 6px;
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 6px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    font-weight: 600;
}

.stTextInput input, .stNumberInput input, .stSelectbox [data-baseweb="select"] {
    border-radius: 8px !important;
    border-color: #cbd5e1 !important;
}

[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #e2e8f0 !important;
}

[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
    border: 1px solid #e2e8f0;
}

.streamlit-expanderHeader {
    font-weight: 600;
    color: #0f172a;
}
"""


def inject_pastel_theme():
    from lib.auth_persist import bootstrap_auth_token
    from lib.connectivity import maybe_show_backend_unavailable_banner

    bootstrap_auth_token()
    maybe_show_backend_unavailable_banner()
    if st.session_state.get("_pf_theme_injected"):
        return
    st.markdown(f"<style>{CUSTOM_CSS}</style>", unsafe_allow_html=True)
    st.session_state["_pf_theme_injected"] = True


def hero(title: str, subtitle: str = ""):
    sub = f"<p>{subtitle}</p>" if (subtitle and subtitle.strip()) else ""
    st.markdown(
        f'<div class="pf-hero"><h1>{title}</h1>{sub}</div>',
        unsafe_allow_html=True,
    )


def notification_panel(api) -> None:
    """Expiry alerts with dismiss actions."""
    token = getattr(api, "token", None)
    base = getattr(api, "base", None)
    if not token or not base:
        return
    try:
        count, notes = _cached_notifications(base, token)
    except Exception:
        return
    n = count.get("count", 0) if isinstance(count, dict) else 0
    if not notes and n == 0:
        return
    st.markdown("### Expiry alerts")
    st.caption("We check your pantry in the background and surface items that need attention.")
    cols = st.columns([1, 1, 1])
    with cols[0]:
        st.metric("Active alerts", n)
    with cols[1]:
        if st.button("Dismiss all", key="dismiss_all_nf", use_container_width=True):
            api.expiry_dismiss_all()
            st.cache_data.clear()
            st.rerun()
    for note in notes[:12]:
        css = "pf-alert-expired" if note.get("severity") == "expired" else (
            "pf-alert-warn" if note.get("severity") == "warning" else "pf-alert-info"
        )
        c1, c2 = st.columns([5, 1])
        with c1:
            st.markdown(
                f'<div class="{css}"><strong>{note.get("severity", "").title()}</strong> · {note.get("message", "")}</div>',
                unsafe_allow_html=True,
            )
        with c2:
            if st.button("Dismiss", key=f"dn_{note['id']}"):
                api.expiry_dismiss(note["id"])
                st.cache_data.clear()
                st.rerun()


@st.cache_data(ttl=120, show_spinner=False)
def _cached_notifications(base_url: str, token: str) -> tuple[dict, list[dict]]:
    api = PantryAPI(base_url=base_url, token=token)
    return api.expiry_notification_count(), api.expiry_notifications()


def sidebar_nav(current: str):
    """Single branded sidebar: logo + app name once, then page links (see ``showSidebarNavigation`` in config)."""
    with st.sidebar:
        from lib.branding import APP_DISPLAY_NAME, APP_TAGLINE, app_icon_path

        _icon = app_icon_path()
        if _icon is not None:
            try:
                st.image(str(_icon), width=72)
            except Exception:
                pass
        st.markdown(
            f'<p style="margin:0.35rem 0 0.15rem 0;font-size:1.25rem;font-weight:700;color:#0f172a;'
            f'letter-spacing:-0.02em;">{APP_DISPLAY_NAME}</p>',
            unsafe_allow_html=True,
        )
        st.caption(APP_TAGLINE)
        st.markdown("---")
        pages = [
            ("Home", "Home.py"),
            ("Dashboard", "pages/01_Dashboard.py"),
            ("Ingredients", "pages/02_Pantry.py"),
            ("Recipes", "pages/03_Recipes_AI.py"),
            ("Shopping", "pages/04_Shopping.py"),
            ("Profile", "pages/05_Profile_Shop.py"),
        ]
        for label, path in pages:
            if label == current:
                st.markdown(f"**{label}**")
            else:
                st.page_link(path, label=label)
