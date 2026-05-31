"""Offline per-cuisine datasets under ``data/catalog/*.json`` plus synthetic fallback."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any
from zlib import crc32

from sqlalchemy.orm import Session

from app.models import Recipe
from app.services.recipe_catalog import (
    ALLOWED_APP_CUISINES,
    ALLOWED_APP_CUISINES_ORDERED,
    MIN_RECIPES_PER_CUISINE,
)
from app.services.instruction_steps import (
    format_steps_as_instructions,
    steps_from_dataset_entry,
    structured_steps_json_for_row,
)
from app.services.dish_image_datasets import lookup_dish_image
from app.services.recipe_dedup import canonical_recipe_key, recipes_are_duplicates
from app.services.recipe_image_urls import ensure_recipe_image_url, placeholder_image_url

logger = logging.getLogger(__name__)

_CUISINE_DATASET_FILES: dict[str, str] = {
    "Kashmiri": "kashmiri.json",
    "Indian": "indian.json",
    "Italian": "italian.json",
    "Chinese": "chinese.json",
    "Middle Eastern": "middle_eastern.json",
}


def _catalog_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "catalog"


def _synthetic_rows_for(cuisine: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i in range(1, 13):
        ingredients = [
            {"name": "Onion", "amount": 1.0, "unit": "each"},
            {"name": "Cooking oil", "amount": 2.0, "unit": "tbsp"},
            {"name": f"{cuisine} spice blend", "amount": round(1.0 + i * 0.07, 2), "unit": "tbsp"},
        ]
        steps = [
            f"Gather ingredients for this {cuisine} dish and prep aromatics (onion, garlic, spices).",
            "Heat oil in a pan, bloom whole spices until fragrant, then add the main ingredients.",
            "Simmer with a splash of water or stock until tender and the sauce coats the food.",
            "Taste, adjust salt and acidity, garnish, and serve warm.",
        ]
        out.append(
            {
                "name": f"PantryFlow {cuisine} {i:02d}",
                "cuisine": cuisine,
                "instructions": format_steps_as_instructions(steps),
                "structured_steps_json": json.dumps(steps),
                "prep_minutes": 18 + (i % 22),
                "calories_per_serving": 200 + (i * 13) % 220,
                "servings": 4,
                "image_url": lookup_dish_image(f"PantryFlow {cuisine} {i:02d}", cuisine)
                or placeholder_image_url(i),
                "ingredients_json": json.dumps(ingredients),
                "diet_tags": json.dumps(["vegetarian", "gluten-free"]),
                "health_notes": json.dumps(["heart-healthy"]),
            }
        )
    return out


def _normalize_dataset_entry(raw: dict[str, Any]) -> dict[str, Any]:
    ingredients = raw.get("ingredients") or []
    diet = raw.get("diet_tags") or []
    health = raw.get("health_notes") or []
    if not isinstance(ingredients, list):
        ingredients = []
    if not isinstance(diet, list):
        diet = []
    if not isinstance(health, list):
        health = []
    nm = str(raw.get("name", "Recipe"))[:200]
    cuisine = str(raw.get("cuisine", "")).strip()[:80]
    bundled = lookup_dish_image(nm, cuisine or None)
    if bundled:
        img = bundled
    elif raw.get("image_url"):
        img = ensure_recipe_image_url(raw.get("image_url")) or placeholder_image_url(
            abs(crc32(nm.encode("utf-8", errors="ignore"))) % 7
        )
    else:
        img = placeholder_image_url(abs(crc32(nm.encode("utf-8", errors="ignore"))) % 7)
    steps = steps_from_dataset_entry(raw)
    instr = str(raw.get("instructions") or "").strip()
    if steps and len(steps) >= 3 and not re.search(r"step\s*1", instr, re.IGNORECASE):
        instr = format_steps_as_instructions(steps)
    elif not instr:
        instr = "Prepare ingredients and cook until done."
    structured = structured_steps_json_for_row(raw) or (
        json.dumps(steps) if len(steps) >= 2 else None
    )
    row: dict[str, Any] = {
        "name": nm,
        "cuisine": str(raw.get("cuisine", "")).strip()[:80],
        "instructions": instr,
        "prep_minutes": int(raw.get("prep_minutes") or 30),
        "calories_per_serving": int(raw.get("calories_per_serving") or 0),
        "servings": max(1, int(raw.get("servings") or 4)),
        "image_url": img[:512],
        "ingredients_json": json.dumps(ingredients),
        "diet_tags": json.dumps(diet),
        "health_notes": json.dumps(health),
    }
    if structured:
        row["structured_steps_json"] = structured
    return row


def _load_bundled_catalog_rows() -> list[dict[str, Any]]:
    base = _catalog_dir()
    out: list[dict[str, Any]] = []
    for cuisine, fname in _CUISINE_DATASET_FILES.items():
        path = base / fname
        if path.is_file():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON in %s: %s", path, e)
                out.extend(_synthetic_rows_for(cuisine))
                continue
            if not isinstance(payload, list):
                logger.error("Expected list in %s", path)
                out.extend(_synthetic_rows_for(cuisine))
                continue
            n = 0
            for raw in payload:
                if not isinstance(raw, dict):
                    continue
                row = _normalize_dataset_entry(raw)
                if row["cuisine"] != cuisine:
                    row["cuisine"] = cuisine
                out.append(row)
                n += 1
            logger.info("Loaded %s offline recipes for %s from %s", n, cuisine, fname)
        else:
            logger.warning("Missing dataset %s — using synthetic fallback for %s", path, cuisine)
            out.extend(_synthetic_rows_for(cuisine))
    return out


BUNDLED_CATALOG_RECIPES: list[dict[str, Any]] = _load_bundled_catalog_rows()


def _row_exists(db: Session, name: str, cuisine: str) -> bool:
    key = canonical_recipe_key(name, cuisine)
    for r in db.query(Recipe.id, Recipe.name).filter(Recipe.cuisine == cuisine).all():
        if canonical_recipe_key(r.name, cuisine) == key:
            return True
        if recipes_are_duplicates(name, r.name, cuisine=cuisine):
            return True
    return False


def top_up_catalog_to_minimum(db: Session) -> dict[str, int]:
    """Insert bundled recipes until each allowed cuisine has at least ``MIN_RECIPES_PER_CUISINE`` rows."""
    added_by: dict[str, int] = {c: 0 for c in ALLOWED_APP_CUISINES_ORDERED}
    try:
        for cuisine in ALLOWED_APP_CUISINES_ORDERED:
            current = db.query(Recipe).filter(Recipe.cuisine == cuisine).count()
            if current >= MIN_RECIPES_PER_CUISINE:
                continue
            need = MIN_RECIPES_PER_CUISINE - current
            for row in BUNDLED_CATALOG_RECIPES:
                if row["cuisine"] != cuisine:
                    continue
                if need <= 0:
                    break
                if _row_exists(db, row["name"], cuisine):
                    continue
                db.add(Recipe(**row))
                need -= 1
                added_by[cuisine] += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    total = sum(added_by.values())
    if total:
        logger.info("Catalog top-up inserted %s recipes: %s", total, added_by)
    return added_by


def merge_bundled_catalog_recipes(db: Session) -> dict[str, int]:
    """Insert bundled catalog rows that are not yet in the DB (same name + cuisine)."""
    added_by: dict[str, int] = {c: 0 for c in ALLOWED_APP_CUISINES_ORDERED}
    try:
        for row in BUNDLED_CATALOG_RECIPES:
            cuisine = (row.get("cuisine") or "").strip()
            if cuisine not in ALLOWED_APP_CUISINES:
                continue
            if _row_exists(db, row["name"], cuisine):
                continue
            db.add(Recipe(**row))
            added_by[cuisine] += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    total = sum(added_by.values())
    if total:
        logger.info("Bundled catalog merge inserted %s recipes: %s", total, added_by)
    return added_by
