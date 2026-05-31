"""Recipe cover images: trusted dish photos vs generic placeholders."""

from __future__ import annotations

# Neutral food hero (Unsplash); used only as seed placeholder, not shown in UI.
DEFAULT_RECIPE_IMAGE_URL = (
    "https://images.unsplash.com/photo-1495521821757-a1efb6729352?w=800&auto=format&fit=crop&q=80"
)

_PLACEHOLDER_ROTATION: tuple[str, ...] = (
    "https://images.unsplash.com/photo-1546069901-ba9599a7e63c?w=800&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1504674900240-903c2f473a88?w=800&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=800&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=800&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1473093295043-cdd812d0e601?w=800&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1563379926898-05f4575a220d?w=800&auto=format&fit=crop&q=80",
    "https://images.unsplash.com/photo-1555939594-58d7cb561ad1?w=800&auto=format&fit=crop&q=80",
)

_TRUSTED_HOST_FRAGMENTS: tuple[str, ...] = (
    "themealdb.com",
    "img.spoonacular.com",
    "spoonacular.com/cdn",
    "upload.wikimedia.org",
    "commons.wikimedia.org",
)


def is_trusted_dish_image_url(value: str | None) -> bool:
    v = (value or "").strip().lower()
    if not v.startswith("https://"):
        return False
    return any(host in v for host in _TRUSTED_HOST_FRAGMENTS)


def is_placeholder_image_url(value: str | None) -> bool:
    v = (value or "").strip()
    if not v:
        return True
    if "images.unsplash.com" in v.lower():
        return True
    if v == DEFAULT_RECIPE_IMAGE_URL:
        return True
    return v in _PLACEHOLDER_ROTATION


def ensure_recipe_image_url(value: str | None) -> str:
    """Return stored URL when trusted; otherwise empty (clients skip generic stock art)."""
    v = (value or "").strip()
    if is_trusted_dish_image_url(v):
        return v
    if v and not is_placeholder_image_url(v):
        return v
    return ""


def placeholder_image_url(rotation_index: int) -> str:
    """Deterministic placeholder for synthetic or CSV rows without art."""
    if rotation_index < 0:
        rotation_index = 0
    return _PLACEHOLDER_ROTATION[rotation_index % len(_PLACEHOLDER_ROTATION)]
