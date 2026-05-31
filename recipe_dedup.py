"""Canonical recipe title keys for feed deduplication (mirrors backend recipe_dedup)."""

from __future__ import annotations

import re

_TOKEN_ALIASES = {
    "ghanoush": "ganoush",
    "ghannouj": "ganoush",
    "fettucine": "fettuccine",
    "houmous": "hummus",
    "hommus": "hummus",
    "humus": "hummus",
}


def _norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def canonical_recipe_key(name: str, cuisine: str = "") -> str:
    n = _norm(name)
    n = re.sub(r"\bma\s+po\b", "mapo", n)
    n = re.sub(r"\balla\b", "", n)
    tokens = [_TOKEN_ALIASES.get(t, t) for t in n.split() if t]
    n = re.sub(r"\s+", " ", " ".join(tokens)).strip()
    cu = (cuisine or "").strip().lower()
    return f"{cu}::{n}" if cu else n


def dedupe_feed_items(items: list[dict]) -> list[dict]:
    seen_keys: set[str] = set()
    seen_ids: set[int] = set()
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        try:
            rid = int(it.get("recipe_id", 0) or 0)
        except (TypeError, ValueError):
            rid = 0
        name = str(it.get("name") or "").strip()
        cuisine = str(it.get("cuisine") or "").strip()
        ckey = canonical_recipe_key(name, cuisine)
        if not ckey or ckey in seen_keys:
            continue
        if rid > 0 and rid in seen_ids:
            continue
        seen_keys.add(ckey)
        if rid > 0:
            seen_ids.add(rid)
        out.append(it)
    return out
