"""Strict recipe title → dish photo matching (avoids wrong cuisine fallbacks)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from app.services.recipe_image_urls import is_trusted_dish_image_url

# Fuzzy match only when this confident (same dish name, not just same cuisine).
STRICT_NAME_SIMILARITY = 0.78
EXACT_NAME_SIMILARITY = 0.92
TOKEN_SUBSET_MIN_SIMILARITY = 0.72

_STOPWORDS = frozenset(
    {
        "with",
        "and",
        "the",
        "a",
        "an",
        "style",
        "recipe",
        "homemade",
        "classic",
        "traditional",
        "easy",
        "quick",
    }
)

_SYNTHETIC_PREFIX = re.compile(r"^pantryflow\s+", re.I)


def norm_recipe_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def significant_tokens(name: str) -> frozenset[str]:
    return frozenset(
        t
        for t in re.findall(r"[a-z0-9]+", norm_recipe_name(name))
        if len(t) >= 3 and t not in _STOPWORDS
    )


def name_similarity(a: str, b: str) -> float:
    aa, bb = norm_recipe_name(a), norm_recipe_name(b)
    if not aa or not bb:
        return 0.0
    seq = SequenceMatcher(None, aa, bb).ratio()
    ta, tb = significant_tokens(aa), significant_tokens(bb)
    if not ta or not tb:
        return seq
    overlap = len(ta & tb) / len(ta | tb)
    return max(seq, overlap)


def is_acceptable_match(recipe_name: str, meal_name: str, *, min_score: float = STRICT_NAME_SIMILARITY) -> bool:
    score = name_similarity(recipe_name, meal_name)
    ta, tb = significant_tokens(recipe_name), significant_tokens(meal_name)
    if not ta:
        return score >= EXACT_NAME_SIMILARITY
    if not (ta & tb):
        return score >= EXACT_NAME_SIMILARITY
    # e.g. recipe "Rogan Josh" → meal "Lamb Rogan josh" (extra protein word is fine).
    if ta <= tb and score >= TOKEN_SUBSET_MIN_SIMILARITY:
        return True
    return score >= min_score


def pick_best_meal_thumb(
    recipe_name: str,
    meals: list[dict[str, Any]],
    *,
    min_score: float = STRICT_NAME_SIMILARITY,
) -> tuple[str | None, float, str | None]:
    """Return (thumb_url, score, matched_meal_name)."""
    best_url: str | None = None
    best_score = 0.0
    best_meal: str | None = None
    for meal in meals:
        meal_name = str(meal.get("strMeal") or "").strip()
        thumb = str(meal.get("strMealThumb") or "").strip()
        if not meal_name or not is_trusted_dish_image_url(thumb):
            continue
        score = name_similarity(recipe_name, meal_name)
        if score > best_score and is_acceptable_match(recipe_name, meal_name, min_score=min_score):
            best_score = score
            best_url = thumb
            best_meal = meal_name
    if best_url:
        return best_url, best_score, best_meal
    return None, 0.0, None


_INDIAN_ALIASES: dict[str, tuple[str, ...]] = {
    "chana masala": ("chana masala", "chole masala", "chickpea curry"),
    "butter chicken": ("butter chicken", "murgh makhani", "chicken makhani"),
    "dal makhani": ("dal makhani", "maa ki dal"),
    "palak paneer": ("palak paneer", "saag paneer"),
    "hyderabadi biryani": ("hyderabadi biryani", "chicken biryani"),
    "chicken tikka wrap": ("chicken tikka", "tikka wrap"),
    "baingan bharta": ("baingan bharta", "baingan ka bharta"),
    "bhindi masala": ("bhindi masala", "okra masala", "bhindi curry"),
    "paneer tikka": ("paneer tikka",),
    "masala dosa": ("masala dosa",),
    "malai kofta": ("malai kofta",),
    "shahi paneer": ("shahi paneer",),
    "khichdi": ("khichdi", "khichri"),
    "upma": ("upma",),
    "vegetable biryani": ("vegetable biryani", "veg biryani"),
    "chicken chettinad": ("chicken chettinad", "chettinad chicken"),
    "kadhi pakora": ("kadhi pakora", "kadhi"),
    "methi matar malai": ("methi matar malai",),
    "tandoori cauliflower": ("tandoori cauliflower", "gobi tandoori"),
    "rogan mushroom": ("mushroom curry", "mushroom masala"),
}


def search_queries_for_recipe(name: str, cuisine: str | None) -> list[str]:
    """Ordered search phrases for TheMealDB (most specific first)."""
    base = (name or "").strip()
    if not base:
        return []
    cleaned = _SYNTHETIC_PREFIX.sub("", base).strip()
    cleaned = re.sub(r"\s+\d{1,2}$", "", cleaned).strip() or base
    out: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        k = norm_recipe_name(q)
        if k and k not in seen:
            seen.add(k)
            out.append(q)

    add(cleaned)
    cu = (cuisine or "").strip()
    if cu == "Kashmiri":
        add(f"Kashmiri {cleaned}")
        add(f"{cleaned} Kashmiri")
        # Common transliterations / alternate dish names on TheMealDB
        aliases = _KASHMIRI_ALIASES.get(norm_recipe_name(cleaned), ())
        for alt in aliases:
            add(alt)
    if cu == "Indian":
        add(f"Indian {cleaned}")
        for alt in _INDIAN_ALIASES.get(norm_recipe_name(cleaned), ()):
            add(alt)
    tokens = [t for t in re.findall(r"[a-z0-9]+", cleaned.lower()) if len(t) >= 4]
    if len(tokens) >= 2:
        add(" ".join(tokens[:3]))
    return out


# Catalog dish name → extra TheMealDB search titles (when the plain name is not listed).
_KASHMIRI_ALIASES: dict[str, tuple[str, ...]] = {
    "dum olav": ("dum aloo", "dum aaloo", "kashmiri dum aloo"),
    "dum aloo": ("dum oloo", "dum olav"),
    "rogan josh": ("lamb rogan josh", "rogan josh kashmir"),
    "yakhni pulao": ("yakhni pulao", "yakhni", "pulao"),
    "gushtaba": ("gushtaba", "kashmiri gushtaba"),
    "rista": ("rista kashmiri", "kashmiri rista"),
    "lyodur tschaman": ("lyodur tschaman", "tschaman", "paneer curry kashmir"),
    "haak": ("haak", "kashmiri haak", "collard greens kashmir"),
    "kabargah": ("tabak maaz", "kashmiri lamb ribs"),
    "tabak maaz": ("tabak maaz", "kabargah"),
    "marchwangan korma": ("marchwangan korma", "kashmiri korma"),
    "aab gosh": ("aab gosh", "aab gosht", "dodhe maaz", "dodhe maaz kashmiri", "kashmiri wazwan lamb"),
    "kaliya": ("kaliya kashmiri",),
    "muji gaad": ("muji gaad", "fish radish kashmir"),
    "nadur yakhni": ("nadur yakhni", "lotus stem curry"),
    "modur pulao": ("modur pulao", "sweet pulao"),
    "shufta": ("shufta kashmiri",),
    "waza kokur": ("waza kokur", "kashmiri chicken wazwan"),
    "methi maaz": ("methi maaz", "lamb fenugreek kashmir"),
    "safed kokur": ("safed kokur", "kashmiri chicken white"),
    "monji haak": ("monji haak",),
    "chok wangun": ("chok wangun", "kashmiri eggplant", "baingan kashmiri"),
    "nadir monji": ("nadir monji", "lotus stem fritters"),
    "al hachi": ("al hachi", "kashmiri dried bottle gourd"),
    "rajma gogji": ("rajma gogji", "kidney beans turnip kashmir"),
    "kashmiri harissa": ("harissa kashmiri",),
    "noon chai": ("noon chai", "kashmiri tea"),
    "tehar": ("tehar", "kashmiri rice"),
    "daniwal korma": ("daniwal korma", "lamb korma kashmir"),
    "gaade tamatar": ("gaade tamatar", "fish tomato kashmir"),
    "khatte baingan": ("khatte baingan", "sour eggplant kashmir"),
    "kong phir": ("kong phir", "kashmiri rice"),
    "veth tsaman": ("veth tsaman", "paneer kashmiri"),
    "marchwangan korma": ("marchwangan korma", "kashmiri red chilli korma"),
}
