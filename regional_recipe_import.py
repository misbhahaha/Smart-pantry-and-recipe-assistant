"""Bulk-import recipes for canonical cuisines via TheMealDB (free API).

Targets: Kashmiri, Indian, Italian, Chinese, Middle Eastern.
TheMealDB uses regional "areas"; we map many areas → "Middle Eastern" and pool Indian / Pakistani / Bangladeshi
→ "Kashmiri" (keyword-priority) so each bucket can grow toward large caps.

Counts are **best-effort**: TheMealDB may list fewer than ``per_cuisine_cap`` meals per area.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Recipe
from app.services.recipe_catalog import THEMEALDB_MIDDLE_EAST_AREAS
from app.services.themealdb import meal_detail, meals_by_area, meal_to_recipe_row

# TheMealDB area names (subset); must match ``THEMEALDB_MIDDLE_EAST_AREAS`` in recipe_catalog.
_MIDDLE_EAST_AREAS = list(THEMEALDB_MIDDLE_EAST_AREAS)

_KASHMIRI_KEYWORDS = (
    "kashmir",
    "kashmiri",
    "rogan",
    "yakhni",
    "gushtaba",
    "gushta",
    "rista",
    "wazwan",
    "waza",
    "tabak",
    "nadur",
    "haak",
    "mirch",
    "dum ",
    "shab",
    "yogurt",
    "yoghurt",
    "chaman",
    "modur",
    "matshang",
)


def _name_exists(db: Session, name: str, cuisine: str) -> bool:
    n = name.strip().lower()
    return (
        db.query(Recipe.id)
        .filter(
            func.lower(func.trim(Recipe.name)) == n,
            Recipe.cuisine == cuisine,
        )
        .limit(1)
        .first()
        is not None
    )


def _add_meal(db: Session, meal_id: str, cuisine: str, seen_ids: set[str]) -> bool:
    if meal_id in seen_ids:
        return False
    detail = meal_detail(meal_id)
    if not detail:
        return False
    row = meal_to_recipe_row(detail, cuisine_override=cuisine)
    if _name_exists(db, row["name"], cuisine):
        return False
    db.add(Recipe(**row))
    seen_ids.add(meal_id)
    return True


def _import_area_cap(db: Session, area: str, cuisine: str, cap: int, seen_ids: set[str]) -> int:
    meals = meals_by_area(area) or []
    n = 0
    for m in meals:
        if n >= cap:
            break
        mid = str(m.get("idMeal") or "")
        if not mid:
            continue
        if _add_meal(db, mid, cuisine, seen_ids):
            n += 1
    return n


def _import_middle_east(db: Session, cap: int, seen_ids: set[str]) -> int:
    n = 0
    for area in _MIDDLE_EAST_AREAS:
        if n >= cap:
            break
        remaining = cap - n
        n += _import_area_cap(db, area, "Middle Eastern", remaining, seen_ids)
    return n


def _kashmiri_sort_key(m: dict) -> int:
    t = str(m.get("strMeal") or "").lower()
    return 1 if any(k in t for k in _KASHMIRI_KEYWORDS) else 0


def _import_kashmiri(db: Session, cap: int, seen_ids: set[str]) -> int:
    pool: list[dict] = []
    for area in ("Indian", "Pakistani", "Bangladeshi"):
        pool.extend(meals_by_area(area) or [])
    pool.sort(key=_kashmiri_sort_key, reverse=True)
    n = 0
    for m in pool:
        if n >= cap:
            break
        mid = str(m.get("idMeal") or "")
        if not mid:
            continue
        if _add_meal(db, mid, "Kashmiri", seen_ids):
            n += 1
    return n


def import_kashmiri_themealdb_candidates(db: Session, cap: int = 15) -> int:
    """Pull Indian / Pakistani / Bangladeshi TheMealDB meals whose titles match Kashmiri keywords → cuisine Kashmiri."""
    n = _import_kashmiri(db, max(1, min(cap, 50)), set())
    if n:
        db.commit()
    return n


def _import_indian_subcontinent(db: Session, cap: int, seen_ids: set[str]) -> int:
    """Fill **Indian** cuisine from Indian, Pakistani, and Bangladeshi TheMealDB areas (deduped by meal id)."""
    n = 0
    for area in ("Indian", "Pakistani", "Bangladeshi"):
        if n >= cap:
            break
        n += _import_area_cap(db, area, "Indian", cap - n, seen_ids)
    return n


def import_five_cuisine_bundles(db: Session, per_cuisine_cap: int) -> dict[str, int | str]:
    """Import up to ``per_cuisine_cap`` recipes per canonical cuisine (best-effort)."""
    cap = max(10, min(per_cuisine_cap, 500))
    seen: set[str] = set()
    stats: dict[str, int | str] = {}

    # Kashmiri first so keyword-weighted Indian / neighbours fill this bucket before Indian proper.
    stats["Kashmiri"] = _import_kashmiri(db, cap, seen)
    stats["Indian"] = _import_indian_subcontinent(db, cap, seen)
    stats["Italian"] = _import_area_cap(db, "Italian", "Italian", cap, seen)
    stats["Chinese"] = _import_area_cap(db, "Chinese", "Chinese", cap, seen)
    stats["Middle Eastern"] = _import_middle_east(db, cap, seen)

    db.commit()
    stats["note"] = (
        "TheMealDB limits how many distinct meals exist per area; counts may be below the cap. "
        "Run again after new meals appear on TheMealDB, or raise the cap once duplicates are exhausted."
    )
    return stats
