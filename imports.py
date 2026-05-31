from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Recipe, User
from app.services.catalog_fill import merge_bundled_catalog_recipes, top_up_catalog_to_minimum
from app.services.kaggle_loader import import_recipes_csv
from app.services.recipe_catalog import themealdb_area_to_catalog_cuisine
from app.services.regional_recipe_import import import_five_cuisine_bundles
from app.services.themealdb import list_areas, meal_detail, meals_by_area, meal_to_recipe_row

router = APIRouter(prefix="/imports", tags=["imports"])


@router.get("/themealdb/areas", response_model=list[str])
def themealdb_areas(user: User = Depends(get_current_user)):
    return list_areas()


class TheMealDBImportBody(BaseModel):
    area: str = Field(..., description="Cuisine / area e.g. Italian, Thai")
    limit: int = Field(15, ge=1, le=500)


class RegionalBundlesBody(BaseModel):
    """Import Kashmiri, Indian, Italian, Chinese, and Middle Eastern buckets from TheMealDB (best-effort)."""

    per_cuisine_cap: int = Field(150, ge=10, le=500, description="Target max new recipes per cuisine (API may return fewer)")


@router.post("/themealdb", response_model=dict)
def import_themealdb(body: TheMealDBImportBody, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    canonical = themealdb_area_to_catalog_cuisine(body.area)
    if not canonical:
        raise HTTPException(
            400,
            "This TheMealDB area is not in the app catalog. Allowed: Italian, Chinese, Indian, "
            "or Middle Eastern (import from Egyptian, Turkish, Lebanese, Moroccan, and similar areas). "
            "Use **Regional recipe import** on Profile for Kashmiri.",
        )
    meals = meals_by_area(body.area)
    if not meals:
        return {"imported": 0, "area": body.area, "catalog_cuisine": canonical, "note": "No meals found for this area."}
    added = 0
    for m in meals[: body.limit]:
        detail = meal_detail(m["idMeal"])
        if not detail:
            continue
        row = meal_to_recipe_row(detail, cuisine_override=canonical)
        nl = str(row["name"]).strip().lower()
        exists = (
            db.query(Recipe.id)
            .filter(func.lower(func.trim(Recipe.name)) == nl, Recipe.cuisine == canonical)
            .first()
        )
        if exists:
            continue
        db.add(Recipe(**row))
        added += 1
    db.commit()
    return {"imported": added, "area": body.area, "catalog_cuisine": canonical}


@router.post("/themealdb/regional-bundles", response_model=dict)
def import_themealdb_regional_bundles(
    body: RegionalBundlesBody,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Pull large catalogs for: Kashmiri, Indian, Italian, Chinese, Middle Eastern (see regional_recipe_import)."""
    stats = import_five_cuisine_bundles(db, body.per_cuisine_cap)
    top_up = top_up_catalog_to_minimum(db)
    merged = merge_bundled_catalog_recipes(db)
    total = sum(int(v) for k, v in stats.items() if isinstance(v, int))
    by_cuisine = {k: v for k, v in stats.items() if k != "note"}
    return {
        "imported_total": total,
        "by_cuisine": by_cuisine,
        "note": stats.get("note"),
        "catalog_top_up": top_up,
        "catalog_merge": merged,
    }


@router.post("/recipes-csv", response_model=dict)
async def import_recipes_csv_upload(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    suffix = Path(file.filename or "recipes.csv").suffix or ".csv"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        path = Path(tmp.name)
    n = 0
    top_up: dict[str, int] = {}
    try:
        n = import_recipes_csv(db, path)
        top_up = top_up_catalog_to_minimum(db)
        merged = merge_bundled_catalog_recipes(db)
    finally:
        path.unlink(missing_ok=True)
    return {"imported": n, "catalog_top_up": top_up, "catalog_merge": merged}


@router.post("/recipes-kaggle-sample", response_model=dict)
def import_recipes_kaggle_sample(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    sample_path = Path(__file__).resolve().parents[5] / "data" / "sample_recipes_kaggle.csv"
    if not sample_path.is_file():
        raise HTTPException(500, "Bundled Kaggle sample dataset is missing.")
    n = import_recipes_csv(db, sample_path)
    top_up = top_up_catalog_to_minimum(db)
    merged = merge_bundled_catalog_recipes(db)
    return {"imported": n, "source": sample_path.name, "catalog_top_up": top_up, "catalog_merge": merged}
