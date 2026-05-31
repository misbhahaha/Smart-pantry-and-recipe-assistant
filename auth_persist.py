"""Keep users signed in across browser restarts using a long-lived cookie.

Profile fields (diet, health, favorites, etc.) are stored in the database via the API.
This module only persists the auth token client-side so Streamlit sessions reopen logged-in.
"""

from __future__ import annotations

import datetime as dt
import threading

import streamlit as st
from extra_streamlit_components import CookieManager
from streamlit.runtime.scriptrunner_utils.script_run_context import get_script_run_ctx

COOKIE_NAME = "pantryflow_auth"
_COOKIE_DAYS = 400

# CookieManager embeds a Streamlit custom component; it must not live in ``st.session_state`` (widget-backed
# values can be dropped or cloned across reruns, which recreates ``CookieManager(key=...)`` and duplicates keys).
# One Python object per connected Streamlit session (server process).
_cm_lock = threading.Lock()
_cm_by_session: dict[str, CookieManager] = {}


def _streamlit_session_id() -> str:
    try:
        ctx = get_script_run_ctx()
        if ctx is not None:
            return ctx.session_id
    except Exception:
        pass
    return "_no_session_ctx"


def _cookie_manager() -> CookieManager:
    sid = _streamlit_session_id()
    with _cm_lock:
        cm = _cm_by_session.get(sid)
        if cm is None:
            safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in sid)
            safe = safe[-48:] if len(safe) > 48 else safe
            cm = CookieManager(key=f"pantryflow_cookie_manager_{safe or 'default'}")
            _cm_by_session[sid] = cm
        return cm


def _ensure_token_key() -> None:
    if "token" not in st.session_state:
        st.session_state.token = None


def bootstrap_auth_token() -> None:
    """If session has no token, restore from cookie."""
    _ensure_token_key()
    if st.session_state.token:
        return
    cm = _cookie_manager()
    cm.get_all(key="pf_cookie_get_all")
    raw = cm.get(COOKIE_NAME)
    if raw:
        st.session_state.token = raw


def persist_auth_token(token: str) -> None:
    """Save token to session and browser cookie."""
    _ensure_token_key()
    st.session_state.token = token
    cm = _cookie_manager()
    cm.set(
        COOKIE_NAME,
        token,
        key="pf_cookie_set",
        expires_at=dt.datetime.now() + dt.timedelta(days=_COOKIE_DAYS),
        same_site="lax",
    )


def clear_auth_token() -> None:
    """Sign out: drop session token and cookie."""
    _ensure_token_key()
    st.session_state.token = None
    st.session_state.pop("_pf_backend_ok", None)
    cm = _cookie_manager()
    try:
        cm.delete(COOKIE_NAME, key="pf_cookie_delete")
    except Exception:
        pass
    st.cache_data.clear()
