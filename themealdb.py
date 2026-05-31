"""TheMealDB public API — recipes by cuisine / area (free, no key)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

from app.services.instruction_steps import (
    format_steps_as_instructions,
    parse_instruction_steps,
    expand_to_clear_steps,
)
from app.services.recipe_image_urls import is_trusted_dish_image_url

BASE = "https://www.themealdb.com/api/json/v1/1"


def _get(url: str) -> dict[str, Any] | None:
    try:
        with urlopen(url, timeout=20) as resp:
            return json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def list_areas() -> list[str]:
    data = _get(f"{BASE}/list.php?a=list")
    if not data or not data.get("meals"):
        return []
    return sorted(str(m["strArea"]).strip() for m in data["meals"] if m.get("strArea"))


_CUISINE_AREAS: dict[str, tuple[str, ...]] = {
    "Chinese": ("Chinese",),
    "Italian": ("Italian",),
    # TheMealDB uses area name "India" (not "Indian").
    "Indian": ("India", "Pakistani", "Bangladeshi"),
    "Kashmiri": ("India", "Pakistani"),
    "Middle Eastern": ("Moroccan", "Turkish", "Greek", "Egyptian", "Lebanese", "Syrian"),
}


@lru_cache(maxsize=12)
def _cached_area_meals(area: str) -> tuple[dict[str, str], ...]:
    return tuple(meals_by_area(area))


def meals_by_area(area: str) -> list[dict[str, str]]:
    data = _get(f"{BASE}/filter.php?a={quote(area)}")
    if not data or not data.get("meals"):
        return []
    out: list[dict[str, str]] = []
    for m in data["meals"]:
        thumb = str(m.get("strMealThumb") or "").strip()
        out.append(
            {
                "idMeal": str(m.get("idMeal") or ""),
                "strMeal": str(m.get("strMeal") or ""),
                "strMealThumb": thumb,
            }
        )
    return out


def search_meals(query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """Search meals by name fragment (TheMealDB ``search.php``)."""
    q = (query or "").strip()
    if len(q) < 2:
        return []
    data = _get(f"{BASE}/search.php?s={quote(q)}")
    if not data or not data.get("meals"):
        return []
    out: list[dict[str, Any]] = []
    for m in data["meals"][: max(1, min(limit, 25))]:
        if isinstance(m, dict):
            out.append(m)
    return out


def _best_thumb_in_meals(query: str, meals: list[dict[str, Any]], *, min_similarity: float) -> str | None:
    from difflib import SequenceMatcher

    key = (query or "").strip().lower()
    if len(key) < 2:
        return None
    best_url: str | None = None
    best_score = 0.0
    for meal in meals:
        name = str(meal.get("strMeal") or "").strip()
        thumb = str(meal.get("strMealThumb") or "").strip()
        if not name or not is_trusted_dish_image_url(thumb):
            continue
        score = SequenceMatcher(None, key, name.lower()).ratio()
        if score > best_score:
            best_score = score
            best_url = thumb
    if best_url and best_score >= min_similarity:
        return best_url
    return None


def thumb_for_meal_name(query: str, *, min_similarity: float = 0.78) -> str | None:
    """Pick the best TheMealDB thumbnail for a recipe title via search + strict name match."""
    from app.services.recipe_image_match import pick_best_meal_thumb

    q = (query or "").strip()
    if len(q) < 2:
        return None
    url, _, _ = pick_best_meal_thumb(q, search_meals(q, limit=15), min_score=min_similarity)
    return url


def thumb_for_recipe(
    query: str,
    cuisine: str | None = None,
    *,
    min_similarity: float = 0.78,
) -> str | None:
    """Strict match only — returns None rather than a wrong cuisine photo."""
    from app.services.recipe_image_match import pick_best_meal_thumb, search_queries_for_recipe

    q = (query or "").strip()
    if len(q) < 2:
        return None
    for phrase in search_queries_for_recipe(q, cuisine):
        url, _, _ = pick_best_meal_thumb(
            q,
            search_meals(phrase, limit=15),
            min_score=min_similarity,
        )
        if url:
            return url
    pool: list[dict[str, Any]] = []
    for area in _CUISINE_AREAS.get((cuisine or "").strip(), ()):
        pool.extend(_cached_area_meals(area))
    if pool:
        url, _, _ = pick_best_meal_thumb(q, pool, min_score=min_similarity)
        if url:
            return url
    from app.services.wikimedia_images import wikimedia_loose_for_recipe, wikimedia_thumb_for_recipe

    url = wikimedia_thumb_for_recipe(q, cuisine)
    if url:
        return url
    return wikimedia_loose_for_recipe(q, cuisine)


def meal_detail(meal_id: str) -> dict[str, Any] | None:
    data = _get(f"{BASE}/lookup.php?i={quote(meal_id)}")
    if not data or not data.get("meals"):
        return None
    return data["meals"][0]


def meal_to_recipe_row(detail: dict[str, Any], *, cuisine_override: str | None = None) -> dict[str, Any]:
    """Build fields for Recipe model. ``cuisine_override`` stores a canonical label (e.g. Middle Eastern, Kashmiri)."""
    ingredients: list[dict[str, str | float]] = []
    for i in range(1, 21):
        ing = (detail.get(f"strIngredient{i}") or "").strip()
        meas = (detail.get(f"strMeasure{i}") or "").strip()
        if ing:
            ingredients.append({"name": ing[:120], "amount": 1.0, "unit": meas or "each"})
    name = (detail.get("strMeal") or "Meal")[:200]
    area = (cuisine_override or detail.get("strArea") or "International")[:80]
    instructions = (detail.get("strInstructions") or "See TheMealDB for steps.").strip()
    steps = parse_instruction_steps(instructions)
    if len(steps) < 3:
        steps = expand_to_clear_steps(instructions, min_steps=3)
    if len(steps) >= 3 and not re.search(r"step\s*1", instructions, re.IGNORECASE):
        instructions = format_steps_as_instructions(steps)
    serv = detail.get("servings") or "4"
    try:
        servings = max(1, int(str(serv).strip()[:3]))
    except ValueError:
        servings = 4
    thumb = (detail.get("strMealThumb") or detail.get("strImageSource") or "").strip()
    row = {
        "name": name,
        "cuisine": area,
        "instructions": instructions,
        "prep_minutes": 30,
        "calories_per_serving": 0,
        "servings": servings,
        "image_url": thumb[:512] if is_trusted_dish_image_url(thumb) else (thumb[:512] if thumb else ""),
        "ingredients_json": json.dumps(ingredients),
        "diet_tags": json.dumps([]),
        "health_notes": json.dumps([]),
    }
    if len(steps) >= 2:
        row["structured_steps_json"] = json.dumps(steps)
    return row
