import json
import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models import Recipe, User
from app.schemas.recipe import CookingGuideStepOut, RecipeDetailOut, RecipeOut
from app.services.household_utils import get_household_for_user
from app.services.recipe_catalog import (
    ALLOWED_APP_CUISINES,
    ALLOWED_APP_CUISINES_ORDERED,
    MIN_RECIPES_PER_CUISINE,
    is_app_catalog_cuisine,
)
from app.services.recipe_engine import pantry_normalized_names, recipe_ingredient_list, score_recipe
from app.services.dish_image_datasets import (
    backfill_recipe_images,
    backfill_recipe_images_online,
    dataset_stats,
    resolve_stored_or_dataset_image,
)
from app.services.recipe_scaling import scale_ingredient_list
from app.services.instruction_steps import steps_for_recipe
from app.services.recipe_dedup import dedupe_recipe_orm
from app.services.spoonacular_recipes import fetch_cooking_guide_by_spoonacular_id, fetch_structured_steps
from app.services.substitutions import SUBSTITUTION_GROUPS, substitution_hint

router = APIRouter(prefix="/recipes", tags=["recipes"])


def _recipe_out_row(r: Recipe, *, resolve_images: bool = False) -> RecipeOut:
    """Build API row with safe defaults (cloud DB rows may have nulls).

    List endpoints skip per-row image lookup for speed; detail views resolve images.
    """
    image_url = (getattr(r, "image_url", None) or "") or ""
    if resolve_images:
        try:
            image_url = resolve_stored_or_dataset_image(
                getattr(r, "image_url", None),
                name=r.name or "",
                cuisine=r.cuisine,
            ) or image_url
        except Exception:
            pass
    return RecipeOut(
        id=int(r.id),
        name=(r.name or "").strip() or "Untitled",
        cuisine=(r.cuisine or "").strip() or "Unknown",
        prep_minutes=int(r.prep_minutes) if r.prep_minutes is not None else 30,
        calories_per_serving=int(r.calories_per_serving) if r.calories_per_serving is not None else 0,
        servings=int(r.servings) if r.servings is not None else 4,
        image_url=image_url or "",
    )


def _query_catalog_recipes(
    db: Session,
    *,
    cuisine: Optional[str],
    q: Optional[str],
) -> list[Recipe]:
    query = db.query(Recipe).filter(Recipe.cuisine.in_(ALLOWED_APP_CUISINES))
    if cuisine:
        query = query.filter(Recipe.cuisine == cuisine)
    if q and q.strip():
        query = query.filter(Recipe.name.ilike(f"%{q.strip()}%"))
    return query.order_by(Recipe.cuisine, Recipe.name, Recipe.id).all()


def _ensure_catalog_seeded(db: Session) -> None:
    """On fresh Render SQLite, background seed may not have finished yet."""
    from app.services.catalog_fill import merge_bundled_catalog_recipes, top_up_catalog_to_minimum

    try:
        merge_bundled_catalog_recipes(db)
        top_up_catalog_to_minimum(db)
    except Exception:
        logger.exception("Inline catalog seed failed")
        db.rollback()


@router.get("", response_model=List[RecipeOut])
def list_recipes(
    cuisine: Optional[str] = None,
    q: Optional[str] = Query(None, description="Search recipe name (substring, case-insensitive)"),
    limit: int = Query(2000, ge=1, le=5000, description="Maximum recipes to return after filters"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if cuisine and cuisine not in ALLOWED_APP_CUISINES:
        raise HTTPException(
            400,
            "Unknown cuisine; use Kashmiri, Indian, Italian, Chinese, or Middle Eastern.",
        )
    rows = _query_catalog_recipes(db, cuisine=cuisine, q=q)
    if not rows:
        _ensure_catalog_seeded(db)
        rows = _query_catalog_recipes(db, cuisine=cuisine, q=q)
    deduped = dedupe_recipe_orm(rows)
    cap = min(max(1, limit), 5000)
    out: list[RecipeOut] = []
    for r in deduped[:cap]:
        try:
            out.append(_recipe_out_row(r))
        except Exception:
            logger.exception("Skipping recipe id=%s during list serialization", getattr(r, "id", None))
    return out


@router.get("/cuisines", response_model=List[str])
def list_cuisines(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(ALLOWED_APP_CUISINES_ORDERED)


@router.get("/substitutions")
def list_substitution_groups(user: User = Depends(get_current_user)):
    """Ingredient swap groups for flexible cooking (cuisine-based discovery support)."""
    return {
        "groups": [sorted(g) for g in SUBSTITUTION_GROUPS],
    }


@router.post("/images/backfill")
def backfill_recipe_images_endpoint(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    online_search: bool = Query(True, description="Use TheMealDB search for remaining titles"),
    search_cap: int = Query(50, ge=0, le=120),
):
    """Apply bundled dish-photo datasets and optional TheMealDB search to recipe rows."""
    from app.services.recipe_image_urls import is_trusted_dish_image_url

    before = db.query(Recipe).filter(Recipe.cuisine.in_(ALLOWED_APP_CUISINES)).count()
    with_trusted = 0
    for r in db.query(Recipe).filter(Recipe.cuisine.in_(ALLOWED_APP_CUISINES)).all():
        if is_trusted_dish_image_url(r.image_url):
            with_trusted += 1
    dataset_n = backfill_recipe_images(db)
    search_n = 0
    if online_search and search_cap > 0:
        search_n = backfill_recipe_images_online(db, limit=search_cap)
    after = 0
    for r in db.query(Recipe).filter(Recipe.cuisine.in_(ALLOWED_APP_CUISINES)).all():
        if is_trusted_dish_image_url(
            resolve_stored_or_dataset_image(r.image_url, name=r.name, cuisine=r.cuisine)
        ):
            after += 1
    return {
        "recipes": before,
        "with_trusted_images_before": with_trusted,
        "dataset_backfill": dataset_n,
        "search_backfill": search_n,
        "with_trusted_images_after": after,
        "dataset_index": dataset_stats(),
    }


@router.get("/catalog-health")
def recipe_catalog_health(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Recipe counts per catalog cuisine (target: MIN_RECIPES_PER_CUISINE each)."""
    rows = (
        db.query(Recipe.cuisine, func.count(Recipe.id))
        .filter(Recipe.cuisine.in_(ALLOWED_APP_CUISINES))
        .group_by(Recipe.cuisine)
        .all()
    )
    counts: dict[str, int] = {c: 0 for c in ALLOWED_APP_CUISINES_ORDERED}
    for c, n in rows:
        if c in counts:
            counts[c] = int(n)
    min_per = MIN_RECIPES_PER_CUISINE
    below = [c for c in ALLOWED_APP_CUISINES_ORDERED if counts[c] < min_per]
    return {"counts": counts, "min_per_cuisine": min_per, "below_target": below}


def _structured_steps_from_db(recipe: Recipe) -> Optional[List[str]]:
    steps = steps_for_recipe(
        recipe.instructions or "",
        getattr(recipe, "structured_steps_json", None),
        recipe_name=recipe.name,
    )
    return steps if len(steps) >= 2 else None


def _cooking_guide_from_db(recipe: Recipe) -> Optional[List[dict[str, Any]]]:
    raw = getattr(recipe, "spoonacular_guide_json", None) or ""
    if not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    out = [x for x in data if isinstance(x, dict)]
    return out if out else None


def _persist_spoonacular_cache(
    db: Session,
    recipe: Recipe,
    plain: list[str],
    rich: list[dict],
    sid: Optional[int],
    dish_image_url: Optional[str] = None,
) -> None:
    recipe.structured_steps_json = json.dumps(plain)
    recipe.spoonacular_guide_json = json.dumps(rich)
    if sid is not None:
        recipe.spoonacular_recipe_id = sid
    img = (dish_image_url or "").strip()
    if img.startswith("http"):
        recipe.image_url = img
    try:
        db.add(recipe)
        db.commit()
        db.refresh(recipe)
    except Exception:
        db.rollback()


def _ensure_spoonacular_cooking_data(
    db: Session, recipe: Recipe
) -> tuple[Optional[List[str]], Optional[List[dict[str, Any]]]]:
    """Return (plain steps, rich per-step guide) from cache or Spoonacular API."""
    steps = _structured_steps_from_db(recipe)
    guide = _cooking_guide_from_db(recipe)
    sid = getattr(recipe, "spoonacular_recipe_id", None)
    sid_i = int(sid) if sid is not None else 0

    if steps and len(steps) >= 3:
        if sid_i > 0 and (not guide or len(guide) != len(steps)):
            pl, rg, dish = fetch_cooking_guide_by_spoonacular_id(sid_i)
            if pl and rg and len(pl) >= 3 and len(pl) == len(rg):
                _persist_spoonacular_cache(db, recipe, pl, rg, sid_i, dish)
                return pl, rg
        if guide and len(guide) == len(steps):
            return steps, guide
        return steps, None

    if not (settings.spoonacular_api_key or "").strip():
        return steps, guide

    pl, rg, new_sid, dish_img = fetch_structured_steps(recipe_name=recipe.name, cuisine=recipe.cuisine)
    if not pl or not rg or len(pl) < 3 or len(pl) != len(rg):
        return steps, guide
    _persist_spoonacular_cache(db, recipe, pl, rg, int(new_sid) if new_sid else None, dish_img)
    return pl, rg


@router.get("/{recipe_id}/pantry-match")
def pantry_match(recipe_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    r = db.get(Recipe, recipe_id)
    if not r:
        raise HTTPException(404, "Recipe not found")
    if not is_app_catalog_cuisine(r.cuisine):
        raise HTTPException(404, "Recipe not in app catalog")
    hh = get_household_for_user(db, user)
    pantry = set()
    if hh:
        from app.models import PantryItem

        pantry = pantry_normalized_names(db.query(PantryItem).filter(PantryItem.household_id == hh.id).all())
    sc = score_recipe(r, pantry)
    ingredients = recipe_ingredient_list(r)
    subs = {str(ing.get("name", "")): substitution_hint(str(ing.get("name", ""))) for ing in ingredients}
    return {
        "match_ratio": sc.score,
        "matched": sc.matched,
        "total": sc.total,
        "missing": sc.missing,
        "substitution_hints": subs,
    }


@router.get("/{recipe_id}", response_model=RecipeDetailOut)
def get_recipe(
    recipe_id: int,
    servings: Optional[int] = Query(
        None,
        ge=1,
        le=99,
        description="Scale ingredient amounts to this many people (recipe keeps original yield metadata).",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = db.get(Recipe, recipe_id)
    if not r:
        raise HTTPException(404, "Recipe not found")
    if not is_app_catalog_cuisine(r.cuisine):
        raise HTTPException(404, "Recipe not in app catalog")
    ingredients = recipe_ingredient_list(r)
    try:
        diet_tags = json.loads(r.diet_tags) if r.diet_tags else []
    except json.JSONDecodeError:
        diet_tags = []
    try:
        health_notes = json.loads(r.health_notes) if r.health_notes else []
    except json.JSONDecodeError:
        health_notes = []
    base_serv = max(1, int(r.servings or 1))
    scaled: Optional[List[dict]] = None
    scaled_to: int | None = None
    if servings is not None:
        scaled = scale_ingredient_list(ingredients, base_serv, int(servings))
        scaled_to = int(servings)
    structured, guide_raw = _ensure_spoonacular_cooking_data(db, r)
    step_source: Optional[str] = None
    if structured and len(structured) >= 2:
        step_source = "spoonacular"
    else:
        catalog_steps = _structured_steps_from_db(r)
        if catalog_steps and len(catalog_steps) >= 2:
            structured = catalog_steps
            step_source = "catalog"
    guide_out: Optional[List[CookingGuideStepOut]] = None
    if guide_raw:
        guide_out = []
        plain_fallback = structured or []
        for idx, row in enumerate(guide_raw):
            try:
                inst = str(row.get("instruction") or "").strip()
                if not inst and idx < len(plain_fallback):
                    inst = str(plain_fallback[idx]).strip()
                if not inst:
                    continue
                guide_out.append(
                    CookingGuideStepOut(
                        number=int(row.get("number") or 0) or (idx + 1),
                        instruction=inst,
                        ingredients=[str(x) for x in (row.get("ingredients") or []) if str(x).strip()],
                        equipment=[str(x) for x in (row.get("equipment") or []) if str(x).strip()],
                    )
                )
            except (TypeError, ValueError):
                continue
        if not guide_out:
            guide_out = None
    return RecipeDetailOut(
        id=r.id,
        name=r.name,
        cuisine=r.cuisine,
        prep_minutes=r.prep_minutes,
        calories_per_serving=r.calories_per_serving,
        servings=r.servings,
        image_url=resolve_stored_or_dataset_image(
            getattr(r, "image_url", None),
            name=r.name,
            cuisine=r.cuisine,
        ),
        instructions=r.instructions,
        ingredients=ingredients,
        diet_tags=diet_tags if isinstance(diet_tags, list) else [],
        health_notes=health_notes if isinstance(health_notes, list) else [],
        ingredients_scaled=scaled,
        scaled_to_servings=scaled_to,
        structured_steps=structured if structured and len(structured) >= 2 else None,
        step_source=step_source,
        cooking_guide_steps=guide_out,
    )
