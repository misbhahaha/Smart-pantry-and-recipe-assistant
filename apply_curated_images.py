#!/usr/bin/env python3
"""Apply verified curated photos only; clear inaccurate catalog/DB image URLs."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.core.database import SessionLocal, init_db  # noqa: E402
from app.models import Recipe  # noqa: E402
from app.services.dish_image_datasets import (  # noqa: E402
    _catalog_dir,
    _exact_key,
    reload_dataset_index,
    resolve_stored_or_dataset_image,
)

CATALOG_FILES = {
    "Kashmiri": "kashmiri.json",
    "Indian": "indian.json",
    "Italian": "italian.json",
    "Chinese": "chinese.json",
    "Middle Eastern": "middle_eastern.json",
}


def main() -> int:
    curated_path = ROOT / "data" / "datasets" / "curated_dish_images.json"
    curated = json.loads(curated_path.read_text(encoding="utf-8"))
    verified: dict[str, str] = curated.get("by_exact") or {}

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
            key = _exact_key(name, cuisine)
            url = verified.get(key)
            if url:
                if row.get("image_url") != url:
                    row["image_url"] = url
                    changed = True
            elif row.pop("image_url", None) is not None:
                changed = True
        if changed:
            path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
            print("Sanitized catalog", fname)

    init_db()
    reload_dataset_index()
    with SessionLocal() as db:
        cleared = 0
        set_url = 0
        for r in db.query(Recipe).all():
            url = resolve_stored_or_dataset_image(None, name=r.name, cuisine=r.cuisine)
            if url:
                if (r.image_url or "").strip() != url:
                    r.image_url = url[:512]
                    set_url += 1
            elif (r.image_url or "").strip():
                r.image_url = ""
                cleared += 1
        db.commit()
        missing = sum(
            1
            for r in db.query(Recipe).all()
            if not resolve_stored_or_dataset_image(None, name=r.name, cuisine=r.cuisine)
        )
        print(f"Set verified URLs: {set_url}; cleared inaccurate: {cleared}; no photo: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
