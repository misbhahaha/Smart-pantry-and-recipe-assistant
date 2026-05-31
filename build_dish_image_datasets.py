#!/usr/bin/env python3
"""Rebuild bundled dish-image datasets under data/datasets/ (requires network)."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASETS = ROOT / "data" / "datasets"
CATALOG = ROOT / "data" / "catalog"
SAMPLE_CSV = ROOT / "data" / "sample_recipes_kaggle.csv"
BASE = "https://www.themealdb.com/api/json/v1/1"

# TheMealDB area -> catalog cuisine
AREA_CUISINE: list[tuple[str, str]] = [
    ("Chinese", "Chinese"),
    ("Italian", "Italian"),
    ("Indian", "Indian"),
    ("Pakistani", "Indian"),
    ("Bangladeshi", "Indian"),
    ("Moroccan", "Middle Eastern"),
    ("Turkish", "Middle Eastern"),
    ("Greek", "Middle Eastern"),
    ("Egyptian", "Middle Eastern"),
    ("Lebanese", "Middle Eastern"),
    ("Syrian", "Middle Eastern"),
    ("Iranian", "Middle Eastern"),
    ("Iraqi", "Middle Eastern"),
    ("Tunisian", "Middle Eastern"),
    ("British", "Kashmiri"),
    ("Irish", "Kashmiri"),
]

CATALOG_FILES = {
    "Kashmiri": "kashmiri.json",
    "Indian": "indian.json",
    "Italian": "italian.json",
    "Chinese": "chinese.json",
    "Middle Eastern": "middle_eastern.json",
}

_SYNTHETIC_RE = re.compile(r"^pantryflow\s+", re.I)


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=25) as r:
        return json.loads(r.read().decode())


def norm(s: str) -> str:
    return " ".join(str(s).lower().split())


def is_trusted_thumb(url: str) -> bool:
    u = (url or "").strip().lower()
    return u.startswith("https://") and "themealdb.com" in u


def best_in_pool(name: str, pool: dict[str, str], cutoff: float = 0.62) -> str | None:
    key = norm(name)
    if key in pool:
        return pool[key]
    best_url, best_score = None, 0.0
    for k, url in pool.items():
        score = SequenceMatcher(None, key, k).ratio()
        if score > best_score:
            best_score, best_url = score, url
    return best_url if best_score >= cutoff else None


def search_thumb(name: str) -> str | None:
    q = (name or "").strip()
    if len(q) < 2 or _SYNTHETIC_RE.search(q):
        return None
    try:
        data = get(f"{BASE}/search.php?s={urllib.parse.quote(q)}")
    except Exception:
        return None
    meals = data.get("meals") or []
    key = norm(q)
    best_url, best_score = None, 0.0
    for m in meals[:12]:
        if not isinstance(m, dict):
            continue
        meal_name = str(m.get("strMeal") or "").strip()
        thumb = str(m.get("strMealThumb") or "").strip()
        if not meal_name or not is_trusted_thumb(thumb):
            continue
        score = SequenceMatcher(None, key, norm(meal_name)).ratio()
        if score > best_score:
            best_score, best_url = score, thumb
    return best_url if best_score >= 0.52 else None


def build_themealdb() -> dict:
    out = {"source": "TheMealDB", "version": 2, "by_name": {}, "by_cuisine": {}}
    for area, cuisine in AREA_CUISINE:
        try:
            data = get(f"{BASE}/filter.php?a={urllib.parse.quote(area)}")
        except Exception as exc:
            print(f"skip area {area}: {exc}")
            continue
        meals = data.get("meals") or []
        out["by_cuisine"].setdefault(cuisine, {})
        print(f"{area} -> {cuisine}: {len(meals)} meals")
        for m in meals:
            mid = m.get("idMeal")
            if not mid:
                continue
            try:
                detail = get(f"{BASE}/lookup.php?i={mid}")
            except Exception:
                continue
            d = (detail.get("meals") or [None])[0]
            if not d:
                continue
            name = str(d.get("strMeal") or "").strip()
            thumb = (d.get("strMealThumb") or "").strip()
            if not name or not is_trusted_thumb(thumb):
                continue
            key = norm(name)
            out["by_name"][key] = thumb
            out["by_cuisine"][cuisine][key] = thumb
            time.sleep(0.03)
    path = DATASETS / "dish_images_themealdb.json"
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("Wrote", path, "entries", len(out["by_name"]))
    return out


def collect_catalog_names() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for cuisine, fname in CATALOG_FILES.items():
        path = CATALOG / fname
        if not path.is_file():
            continue
        recipes = json.loads(path.read_text(encoding="utf-8"))
        for r in recipes:
            if not isinstance(r, dict):
                continue
            name = str(r.get("name") or "").strip()
            if name and not _SYNTHETIC_RE.search(name):
                rows.append((name, cuisine))
    if SAMPLE_CSV.is_file():
        import csv

        with SAMPLE_CSV.open(encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh):
                name = str(row.get("name") or row.get("Name") or "").strip()
                cuisine = str(row.get("cuisine") or row.get("Cuisine") or "Indian").strip()
                if name and cuisine in CATALOG_FILES and not _SYNTHETIC_RE.search(name):
                    rows.append((name, cuisine))
    return rows


def build_search_index(themealdb: dict, names: list[tuple[str, str]]) -> dict:
    by_name = dict(themealdb.get("by_name") or {})
    by_cuisine = {k: dict(v) for k, v in (themealdb.get("by_cuisine") or {}).items()}
    searched = 0
    for name, cuisine in names:
        key = norm(name)
        if key in by_name:
            continue
        bucket = by_cuisine.get(cuisine, {})
        if key in bucket:
            by_name[key] = bucket[key]
            continue
        url = best_in_pool(name, bucket, cutoff=0.62) or best_in_pool(name, by_name, cutoff=0.62)
        if not url:
            url = search_thumb(name)
            searched += 1
            time.sleep(0.12)
        if url:
            by_name[key] = url
            by_cuisine.setdefault(cuisine, {})[key] = url
    print("TheMealDB searches run:", searched)
    return {"source": "TheMealDB search + catalog", "version": 2, "by_name": by_name, "by_cuisine": by_cuisine}


def build_catalog_map(combined: dict) -> None:
    by_name = combined["by_name"]
    by_cuisine = combined.get("by_cuisine", {})
    catalog = {"source": "Smart Pantry catalog ↔ TheMealDB", "version": 2, "by_name": {}, "by_cuisine": {}}
    updated_files = 0
    for cuisine, fname in CATALOG_FILES.items():
        path = CATALOG / fname
        if not path.is_file():
            continue
        recipes = json.loads(path.read_text(encoding="utf-8"))
        bucket = by_cuisine.get(cuisine, {})
        catalog["by_cuisine"][cuisine] = {}
        changed = False
        for r in recipes:
            if not isinstance(r, dict):
                continue
            name = str(r.get("name") or "").strip()
            if not name:
                continue
            url = (
                best_in_pool(name, bucket, cutoff=0.58)
                or best_in_pool(name, by_name, cutoff=0.58)
                or None
            )
            if url:
                key = norm(name)
                catalog["by_name"][key] = url
                catalog["by_cuisine"][cuisine][key] = url
                if r.get("image_url") != url:
                    r["image_url"] = url
                    changed = True
        if changed:
            path.write_text(json.dumps(recipes, indent=2), encoding="utf-8")
            updated_files += 1
    out_path = DATASETS / "dish_images_catalog.json"
    out_path.write_text(json.dumps(catalog, indent=2), encoding="utf-8")
    print("Wrote", out_path, "entries", len(catalog["by_name"]), "catalog files patched:", updated_files)


def main() -> None:
    DATASETS.mkdir(parents=True, exist_ok=True)
    themealdb = build_themealdb()
    names = collect_catalog_names()
    print("catalog names to map:", len(names))
    combined = build_search_index(themealdb, names)
    (DATASETS / "dish_images_themealdb.json").write_text(
        json.dumps(
            {
                "source": "TheMealDB",
                "version": 2,
                "by_name": combined["by_name"],
                "by_cuisine": combined["by_cuisine"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    build_catalog_map(combined)
    print("total mapped names:", len(combined["by_name"]))


if __name__ == "__main__":
    main()
