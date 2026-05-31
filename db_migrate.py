"""Lightweight schema patches for dev DBs (no Alembic)."""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.core.database import engine
from app.services.recipe_image_urls import DEFAULT_RECIPE_IMAGE_URL


def _ensure_recipe_image_column() -> None:
    """Add ``recipes.image_url`` when missing and backfill empty values (all supported DB dialects)."""
    insp = inspect(engine)
    tables = insp.get_table_names()
    if "recipes" not in tables:
        return
    rcols = {c["name"] for c in insp.get_columns("recipes")}
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if "image_url" not in rcols:
            if dialect == "postgresql":
                conn.execute(text("ALTER TABLE recipes ADD COLUMN image_url VARCHAR(512)"))
            else:
                conn.execute(text("ALTER TABLE recipes ADD COLUMN image_url VARCHAR(512)"))
        conn.execute(
            text(
                "UPDATE recipes SET image_url = :u "
                "WHERE image_url IS NULL OR trim(image_url) = ''"
            ),
            {"u": DEFAULT_RECIPE_IMAGE_URL},
        )


def _ensure_recipe_spoonacular_columns() -> None:
    """Add Spoonacular step cache columns when missing (SQLite + PostgreSQL)."""
    insp = inspect(engine)
    tables = insp.get_table_names()
    if "recipes" not in tables:
        return
    rcols = {c["name"] for c in insp.get_columns("recipes")}
    dialect = engine.dialect.name
    with engine.begin() as conn:
        if "structured_steps_json" not in rcols:
            conn.execute(text("ALTER TABLE recipes ADD COLUMN structured_steps_json TEXT"))
        if "spoonacular_recipe_id" not in rcols:
            if dialect == "postgresql":
                conn.execute(text("ALTER TABLE recipes ADD COLUMN spoonacular_recipe_id INTEGER"))
            else:
                conn.execute(text("ALTER TABLE recipes ADD COLUMN spoonacular_recipe_id INTEGER"))
        if "spoonacular_guide_json" not in rcols:
            conn.execute(text("ALTER TABLE recipes ADD COLUMN spoonacular_guide_json TEXT"))


def ensure_schema():
    _ensure_recipe_image_column()
    _ensure_recipe_spoonacular_columns()

    if not str(engine.url).startswith("sqlite"):
        return
    insp = inspect(engine)
    tables = insp.get_table_names()
    if "users" not in tables:
        return
    cols = {c["name"] for c in insp.get_columns("users")}
    with engine.begin() as conn:
        if "ai_preferences" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN ai_preferences TEXT"))
        if "favorite_cuisines" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN favorite_cuisines TEXT"))
        if "cooking_mode" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN cooking_mode VARCHAR(16) DEFAULT 'solo'"))
    if "recipes" in tables:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    DELETE FROM recipes
                    WHERE id IN (
                        SELECT r1.id FROM recipes r1
                        WHERE EXISTS (
                            SELECT 1 FROM recipes r2
                            WHERE r2.id < r1.id
                            AND lower(trim(r2.name)) = lower(trim(r1.name))
                            AND r2.cuisine = r1.cuisine
                        )
                    )
                    """
                )
            )
            conn.execute(
                text(
                    "UPDATE recipes SET cuisine = 'Middle Eastern' "
                    "WHERE cuisine IN ('Middle East', 'Mediterranean')"
                )
            )
