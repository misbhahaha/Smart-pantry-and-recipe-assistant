"""Detect whether the Smart Pantry API is reachable (Streamlit UI)."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx
import streamlit as st

from lib.api_client import DEFAULT_BASE

LAUNCH_HINT = (
    "From the project folder run **`python run_pantryflow.py`** — it starts the API and this web app together."
)

CLOUD_DEPLOY_HINT = (
    "**Streamlit Cloud + Render:** open **`BACKEND_URL/health`** in a browser. You should see "
    '`{"status":"ok"}`. If the page hangs or errors, fix the **Render** service first '
    "(Dashboard → Logs: build must use `requirements-render.txt`, start "
    "`cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT`). "
    "Free tier can take **~60s** to wake after sleep — refresh and wait.\n\n"
    "On Render set **`PANTRY_SECRET`** and **`CORS_ORIGINS`** to your exact "
    "`https://….streamlit.app` URL. Match **`PANTRY_SECRET`** in Streamlit secrets, then **Reboot app**."
)


def _is_local_backend(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def _health_urls_to_try() -> list[str]:
    """Probe configured API URL; only fall back to localhost when BACKEND_URL is local."""
    base = DEFAULT_BASE.rstrip("/")
    if not _is_local_backend(base):
        return [base]
    seen: set[str] = set()
    out: list[str] = []
    for u in (
        base,
        f"http://127.0.0.1:{os.environ.get('API_PORT', '8000').strip() or '8000'}",
        "http://localhost:8000",
    ):
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _probe_timeout(base: str, *, quick: bool) -> float:
    """Fast /live probe on cloud; slightly longer only when waking a cold Render instance."""
    if _is_local_backend(base):
        return 3.0
    return 8.0 if quick else 20.0


@st.cache_data(ttl=60, show_spinner=False)
def _backend_health_probe() -> tuple[bool, str]:
    """Return (ok, detail) where detail names the first working base or explains failure."""
    last_err = "no response"
    for base in _health_urls_to_try():
        try:
            live = httpx.get(f"{base}/live", timeout=_probe_timeout(base, quick=True))
            if live.status_code == 404:
                return False, f"{base} returned 404 — wrong URL or deleted Render service; update BACKEND_URL"
        except httpx.RequestError as e:
            last_err = str(e)[:160]
            continue
        try:
            r = httpx.get(f"{base}/health", timeout=_probe_timeout(base, quick=False))
            if r.status_code == 200:
                return True, base
            if r.status_code == 503:
                return False, f"{base} is running but database check failed (503)"
            if live.status_code == 200:
                return True, base
        except httpx.RequestError as e:
            last_err = str(e)[:160]
            if live.status_code == 200:
                return True, base
        except Exception as e:
            last_err = str(e)[:160]
    return False, last_err


def maybe_show_backend_unavailable_banner() -> None:
    # Signed-in pages already talk to the API; skip the probe on every navigation.
    if st.session_state.get("token"):
        return
    if st.session_state.get("_pf_backend_ok"):
        return
    ok, detail = _backend_health_probe()
    if ok:
        st.session_state["_pf_backend_ok"] = True
    if ok:
        if detail.rstrip("/") != DEFAULT_BASE.rstrip("/"):
            st.warning(
                f"The API is running at **`{detail}`**, but this app is configured with "
                f"**`BACKEND_URL={DEFAULT_BASE}`** (unreachable). Sign-in and data calls will fail until they match.\n\n"
                f"**Fix:** stop Streamlit, then start again with e.g. `BACKEND_URL={detail} python run_pantryflow.py` "
                f"or unset `BACKEND_URL` to use the default `http://127.0.0.1:8000`.\n\n"
                + LAUNCH_HINT
            )
        return
    tried = ", ".join(_health_urls_to_try())
    remote = not _is_local_backend(DEFAULT_BASE.rstrip("/"))
    extra = CLOUD_DEPLOY_HINT if remote else (
        LAUNCH_HINT
        + "\n\n**If the web page itself would not load:** use **http://127.0.0.1:8501** on the same computer, "
        "or **http://YOUR-WIFI-IP:8501** from a phone (same Wi‑Fi). Restart after changing network."
    )
    st.warning(
        "The Smart Pantry **API** is not reachable from this app, so sign-in and data views will not work until it is running.\n\n"
        f"Configured **`BACKEND_URL`**: `{DEFAULT_BASE}`\n\n"
        f"Tried: {tried} — last error: `{detail}`\n\n"
        + extra
    )
