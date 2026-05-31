"""Recipe photos for feed and detail views — trusted URLs, caching, fast feed sizing."""

from __future__ import annotations

import concurrent.futures
from typing import Iterable

import httpx
import streamlit as st

_TRUSTED = (
    "themealdb.com",
    "img.spoonacular.com",
    "spoonacular.com/cdn",
    "upload.wikimedia.org",
)


def trusted_dish_image_url(url: str | None) -> str | None:
    u = (url or "").strip()
    if not u.lower().startswith("https://"):
        return None
    low = u.lower()
    if "images.unsplash.com" in low:
        return None
    if any(host in low for host in _TRUSTED):
        return u
    return None


def feed_image_url(url: str | None) -> str | None:
    """URL suitable for home-feed tiles (trusted dish photos only)."""
    return trusted_dish_image_url(url)


NO_DISH_IMAGE_MESSAGE = "No image available for this dish."


def render_dish_image_or_unavailable(
    url: str | None,
    *,
    dish_name: str = "",
    use_container_width: bool = True,
    caption: str | None = None,
) -> bool:
    """Show the dish photo when trusted; otherwise a clear unavailable message. Returns True if shown."""
    photo = trusted_dish_image_url(url)
    if photo:
        st.image(photo, use_container_width=use_container_width, caption=caption or dish_name or None)
        return True
    label = (dish_name or "This dish").strip()
    st.markdown(
        f'<div class="pf-insta-ph" style="padding:1.1rem;text-align:center;color:#64748b;">'
        f"<strong>{label}</strong><br/>"
        f'<span style="font-size:0.85rem;">{NO_DISH_IMAGE_MESSAGE}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )
    return False


@st.cache_data(ttl=3600, show_spinner=False)
def prefetch_feed_images(urls: tuple[str, ...]) -> dict[str, bytes]:
    """Download feed images once; Streamlit reruns reuse bytes (faster than remote st.image)."""
    unique = tuple(dict.fromkeys(u for u in urls if u))
    if not unique:
        return {}

    def _fetch(client: httpx.Client, url: str) -> tuple[str, bytes | None]:
        try:
            r = client.get(
                url,
                timeout=12.0,
                headers={"User-Agent": "SmartPantry/1.0 (recipe feed)"},
            )
            if r.status_code == 200 and r.content:
                return url, r.content
        except Exception:
            pass
        return url, None

    out: dict[str, bytes] = {}
    with httpx.Client(follow_redirects=True) as client:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(_fetch, client, u) for u in unique]
            for fut in concurrent.futures.as_completed(futures):
                url, data = fut.result()
                if data:
                    out[url] = data
    return out


def prefetch_urls_from_items(items: Iterable[dict]) -> dict[str, bytes]:
    urls: list[str] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        u = feed_image_url(str(it.get("image_url") or ""))
        if u:
            urls.append(u)
    return prefetch_feed_images(tuple(urls))
