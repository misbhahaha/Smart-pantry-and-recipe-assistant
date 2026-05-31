#!/usr/bin/env python3
"""Build strict per-recipe image map for catalog + DB (TheMealDB title match only)."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.database import SessionLocal, init_db  # noqa: E402
from app.models import Recipe  # noqa: E402
from app.services.dish_image_datasets import _catalog_dir, _exact_key, reload_dataset_index  # noqa: E402
from app.services.recipe_image_match import norm_recipe_name  # noqa: E402
from app.services.themealdb import thumb_for_recipe  # noqa: E402

CATALOG_FILES = {
    "Kashmiri": "kashmiri.json",
    "Indian": "indian.json",
    "Italian": "italian.json",
    "Chinese": "chinese.json",
    "Middle Eastern": "middle_eastern.json",
}


def _collect_names() -> list[tuple[str, str]]:
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for cuisine, fname in CATALOG_FILES.items():
        path = _catalog_dir() / fname
        if not path.is_file():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            if not name:
                continue
            k = _exact_key(name, cuisine)
            if k in seen:
                continue
            seen.add(k)
            out.append((name, cuisine))
    init_db()
    with SessionLocal() as db:
        for r in db.query(Recipe).order_by(Recipe.id):
            k = _exact_key(r.name, r.cuisine)
            if k in seen:
                continue
            seen.add(k)
            out.append((r.name, r.cuisine))
    return out


def main() -> int:
    names = _collect_names()
    print(f"Mapping {len(names)} recipes with strict TheMealDB matching…")
    by_exact: dict[str, str] = {}
    by_name: dict[str, str] = {}
    by_cuisine: dict[str, dict[str, str]] = {}
    meta: dict[str, dict] = {}
    missed: list[str] = []

    for i, (name, cuisine) in enumerate(names, 1):
        url = thumb_for_recipe(name, cuisine)
        key = _exact_key(name, cuisine)
        if url:
            by_exact[key] = url
            nk = norm_recipe_name(name)
            by_name[nk] = url
            by_cuisine.setdefault(cuisine, {})[nk] = url
            meta[key] = {"name": name, "cuisine": cuisine, "image_url": url}
        else:
            missed.append(f"{cuisine}: {name}")
        if i % 10 == 0:
            print(f"  {i}/{len(names)}…")
        time.sleep(0.08)

    out = {
        "source": "Smart Pantry strict title match (TheMealDB)",
        "version": 1,
        "by_exact": by_exact,
        "by_name": by_name,
        "by_cuisine": by_cuisine,
        "meta": meta,
    }
    out_path = ROOT / "data" / "datasets" / "dish_images_exact.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} — matched {len(by_exact)}, missed {len(missed)}")
    if missed:
        print("No strict match for:")
        for line in missed[:25]:
            print(" ", line)
        if len(missed) > 25:
            print(f"  … and {len(missed) - 25} more")

    # Patch catalog JSON files
    for cuisine, fname in CATALOG_FILES.items():
        path = _catalog_dir() / fname
        if not path.is_file():
            continue
        rows = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()
            url = by_exact.get(_exact_key(name, cuisine))
            if url and row.get("image_url") != url:
                row["image_url"] = url
                changed = True
        if changed:
            path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
            print("Updated catalog", fname)

    reload_dataset_index()
    from app.services.dish_image_datasets import reassign_all_recipe_images_strict  # noqa: E402

    with SessionLocal() as db:
        stats = reassign_all_recipe_images_strict(db, online=False)
    print("DB reassigned:", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
