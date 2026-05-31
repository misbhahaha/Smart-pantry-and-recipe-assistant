"""Your Personal Kitchen Companion — Streamlit frontend (calls backend API only)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import html
from typing import Optional

import httpx
import streamlit as st
from lib.api_client import DEFAULT_BASE, PantryAPI
from lib.auth_persist import clear_auth_token, persist_auth_token
from lib.branding import APP_DISPLAY_NAME, APP_TAGLINE, app_icon_path
from lib.dish_images import prefetch_urls_from_items, trusted_dish_image_url
from lib.home_infinite_scroll import inject_home_infinite_scroll
from lib.recipe_dedup import canonical_recipe_key, dedupe_feed_items
from lib.ui import inject_pastel_theme, sidebar_nav

HOME_FEED_PAGE_SIZE = 12

_cfg = {"page_title": APP_DISPLAY_NAME, "layout": "wide", "initial_sidebar_state": "expanded"}
_icon = app_icon_path()
if _icon is not None:
    _cfg["page_icon"] = str(_icon)
st.set_page_config(**_cfg)
inject_pastel_theme()

if "token" not in st.session_state:
    st.session_state.token = None


def _friendly_auth_error(err: Exception) -> str:
    if isinstance(err, httpx.TimeoutException):
        return "The request took too long. Check your connection and try again."
    if isinstance(err, httpx.RequestError):
        from urllib.parse import urlparse

        host = (urlparse(DEFAULT_BASE).hostname or "").lower()
        if host not in ("127.0.0.1", "localhost", "::1"):
            return (
                f"Cannot reach the API at `{DEFAULT_BASE}`. "
                "Open that URL with `/health` in a browser — it should return "
                '`{"status":"ok"}`. If not, check the Render service logs and redeploy.'
            )
        return (
            f"Cannot reach the server at `{DEFAULT_BASE}`. "
            "From the project folder run `python3 run_pantryflow.py` (starts the API and this app)."
        )
    if isinstance(err, httpx.HTTPStatusError):
        code = err.response.status_code
        if code == 404:
            return (
                f"The API at `{DEFAULT_BASE}` returned 404 (not found). "
                "Your Render URL may have changed — update **`BACKEND_URL`** in Streamlit secrets "
                "to the new `https://….onrender.com` URL, then reboot the app."
            )
        if code == 401:
            return (
                "Invalid email or password. "
                "A **new Render deployment uses an empty database** — use **Create account** "
                "instead of an old local password."
            )
        detail = ""
        try:
            payload = err.response.json()
            detail = payload.get("detail") if isinstance(payload, dict) else ""
        except Exception:
            detail = err.response.text[:200] if err.response.text else ""
        return str(detail or err)
    return str(err)


def _inject_home_feed_css() -> None:
    if st.session_state.get("_pf_home_feed_css_insta"):
        return
    st.markdown(
        """
        <style>
        .pf-home-brand {
            margin-bottom: 0.35rem;
        }
        .pf-home-brand-row {
            display: flex;
            align-items: center;
            gap: 0.85rem;
            flex-wrap: nowrap;
            min-width: 0;
        }
        .pf-home-brand-copy { min-width: 0; flex: 1 1 auto; }
        .pf-home-brand h2 {
            margin: 0;
            font-size: 1.85rem;
            font-weight: 800;
            color: #0f172a;
            letter-spacing: -0.02em;
            white-space: nowrap;
            line-height: 1.15;
        }
        .pf-home-brand .pf-tagline {
            margin: 0.45rem 0 0 0;
            font-size: 1rem;
            color: #64748b;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            line-height: 1.3;
        }
        .pf-home-feed-section { margin-top: 1.35rem; }
        .pf-feed-heading { margin: 0 0 0.85rem 0; font-size: 1.05rem; font-weight: 400; color: #0f172a; }
        .pf-insta-feed { max-width: 470px; margin: 0 auto; padding: 0 0.15rem; }
        .pf-insta-post {
            background: #fff;
            border: 1px solid #dbdbdb;
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 1.35rem;
            box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
        }
        .pf-insta-post img {
            width: 100%;
            aspect-ratio: 1 / 1;
            object-fit: cover;
            display: block;
            background: #f1f5f9;
        }
        .pf-insta-post-body { padding: 0.75rem 0.9rem 0.85rem; }
        .pf-insta-title { font-weight: 700; font-size: 0.98rem; color: #0f172a; margin: 0 0 0.2rem; }
        .pf-insta-meta { font-size: 0.82rem; color: #64748b; margin: 0; }
        .pf-insta-ph {
            width: 100%;
            aspect-ratio: 1 / 1;
            background: linear-gradient(135deg, #e2e8f0 0%, #f8fafc 55%, #ccfbf1 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            color: #64748b;
            font-size: 0.85rem;
            text-align: center;
            padding: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_pf_home_feed_css_insta"] = True


def _cloud_backend() -> bool:
    from urllib.parse import urlparse

    host = (urlparse(DEFAULT_BASE).hostname or "").lower()
    return host.endswith(".onrender.com")


@st.cache_data(ttl=120, show_spinner=False)
def _home_reco_bundle(token: str) -> tuple[list, list]:
    """Rules-based picks only on cloud (AI/TF-IDF is slow on Render free tier)."""
    api = PantryAPI(token=token)
    ai: list = []
    if not _cloud_backend():
        try:
            ai = api.recommendations_ai(limit=16)
        except Exception:
            ai = []
    try:
        rules = api.recommendations_rules(limit=24)
    except Exception:
        rules = []
    return ai if isinstance(ai, list) else [], rules if isinstance(rules, list) else []


@st.cache_data(ttl=90, show_spinner=False)
def _home_recipe_search(token: str, q: str) -> list[dict]:
    if not (q and str(q).strip()):
        return []
    return PantryAPI(token=token).recipes(search=str(q).strip(), limit=48)


def _dedupe_feed_cards(items: list[dict]) -> list[dict]:
    """One tile per recipe id and per canonical title (e.g. Ganoush vs Ghanoush → one card)."""
    return dedupe_feed_items(items)


def _feed_cards_with_images(items: list[dict]) -> list[dict]:
    """Home feed only shows recipes that have a verified dish photo."""
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        if trusted_dish_image_url(str(it.get("image_url") or "")):
            out.append(it)
    return out


def _feed_cards_from_recommendations(ai: list, rules: list) -> list[dict]:
    seen_id: set[int] = set()
    seen_title: set[str] = set()
    out: list[dict] = []
    for x in ai:
        if not isinstance(x, dict):
            continue
        try:
            rid = int(x.get("recipe_id", 0) or 0)
        except (TypeError, ValueError):
            continue
        cuisine = str(x.get("cuisine") or "")
        ckey = canonical_recipe_key(str(x.get("name") or ""), cuisine)
        if rid <= 0 or rid in seen_id or ckey in seen_title:
            continue
        seen_id.add(rid)
        seen_title.add(ckey)
        ms = float(x.get("ingredient_match_score") or 0)
        out.append(
            {
                "recipe_id": rid,
                "name": str(x.get("name") or "Recipe"),
                "cuisine": cuisine,
                "subtitle": f"{ms:.0%} pantry match",
                "image_url": str(x.get("image_url") or ""),
            }
        )
    for x in rules:
        if not isinstance(x, dict):
            continue
        try:
            rid = int(x.get("recipe_id", 0) or 0)
        except (TypeError, ValueError):
            continue
        cuisine = str(x.get("cuisine") or "")
        ckey = canonical_recipe_key(str(x.get("name") or ""), cuisine)
        if rid <= 0 or rid in seen_id or ckey in seen_title:
            continue
        seen_id.add(rid)
        seen_title.add(ckey)
        ms = float(x.get("ingredient_match_score") or 0)
        out.append(
            {
                "recipe_id": rid,
                "name": str(x.get("name") or "Recipe"),
                "cuisine": cuisine,
                "subtitle": f"{ms:.0%} match",
                "image_url": str(x.get("image_url") or ""),
            }
        )
    return out


def _feed_cards_from_recipe_rows(rows: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    seen_id: set[int] = set()
    for r in rows:
        if not isinstance(r, dict):
            continue
        try:
            rid = int(r.get("id", 0) or 0)
        except (TypeError, ValueError):
            continue
        if rid <= 0 or rid in seen_id:
            continue
        cuisine = str(r.get("cuisine") or "")
        ckey = canonical_recipe_key(str(r.get("name") or ""), cuisine)
        if not ckey or ckey in seen:
            continue
        seen.add(ckey)
        seen_id.add(rid)
        pm = int(r.get("prep_minutes") or 0)
        out.append(
            {
                "recipe_id": rid,
                "name": str(r.get("name") or "Recipe"),
                "cuisine": str(r.get("cuisine") or ""),
                "subtitle": f"{pm} min prep",
                "image_url": str(r.get("image_url") or ""),
            }
        )
    return out


def _merge_catalog_into_feed(primary: list[dict], catalog_rows: list[dict]) -> list[dict]:
    """Recommendations first, then remaining catalog recipes that have photos."""
    out = list(primary)
    seen_ids = {int(x["recipe_id"]) for x in out}
    seen_keys = {canonical_recipe_key(str(x.get("name") or ""), str(x.get("cuisine") or "")) for x in out}
    for card in _feed_cards_from_recipe_rows(catalog_rows):
        rid = int(card["recipe_id"])
        ckey = canonical_recipe_key(str(card.get("name") or ""), str(card.get("cuisine") or ""))
        if rid in seen_ids or ckey in seen_keys:
            continue
        if not trusted_dish_image_url(str(card.get("image_url") or "")):
            continue
        seen_ids.add(rid)
        seen_keys.add(ckey)
        out.append(card)
    return out


@st.cache_data(ttl=180, show_spinner=False)
def _home_feed_pool(token: str) -> list[dict]:
    """Full home feed: personalized picks first, then catalog recipes with verified photos."""
    api = PantryAPI(token=token)
    ai, rules = _home_reco_bundle(token)
    head = _feed_cards_with_images(_dedupe_feed_cards(_feed_cards_from_recommendations(ai, rules)))
    try:
        catalog = api.recipes(limit=120)
    except Exception:
        catalog = []
    return _merge_catalog_into_feed(head, catalog if isinstance(catalog, list) else [])


def _render_recipe_feed_grid(
    items: list[dict],
    *,
    key_prefix: str,
    require_image: bool = True,
    empty_message: Optional[str] = None,
) -> None:
    if not items:
        st.info(
            empty_message
            or "Nothing here yet. Open **Recipes** from the sidebar or add pantry items for picks."
        )
        return
    image_cache = prefetch_urls_from_items(items)
    st.markdown('<div class="pf-insta-feed">', unsafe_allow_html=True)
    shown = 0
    for i, it in enumerate(items):
        name = html.escape(str(it.get("name") or "Recipe"))
        cuisine = html.escape(str(it.get("cuisine") or ""))
        subtitle = html.escape(str(it.get("subtitle") or ""))
        photo_url = trusted_dish_image_url(str(it.get("image_url") or ""))
        if not photo_url and require_image:
            continue
        shown += 1
        st.markdown('<article class="pf-insta-post">', unsafe_allow_html=True)
        if photo_url and photo_url in image_cache:
            st.image(image_cache[photo_url], width="stretch")
        elif photo_url:
            st.markdown(
                f'<img src="{html.escape(photo_url)}" alt="{name}" loading="lazy" />',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="pf-insta-ph" style="padding:2.5rem 1rem;text-align:center;'
                f'background:#f8fafc;color:#64748b;min-height:120px;">'
                f"<strong>{name}</strong><br/>"
                f'<span style="font-size:0.85rem;">No photo — open recipe for details</span>'
                f"</div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            f'<div class="pf-insta-post-body">'
            f'<p class="pf-insta-title">{name}</p>'
            f'<p class="pf-insta-meta">{cuisine} · {subtitle}</p>'
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button(
            "View recipe",
            key=f"{key_prefix}_vw_{it['recipe_id']}_{i}",
            use_container_width=True,
        ):
            st.session_state["open_recipe_id"] = int(it["recipe_id"])
            st.switch_page("pages/03_Recipes_AI.py")
        st.markdown("</article>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    if require_image and shown == 0 and items:
        st.info(
            empty_message
            or "Matches were found but none have a verified photo yet. Try **Recipes** in the sidebar for the full list."
        )


if st.session_state.token:
    sidebar_nav("Home")

if st.session_state.token is None:
    _, center, _ = st.columns([1, 2.1, 1])
    with center:
        _icon = app_icon_path()
        if _icon is not None:
            st.image(str(_icon), width=120, use_container_width=False)
        st.markdown(f"# {APP_DISPLAY_NAME}")
        st.caption(APP_TAGLINE)
        st.markdown(
            '<div class="pf-card" style="text-align:center;">'
            "Sign in or create an account to manage ingredients, track calories, expiry alerts, "
            "and recommendations tailored to you."
            "</div>",
            unsafe_allow_html=True,
        )
        tab1, tab2 = st.tabs(["Sign in", "Create account"])
        with tab1:
            with st.form("login"):
                em = st.text_input("Email")
                pw = st.text_input("Password", type="password")
                if st.form_submit_button("Sign in", use_container_width=True):
                    if not em.strip() or not pw:
                        st.error("Email and password are required.")
                    else:
                        try:
                            with st.spinner("Signing in…"):
                                tok = PantryAPI().login(em.strip(), pw)
                            persist_auth_token(tok)
                            st.success("Welcome back!")
                            st.rerun()
                        except httpx.RequestError as e:
                            st.warning(_friendly_auth_error(e))
                        except Exception as e:
                            st.error(f"Could not sign in: {_friendly_auth_error(e)}")
        with tab2:
            with st.form("reg"):
                name = st.text_input("Full name")
                em = st.text_input("Email", key="r_em")
                pw = st.text_input("Password", type="password", key="r_pw")
                joint_plan = st.checkbox("Join a joint family plan", value=False)
                code = ""
                if joint_plan:
                    code = st.text_input("Invite code", help="Ask the household owner for their invite code.")
                if st.form_submit_button("Create account", use_container_width=True):
                    if not name.strip():
                        st.error("Full name is required.")
                    elif not em.strip():
                        st.error("Email is required.")
                    elif len(pw) < 8:
                        st.error("Password must be at least 8 characters.")
                    elif joint_plan and not code.strip():
                        st.error("Invite code is required for a joint family plan.")
                    else:
                        try:
                            with st.spinner("Creating your account…"):
                                tok = PantryAPI().register(
                                    em.strip(),
                                    pw,
                                    name.strip(),
                                    household_name=None,
                                    join_code=code.strip().upper(),
                                )
                            persist_auth_token(tok)
                            st.success("Account ready — explore the sidebar.")
                            st.rerun()
                        except httpx.RequestError as e:
                            st.warning(_friendly_auth_error(e))
                        except Exception as e:
                            st.error(f"Registration failed: {_friendly_auth_error(e)}")
else:
    try:
        api = PantryAPI(token=st.session_state.token)
        api.me()
    except httpx.RequestError:
        st.info("The server is unreachable. When it is back, use **Reload** in the Streamlit menu or press **R**.")
        st.stop()
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (401, 403):
            clear_auth_token()
            st.rerun()
        st.error(str(e))
        st.stop()
    except Exception as e:
        st.error(f"Could not verify session: {e}")
        st.stop()

    _inject_home_feed_css()

    c_brand, c_search = st.columns([1.7, 1.7], gap="medium")
    with c_brand:
        logo_col, text_col = st.columns([0.24, 0.76], gap="small")
        with logo_col:
            hi = app_icon_path()
            if hi is not None:
                st.image(str(hi), width=96)
        with text_col:
            st.markdown(
                f'<div class="pf-home-brand">'
                f'<div class="pf-home-brand-copy">'
                f"<h2>{html.escape(APP_DISPLAY_NAME)}</h2>"
                f'<p class="pf-tagline">{html.escape(APP_TAGLINE)}</p>'
                f"</div></div>",
                unsafe_allow_html=True,
            )
    with c_search:
        st.text_input(
            "Search recipes",
            label_visibility="collapsed",
            placeholder="Search recipes by name (e.g. curry, pasta, soup)…",
            key="home_feed_search",
        )

    tok = st.session_state.token
    q = (st.session_state.get("home_feed_search") or "").strip()

    if len(q) >= 2:
        st.markdown(
            f'<div class="pf-home-feed-section">'
            f'<p class="pf-feed-heading">Search results · “{html.escape(q)}”</p>'
            f"</div>",
            unsafe_allow_html=True,
        )
        try:
            hits = _home_recipe_search(tok, q)
            search_items = _dedupe_feed_cards(_feed_cards_from_recipe_rows(hits))
            _render_recipe_feed_grid(
                search_items,
                key_prefix="hf_srch",
                require_image=False,
                empty_message=f'No recipes found matching “{html.escape(q)}”. Try another name or open **Recipes** in the sidebar.',
            )
        except Exception as e:
            st.error(f"Search failed: {e}")
        st.divider()
    elif len(q) == 1:
        st.caption("Type at least 2 characters to search recipes by name.")

    if st.session_state.get("home_feed_pool_token") != tok:
        st.session_state.home_feed_pool_token = tok
        st.session_state.home_feed_visible = HOME_FEED_PAGE_SIZE

    if "home_feed_visible" not in st.session_state:
        st.session_state.home_feed_visible = HOME_FEED_PAGE_SIZE

    with st.status("Loading recipes…", expanded=False):
        pool = _home_feed_pool(tok)
    visible_n = min(int(st.session_state.home_feed_visible), len(pool))
    rec_items = pool[:visible_n]

    if len(q) < 2:
        st.markdown(
            '<div class="pf-home-feed-section">'
            '<p class="pf-feed-heading">Recommended recipes</p>'
            "</div>",
            unsafe_allow_html=True,
        )
        _render_recipe_feed_grid(rec_items, key_prefix="hf_rec")

        if visible_n < len(pool):
            st.markdown('<div id="home-feed-sentinel"></div>', unsafe_allow_html=True)
            if st.button("Load more recipes", key="home_feed_load_more", use_container_width=True):
                st.session_state.home_feed_visible = min(
                    len(pool),
                    int(st.session_state.home_feed_visible) + HOME_FEED_PAGE_SIZE,
                )
                st.rerun()
            inject_home_infinite_scroll()
        elif pool:
            st.caption("You have reached the end of the feed.")
