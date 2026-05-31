#!/usr/bin/env python3
"""Fill trusted recipe photos for rows that have none (strict title match only)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import SessionLocal, init_db  # noqa: E402
from app.models import Recipe  # noqa: E402
from app.services.dish_image_datasets import (  # noqa: E402
    fill_missing_recipe_images,
    reload_dataset_index,
    resolve_stored_or_dataset_image,
)


def main() -> int:
    init_db()
    with SessionLocal() as db:
        before = sum(
            1
            for r in db.query(Recipe).all()
            if not resolve_stored_or_dataset_image(r.image_url, name=r.name, cuisine=r.cuisine)
        )
        print(f"Recipes without trusted image before: {before}")
        filled = fill_missing_recipe_images(db, online=True)
        reload_dataset_index()
        after = sum(
            1
            for r in db.query(Recipe).all()
            if not resolve_stored_or_dataset_image(r.image_url, name=r.name, cuisine=r.cuisine)
        )
        print(f"Filled this run: {filled}; still missing: {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
