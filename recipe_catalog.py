"""In-app recipe catalog: Kashmiri, Indian, Italian, Chinese, Middle Eastern only."""

from __future__ import annotations

# Display / DB labels (order matches Recipes filter)
ALLOWED_APP_CUISINES_ORDERED: tuple[str, ...] = (
    "Kashmiri",
    "Indian",
    "Italian",
    "Chinese",
    "Middle Eastern",
)

ALLOWED_APP_CUISINES: frozenset[str] = frozenset(ALLOWED_APP_CUISINES_ORDERED)

# Browse / catalog target (filled from bundled data + imports when below this)
MIN_RECIPES_PER_CUISINE = 10

# TheMealDB "area" names that map to catalog **Middle Eastern** (shared with regional import)
THEMEALDB_MIDDLE_EAST_AREAS: tuple[str, ...] = (
    "Egyptian",
    "Moroccan",
    "Turkish",
    "Lebanese",
    "Syrian",
    "Iranian",
    "Iraqi",
    "Tunisian",
    "Libyan",
    "Greek",
    "Saudi",
    "Kuwaiti",
    "Emirati",
    "Palestinian",
    "Jordanian",
)
_THEMEALDB_MIDDLE_EAST_AREAS_FS: frozenset[str] = frozenset(THEMEALDB_MIDDLE_EAST_AREAS)


def themealdb_area_to_catalog_cuisine(area: str) -> str | None:
    """Map a TheMealDB list.php area to one of the five catalog cuisines, or None if not allowed."""
    a = (area or "").strip()
    if not a:
        return None
    if a in ("Italian", "Chinese", "Indian"):
        return a
    if a in _THEMEALDB_MIDDLE_EAST_AREAS_FS:
        return "Middle Eastern"
    return None


_CUISINE_ALIASES: dict[str, str] = {
    "middle eastern": "Middle Eastern",
    "middle-eastern": "Middle Eastern",
    "middle east": "Middle Eastern",
    "mideast": "Middle Eastern",
    "mediterranean": "Middle Eastern",
}


def normalize_cuisine_label(raw: str | None) -> str | None:
    """Map CSV / legacy labels onto the five canonical cuisines, or None if out of scope."""
    if not raw:
        return None
    s = raw.strip()
    if not s:
        return None
    key = s.lower()
    if key in _CUISINE_ALIASES:
        return _CUISINE_ALIASES[key]
    if s in ALLOWED_APP_CUISINES:
        return s
    return None


def is_app_catalog_cuisine(cuisine: str | None) -> bool:
    return (cuisine or "").strip() in ALLOWED_APP_CUISINES
