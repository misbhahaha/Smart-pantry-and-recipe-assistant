"""Fetch analyzed step-by-step instructions from Spoonacular (optional API key)."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.core.config import settings

SPOON_BASE = "https://api.spoonacular.com"

# Map app catalog labels to Spoonacular `cuisine` filter values (see their API docs).
_CUISINE_FILTER: dict[str, str] = {
    "Italian": "Italian",
    "Indian": "Indian",
    "Chinese": "Chinese",
    "Middle Eastern": "Middle Eastern",
    "Kashmiri": "Indian",
}


def _pick_search_result(results: list[dict[str, Any]], target_name: str) -> dict[str, Any] | None:
    if not results:
        return None
    tl = re.sub(r"\s+", " ", (target_name or "").strip().lower())
    if not tl:
        return results[0]
    for row in results:
        title = re.sub(r"\s+", " ", str(row.get("title") or "").strip().lower())
        if not title:
            continue
        if tl in title or title in tl:
            return row
    return results[0]


def _names_from_objects(items: Any, *, key: str) -> list[str]:
    out: list[str] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if not isinstance(it, dict):
            continue
        n = str(it.get("localizedName") or it.get(key) or "").strip()
        if n and n not in out:
            out.append(n)
    return out


def _parse_analyzed_instructions(
    analyzed: list[dict[str, Any]] | None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Return (plain step strings, rich steps with ingredients/equipment per step)."""
    plain: list[str] = []
    rich: list[dict[str, Any]] = []
    for sec in analyzed or []:
        if not isinstance(sec, dict):
            continue
        for s in sec.get("steps") or []:
            if not isinstance(s, dict):
                continue
            text = str(s.get("step") or "").strip()
            if not text:
                continue
            try:
                num = int(s.get("number") or 0)
            except (TypeError, ValueError):
                num = 0
            if num <= 0:
                num = len(rich) + 1
            plain.append(text)
            rich.append(
                {
                    "number": num,
                    "instruction": text,
                    "ingredients": _names_from_objects(s.get("ingredients"), key="name"),
                    "equipment": _names_from_objects(s.get("equipment"), key="name"),
                }
            )
    return plain, rich


def spoonacular_dish_image_url(detail: dict[str, Any]) -> str | None:
    """Official recipe image for this Spoonacular id (same dish as steps)."""
    u = str(detail.get("image") or "").strip()
    if u.startswith("http"):
        return u
    return None


def _recipe_information(spoonacular_id: int, *, client: httpx.Client) -> dict[str, Any] | None:
    key = (settings.spoonacular_api_key or "").strip()
    if not key or spoonacular_id <= 0:
        return None
    try:
        r = client.get(
            f"{SPOON_BASE}/recipes/{int(spoonacular_id)}/information",
            params={"apiKey": key, "includeNutrition": "false"},
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def fetch_structured_steps(
    *,
    recipe_name: str,
    cuisine: str,
) -> tuple[list[str] | None, list[dict[str, Any]] | None, int | None, str | None]:
    """
    Search Spoonacular by title, then load analyzed instructions with per-step ingredients/equipment.
    Returns (plain_steps, cooking_guide, spoonacular_recipe_id, dish_image_url) or Nones on miss / error / no API key.
    """
    key = (settings.spoonacular_api_key or "").strip()
    if not key:
        return None, None, None, None
    name = (recipe_name or "").strip()
    if not name:
        return None, None, None, None

    cuisine_key = _CUISINE_FILTER.get((cuisine or "").strip(), "")
    params: dict[str, object] = {
        "apiKey": key,
        "query": name,
        "number": 5,
        "addRecipeInformation": False,
    }
    if cuisine_key:
        params["cuisine"] = cuisine_key

    try:
        with httpx.Client(timeout=20.0) as client:
            r = client.get(
                f"{SPOON_BASE}/recipes/complexSearch",
                params=params,
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            payload = r.json()
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        return None, None, None, None

    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list) or not results:
        return None, None, None, None
    pick = _pick_search_result([x for x in results if isinstance(x, dict)], name)
    if not pick:
        return None, None, None, None
    try:
        sid = int(pick.get("id") or 0)
    except (TypeError, ValueError):
        return None, None, None, None
    if sid <= 0:
        return None, None, None, None

    with httpx.Client(timeout=20.0) as client:
        detail = _recipe_information(sid, client=client)
    if not detail:
        return None, None, None, None
    analyzed = detail.get("analyzedInstructions")
    if not isinstance(analyzed, list):
        return None, None, None, None
    plain, rich = _parse_analyzed_instructions(analyzed)
    if len(plain) < 3:
        return None, None, None, None
    dish_img = spoonacular_dish_image_url(detail)
    return plain[:40], rich[:40], sid, dish_img


def fetch_cooking_guide_by_spoonacular_id(
    spoonacular_id: int,
) -> tuple[list[str] | None, list[dict[str, Any]] | None, str | None]:
    """Reload plain + rich steps + dish image when we already have a Spoonacular recipe id."""
    if spoonacular_id <= 0:
        return None, None, None
    try:
        with httpx.Client(timeout=20.0) as client:
            detail = _recipe_information(spoonacular_id, client=client)
    except (httpx.HTTPError, ValueError, json.JSONDecodeError):
        return None, None, None
    if not detail:
        return None, None, None
    analyzed = detail.get("analyzedInstructions")
    if not isinstance(analyzed, list):
        return None, None, None
    plain, rich = _parse_analyzed_instructions(analyzed)
    if len(plain) < 3:
        return None, None, None
    return plain[:40], rich[:40], spoonacular_dish_image_url(detail)
