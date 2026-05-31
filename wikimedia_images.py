"""Wikimedia Commons food photos when TheMealDB has no strict title match."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.services.recipe_image_match import (
    is_acceptable_match,
    name_similarity,
    search_queries_for_recipe,
    significant_tokens,
)

_API = "https://commons.wikimedia.org/w/api.php"
_FILE_RE = re.compile(r"^File:", re.I)


def _get(params: dict[str, str]) -> dict[str, Any] | None:
    q = "&".join(f"{k}={quote(v)}" for k, v in params.items())
    url = f"{_API}?{q}&format=json"
    try:
        req = Request(url, headers={"User-Agent": "SmartPantry/1.0 (recipe images; educational)"})
        with urlopen(req, timeout=18) as resp:
            return json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _title_from_file_name(file_name: str) -> str:
    base = file_name
    if base.lower().startswith("file:"):
        base = base[5:]
    base = re.sub(r"\.[a-z0-9]+$", "", base, flags=re.I)
    base = base.replace("_", " ")
    return base.strip()


def wikimedia_thumb_for_recipe(recipe_name: str, cuisine: str | None = None) -> str | None:
    """Return a direct image URL when Commons has a close title match."""
    name = (recipe_name or "").strip()
    if len(name) < 2:
        return None
    queries = list(search_queries_for_recipe(name, cuisine))
    if name not in queries:
        queries.insert(0, name)
    best_url: str | None = None
    best_score = 0.0
    seen: set[str] = set()
    for q in queries:
        if q in seen:
            continue
        seen.add(q)
        data = _get(
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": q,
                "gsrnamespace": "6",
                "gsrlimit": "8",
                "prop": "imageinfo",
                "iiprop": "url",
                "iiurlwidth": "900",
            }
        )
        if not data:
            continue
        pages = (data.get("query") or {}).get("pages") or {}
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            title = str(page.get("title") or "")
            if not _FILE_RE.match(title):
                continue
            label = _title_from_file_name(title)
            info = page.get("imageinfo") or []
            if not info or not isinstance(info[0], dict):
                continue
            url = str(info[0].get("thumburl") or info[0].get("url") or "").strip()
            if not url.startswith("https://"):
                continue
            score = name_similarity(name, label)
            nn, nl = name.lower(), label.lower()
            title_prefix = nl.startswith(nn) or nl.startswith(f"{nn} ")
            # Skip portraits, documents, and other non-food files.
            if re.search(r"\b(19|20)\d{2}\b", label) or re.search(r"\b(d\.|born|portrait|logo)\b", label, re.I):
                continue
            if not title_prefix and not is_acceptable_match(name, label, min_score=0.72):
                continue
            ta, tb = significant_tokens(name), significant_tokens(label)
            if len(ta) == 1 and not title_prefix:
                continue
            if ta and not title_prefix and not (ta <= tb or len(ta & tb) >= max(1, len(ta) - 1)):
                continue
            if title_prefix:
                score = max(score, 0.9)
            if score > best_score:
                best_score = score
                best_url = url
    return best_url


def wikimedia_loose_for_recipe(recipe_name: str, cuisine: str | None = None) -> str | None:
    """Last resort: image file title must contain the recipe name (or a known alias)."""
    from app.services.recipe_image_match import _INDIAN_ALIASES, _KASHMIRI_ALIASES, norm_recipe_name

    name = (recipe_name or "").strip()
    if len(name) < 2:
        return None
    needles = {norm_recipe_name(name)}
    cu = (cuisine or "").strip()
    if cu == "Kashmiri":
        needles.update(norm_recipe_name(a) for a in _KASHMIRI_ALIASES.get(norm_recipe_name(name), ()))
    if cu == "Indian":
        needles.update(norm_recipe_name(a) for a in _INDIAN_ALIASES.get(norm_recipe_name(name), ()))
    for q in search_queries_for_recipe(name, cuisine):
        needles.add(norm_recipe_name(q))
    for needle in sorted(needles, key=len, reverse=True):
        if len(needle) < 3:
            continue
        data = _get(
            {
                "action": "query",
                "generator": "search",
                "gsrsearch": needle,
                "gsrnamespace": "6",
                "gsrlimit": "6",
                "prop": "imageinfo",
                "iiprop": "url",
                "iiurlwidth": "900",
            }
        )
        if not data:
            continue
        pages = (data.get("query") or {}).get("pages") or {}
        for page in pages.values():
            if not isinstance(page, dict):
                continue
            title = _title_from_file_name(str(page.get("title") or "")).lower()
            if re.search(r"\b(19|20)\d{2}\b", title):
                continue
            if needle not in norm_recipe_name(title):
                continue
            info = page.get("imageinfo") or []
            if not info or not isinstance(info[0], dict):
                continue
            url = str(info[0].get("thumburl") or info[0].get("url") or "").strip()
            if url.startswith("https://"):
                return url
    return None
