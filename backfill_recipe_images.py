#!/usr/bin/env python3
"""Assign a real dish photo (TheMealDB) to every recipe missing one."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal, init_db  # noqa: E402
from app.services.dish_image_datasets import dataset_stats, reassign_all_recipe_images_strict  # noqa: E402


def main() -> int:
    init_db()
    stats_before = dataset_stats()
    print("Bundled image index:", stats_before)
    with SessionLocal() as db:
        counts = reassign_all_recipe_images_strict(db, online=True)
    print("Updated:", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
