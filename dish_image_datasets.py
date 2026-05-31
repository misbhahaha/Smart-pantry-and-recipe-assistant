"""Bundled dish-photo datasets under ``data/datasets/`` and strict DB backfill."""

from __future__ import annotations

import json
import logging
import re
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.models import Recipe
from app.services.recipe_image_match import norm_recipe_name, name_similarity
from app.services.recipe_image_urls import is_placeholder_image_url, is_trusted_dish_image_url

logger = logging.getLogger(__name__)

_DATASET_FILES: tuple[str, ...] = (
    "curated_dish_images.json",
    "dish_images_exact.json",
    "dish_images_themealdb.json",
    "dish_images_catalog.json",
)

_STRICT_FUZZY_CUTOFF = 0.78
_SYNTHETIC_PREFIX = re.compile(r"^pantryflow\s+", re.I)

_CATALOG_FILES: dict[str, str] = {
    "Kashmiri": "kashmiri.json",
    "Indian": "indian.json",
    "Italian": "italian.json",
    "Chinese": "chinese.json",
    "Middle Eastern": "middle_eastern.json",
}


def _datasets_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "datasets"


def _catalog_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "catalog"


def recipe_title_for_image_search(name: str) -> str:
    n = _SYNTHETIC_PREFIX.sub("", (name or "").strip())
    n = re.sub(r"\s+\d{1,2}$", "", n).strip()
    return n or (name or "").strip()


def _exact_key(name: str, cuisine: str | None) -> str:
    return f"{(cuisine or '').strip().lower()}::{norm_recipe_name(name)}"


def needs_dish_image(stored_url: str | None) -> bool:
    current = (stored_url or "").strip()
    if not current:
        return True
    if is_placeholder_image_url(current):
        return True
    return not is_trusted_dish_image_url(current)


@lru_cache(maxsize=1)
def _catalog_name_images() -> dict[str, str]:
    """Exact images stored on catalog JSON rows (highest priority)."""
    out: dict[str, str] = {}
    for cuisine, fname in _CATALOG_FILES.items():
        path = _catalog_dir() / fname
        if not path.is_file():
            continue
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            url = str(row.get("image_url") or "").strip()
            if name and url and is_trusted_dish_image_url(url):
                out[_exact_key(name, cuisine)] = url
    return out


@lru_cache(maxsize=1)
def _merged_index() -> dict[str, Any]:
    """Merge exact map + bundled datasets; catalog file entries override."""
    by_exact: dict[str, str] = {}
    by_name: dict[str, str] = {}
    by_cuisine: dict[str, dict[str, str]] = {}
    sources: list[str] = []

    for fname in _DATASET_FILES:
        path = _datasets_dir() / fname
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not load dish image dataset %s: %s", path, exc)
            continue
        if not isinstance(payload, dict):
            continue
        src = str(payload.get("source") or fname)
        sources.append(src)
        for k, v in (payload.get("by_exact") or {}).items():
            url = str(v or "").strip()
            if url and is_trusted_dish_image_url(url):
                by_exact[str(k)] = url
        for k, v in (payload.get("by_name") or {}).items():
            url = str(v or "").strip()
            if url and is_trusted_dish_image_url(url):
                by_name[norm_recipe_name(str(k))] = url
        for cuisine, bucket in (payload.get("by_cuisine") or {}).items():
            if not isinstance(bucket, dict):
                continue
            cu = str(cuisine).strip()
            by_cuisine.setdefault(cu, {})
            for k, v in bucket.items():
                url = str(v or "").strip()
                if url and is_trusted_dish_image_url(url):
                    by_cuisine[cu][norm_recipe_name(str(k))] = url

    # Catalog JSON may contain outdated URLs; only verified dataset keys are merged above.
    return {
        "by_exact": by_exact,
        "by_name": by_name,
        "by_cuisine": by_cuisine,
        "sources": sources,
    }


def lookup_dish_image(name: str, cuisine: str | None = None) -> str | None:
    """Return a trusted dish photo only when the title matches precisely enough."""
    if _SYNTHETIC_PREFIX.search((name or "").strip()):
        return None
    key = norm_recipe_name(name)
    if not key:
        return None
    idx = _merged_index()
    exact = (idx.get("by_exact") or {}).get(_exact_key(name, cuisine))
    if exact:
        return exact
    by_name: dict[str, str] = idx.get("by_name") or {}
    if key in by_name:
        return by_name[key]

    cuisine_key = (cuisine or "").strip()
    bucket: dict[str, str] = (idx.get("by_cuisine") or {}).get(cuisine_key, {})
    if key in bucket:
        return bucket[key]
    return None


def backfill_recipe_images_online(db: Session, *, limit: int = 40) -> int:
    from app.services.themealdb import thumb_for_recipe

    updated = 0
    for recipe in db.query(Recipe).order_by(Recipe.id).all():
        if updated >= limit:
            break
        search_title = recipe_title_for_image_search(recipe.name)
        url = thumb_for_recipe(search_title, recipe.cuisine)
        if not url:
            continue
        if (recipe.image_url or "").strip() == url:
            continue
        recipe.image_url = url[:512]
        updated += 1
        time.sleep(0.15)
    if updated:
        try:
            db.commit()
            logger.info("Strict TheMealDB image backfill updated %s recipes.", updated)
        except Exception:
            db.rollback()
            raise
    return updated


def resolve_stored_or_dataset_image(
    stored_url: str | None,
    *,
    name: str,
    cuisine: str | None = None,
) -> str:
    """Return a trusted photo only for an exact title match — never a wrong substitute."""
    del stored_url  # DB cache ignored; prevents stale/wrong photos from showing.
    return lookup_dish_image(name, cuisine) or ""


def reload_dataset_index() -> None:
    _merged_index.cache_clear()
    _catalog_name_images.cache_clear()


def backfill_recipe_images(db: Session, *, limit: int = 5000) -> int:
    reload_dataset_index()
    updated = 0
    rows = db.query(Recipe).order_by(Recipe.id).limit(max(1, min(limit, 10000))).all()
    for recipe in rows:
        url = lookup_dish_image(recipe.name, recipe.cuisine)
        if not url:
            continue
        if (recipe.image_url or "").strip() == url:
            continue
        recipe.image_url = url[:512]
        updated += 1
    if updated:
        try:
            db.commit()
            logger.info("Dataset image backfill updated %s recipes.", updated)
        except Exception:
            db.rollback()
            raise
    return updated


def reassign_all_recipe_images_strict(db: Session, *, online: bool = True) -> dict[str, int]:
    """Force every recipe to use strict title-matched photos (fixes wrong assignments)."""
    from app.services.themealdb import thumb_for_recipe

    reload_dataset_index()
    dataset_n = 0
    online_n = 0
    skipped = 0
    for recipe in db.query(Recipe).order_by(Recipe.id).all():
        url = lookup_dish_image(recipe.name, recipe.cuisine)
        if not url and online:
            url = thumb_for_recipe(
                recipe_title_for_image_search(recipe.name),
                recipe.cuisine,
            )
            if url:
                online_n += 1
                time.sleep(0.15)
        elif url:
            dataset_n += 1
        if not url:
            recipe.image_url = ""
            skipped += 1
            continue
        recipe.image_url = url[:512]
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    logger.info(
        "Strict image reassignment: dataset=%s online=%s cleared=%s",
        dataset_n,
        online_n,
        skipped,
    )
    return {"dataset": dataset_n, "online": online_n, "cleared": skipped}


def backfill_all_recipe_images(db: Session, *, online: bool = True) -> dict[str, int]:
    return reassign_all_recipe_images_strict(db, online=online)


def fill_missing_recipe_images(db: Session, *, online: bool = True, limit: int = 5000) -> int:
    """Assign trusted photos only where the recipe row has none (never clear existing)."""
    from app.services.themealdb import thumb_for_recipe

    reload_dataset_index()
    updated = 0
    for recipe in db.query(Recipe).order_by(Recipe.id).limit(max(1, min(limit, 10000))).all():
        if resolve_stored_or_dataset_image(
            getattr(recipe, "image_url", None),
            name=recipe.name,
            cuisine=recipe.cuisine,
        ):
            continue
        url = lookup_dish_image(recipe.name, recipe.cuisine)
        if not url and online:
            url = thumb_for_recipe(
                recipe_title_for_image_search(recipe.name),
                recipe.cuisine,
            )
            if url:
                time.sleep(0.12)
        if not url:
            continue
        recipe.image_url = url[:512]
        updated += 1
    if updated:
        try:
            db.commit()
            logger.info("Filled missing images for %s recipes.", updated)
        except Exception:
            db.rollback()
            raise
    return updated


def dataset_stats() -> dict[str, Any]:
    idx = _merged_index()
    return {
        "sources": idx.get("sources") or [],
        "exact_count": len(idx.get("by_exact") or {}),
        "by_name_count": len(idx.get("by_name") or {}),
        "cuisines": {c: len(b) for c, b in (idx.get("by_cuisine") or {}).items()},
    }
