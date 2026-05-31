import json
import logging
import os
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Recipe
from app.services.catalog_fill import merge_bundled_catalog_recipes, top_up_catalog_to_minimum
from app.services.kaggle_loader import import_recipes_csv
from app.services.instruction_steps import (
    backfill_structured_steps,
    format_steps_as_instructions,
    rebuild_all_recipe_steps,
)
from app.services.recipe_image_urls import placeholder_image_url

logger = logging.getLogger(__name__)


def seed_if_empty(db: Session) -> int:
    if db.query(Recipe).first():
        return 0
    recipes = [
        Recipe(
            name="Vegetable Stir-Fry",
            cuisine="Chinese",
            instructions=format_steps_as_instructions(
                [
                    "Bring a pot of water to a boil if you are serving rice; cook rice according to package directions.",
                    "Heat oil in a wok over high heat until shimmering.",
                    "Stir-fry garlic and ginger for 30 seconds until fragrant.",
                    "Add vegetables and stir-fry 4–5 minutes until crisp-tender.",
                    "Add soy sauce, toss to coat, finish with sesame oil, and serve over rice.",
                ]
            ),
            prep_minutes=25,
            calories_per_serving=320,
            servings=4,
            ingredients_json=json.dumps(
                [
                    {"name": "Broccoli", "amount": 300, "unit": "g"},
                    {"name": "Bell pepper", "amount": 2, "unit": "each"},
                    {"name": "Soy sauce", "amount": 3, "unit": "tbsp"},
                    {"name": "Garlic", "amount": 3, "unit": "cloves"},
                    {"name": "Olive oil", "amount": 2, "unit": "tbsp"},
                    {"name": "Rice", "amount": 400, "unit": "g cooked"},
                ]
            ),
            diet_tags=json.dumps(["vegetarian", "vegan", "gluten-free", "low-sodium"]),
            health_notes=json.dumps(["diabetes-friendly", "heart-healthy"]),
            image_url=placeholder_image_url(0),
        ),
        Recipe(
            name="Chana Masala",
            cuisine="Indian",
            instructions="Sauté onions and spices, add tomatoes and chickpeas, simmer until thick. Serve with rice or bread.",
            prep_minutes=40,
            calories_per_serving=380,
            servings=4,
            ingredients_json=json.dumps(
                [
                    {"name": "Chickpeas", "amount": 400, "unit": "g canned"},
                    {"name": "Onion", "amount": 1, "unit": "large"},
                    {"name": "Tomato", "amount": 400, "unit": "g"},
                    {"name": "Ginger", "amount": 1, "unit": "tbsp"},
                    {"name": "Rice", "amount": 300, "unit": "g"},
                ]
            ),
            diet_tags=json.dumps(["vegetarian", "vegan", "gluten-free"]),
            health_notes=json.dumps(["diabetes-friendly", "high-fiber"]),
            image_url=placeholder_image_url(1),
        ),
        Recipe(
            name="Greek Salad Bowl",
            cuisine="Middle Eastern",
            instructions="Chop vegetables, combine with olives and feta. Dress with olive oil and lemon.",
            prep_minutes=15,
            calories_per_serving=280,
            servings=2,
            ingredients_json=json.dumps(
                [
                    {"name": "Cucumber", "amount": 1, "unit": "each"},
                    {"name": "Tomato", "amount": 2, "unit": "each"},
                    {"name": "Olive oil", "amount": 2, "unit": "tbsp"},
                    {"name": "Lemon", "amount": 1, "unit": "each"},
                    {"name": "Feta cheese", "amount": 100, "unit": "g"},
                ]
            ),
            diet_tags=json.dumps(["vegetarian", "gluten-free"]),
            health_notes=json.dumps(["heart-healthy", "low-carb"]),
            image_url=placeholder_image_url(2),
        ),
        Recipe(
            name="Chicken Tikka Wrap",
            cuisine="Indian",
            instructions="Marinate chicken in yogurt and spices, grill, wrap with salad and chutney.",
            prep_minutes=45,
            calories_per_serving=520,
            servings=4,
            ingredients_json=json.dumps(
                [
                    {"name": "Chicken breast", "amount": 600, "unit": "g"},
                    {"name": "Yogurt", "amount": 200, "unit": "g"},
                    {"name": "Onion", "amount": 1, "unit": "each"},
                    {"name": "Garlic", "amount": 4, "unit": "cloves"},
                    {"name": "Flour tortilla", "amount": 4, "unit": "each"},
                ]
            ),
            diet_tags=json.dumps(["high-protein"]),
            health_notes=json.dumps([]),
            image_url=placeholder_image_url(3),
        ),
        Recipe(
            name="Miso Soup",
            cuisine="Chinese",
            instructions="Simmer dashi, whisk in miso, add tofu and seaweed.",
            prep_minutes=20,
            calories_per_serving=120,
            servings=2,
            ingredients_json=json.dumps(
                [
                    {"name": "Tofu", "amount": 200, "unit": "g"},
                    {"name": "Miso paste", "amount": 2, "unit": "tbsp"},
                    {"name": "Green onion", "amount": 2, "unit": "stalks"},
                    {"name": "Soy sauce", "amount": 1, "unit": "tsp"},
                ]
            ),
            diet_tags=json.dumps(["vegetarian", "vegan", "low-sodium"]),
            health_notes=json.dumps(["diabetes-friendly"]),
            image_url=placeholder_image_url(4),
        ),
        Recipe(
            name="Pasta Aglio e Olio",
            cuisine="Italian",
            instructions="Cook pasta. Sauté garlic in olive oil, toss with pasta and parsley.",
            prep_minutes=20,
            calories_per_serving=410,
            servings=3,
            ingredients_json=json.dumps(
                [
                    {"name": "Spaghetti", "amount": 300, "unit": "g"},
                    {"name": "Olive oil", "amount": 4, "unit": "tbsp"},
                    {"name": "Garlic", "amount": 6, "unit": "cloves"},
                    {"name": "Parsley", "amount": 0.5, "unit": "cup"},
                ]
            ),
            diet_tags=json.dumps(["vegetarian", "vegan"]),
            health_notes=json.dumps([]),
            image_url=placeholder_image_url(5),
        ),
        Recipe(
            name="Haak Tamatar",
            cuisine="Kashmiri",
            instructions="Simmer greens with tomato and spices until tender. Finish with a little yogurt if you like.",
            prep_minutes=35,
            calories_per_serving=210,
            servings=4,
            ingredients_json=json.dumps(
                [
                    {"name": "Spinach", "amount": 400, "unit": "g"},
                    {"name": "Tomato", "amount": 200, "unit": "g"},
                    {"name": "Oil", "amount": 2, "unit": "tbsp"},
                    {"name": "Cumin", "amount": 1, "unit": "tsp"},
                ]
            ),
            diet_tags=json.dumps(["vegetarian", "vegan", "gluten-free"]),
            health_notes=json.dumps(["high-fiber"]),
            image_url=placeholder_image_url(6),
        ),
    ]
    for r in recipes:
        db.add(r)
    db.commit()
    return len(recipes)


def _recipe_count(db: Session) -> int:
    return int(db.query(Recipe).count())


def ensure_recipe_seed_data(db: Session) -> dict:
    """
    Ensure recipe data exists without requiring user-facing imports.
    - Load bundled Kaggle sample when DB is empty.
    - Optionally bulk-import from TheMealDB for all catalog cuisines (requires network).
    """
    before = _recipe_count(db)
    loaded_from_kaggle = 0
    loaded_from_fallback = 0
    loaded_from_api = 0
    themealdb_bundle: dict[str, int | str] = {}

    if before == 0:
        sample_path = Path(__file__).resolve().parents[3] / "data" / "sample_recipes_kaggle.csv"
        if sample_path.is_file():
            loaded_from_kaggle = import_recipes_csv(db, sample_path)
            logger.info("Loaded %s recipes from bundled Kaggle sample.", loaded_from_kaggle)
        if loaded_from_kaggle == 0:
            loaded_from_fallback = seed_if_empty(db)
            logger.info("Loaded %s fallback recipes.", loaded_from_fallback)

    catalog_top_up: dict[str, int] = {}
    catalog_merge: dict[str, int] = {}
    try:
        catalog_top_up = top_up_catalog_to_minimum(db)
        catalog_merge = merge_bundled_catalog_recipes(db)
    except Exception as exc:
        db.rollback()
        logger.warning("Bundled catalog top-up skipped: %s", exc)

    auto_api = os.environ.get("AUTO_THEMEALDB_ENRICH", "1").strip() == "1"
    if auto_api:
        try:
            from sqlalchemy import func

            from app.services.recipe_catalog import ALLOWED_APP_CUISINES_ORDERED

            rows = (
                db.query(Recipe.cuisine, func.count(Recipe.id))
                .filter(Recipe.cuisine.in_(tuple(ALLOWED_APP_CUISINES_ORDERED)))
                .group_by(Recipe.cuisine)
                .all()
            )
            counts: dict[str, int] = {c: 0 for c in ALLOWED_APP_CUISINES_ORDERED}
            for c, n in rows:
                counts[c] = int(n)
            min_threshold = int(os.environ.get("AUTO_THEMEALDB_MIN_COUNT", "25"))
            force = os.environ.get("FORCE_THEMEALDB_BULK", "").strip().lower() in ("1", "true", "yes")
            need_bulk = force or any(counts[c] < min_threshold for c in ALLOWED_APP_CUISINES_ORDERED)

            if not need_bulk:
                logger.info("Skipping TheMealDB bundle (counts ok or threshold met): %s", counts)
            else:
                from app.services.regional_recipe_import import import_five_cuisine_bundles

                cap = int(os.environ.get("AUTO_THEMEALDB_CATALOG_CAP", "150"))
                cap = max(25, min(cap, 300))
                themealdb_bundle = import_five_cuisine_bundles(db, cap)
                loaded_from_api = sum(int(v) for k, v in themealdb_bundle.items() if k != "note" and isinstance(v, int))
                if loaded_from_api:
                    logger.info("TheMealDB bundle import added %s recipes (per-cuisine cap %s).", loaded_from_api, cap)
        except Exception as exc:
            db.rollback()
            logger.warning("TheMealDB bundle import skipped: %s", exc)

    kashmiri_themealdb = 0
    if os.environ.get("AUTO_KASHMIRI_THEMEALDB", "1").strip() == "1":
        try:
            from sqlalchemy import func

            from app.services.regional_recipe_import import import_kashmiri_themealdb_candidates

            kc = db.query(func.count(Recipe.id)).filter(Recipe.cuisine == "Kashmiri").scalar() or 0
            if kc < 25:
                kashmiri_themealdb = import_kashmiri_themealdb_candidates(db, 18)
                if kashmiri_themealdb:
                    logger.info("Kashmiri keyword TheMealDB import: %s recipes.", kashmiri_themealdb)
        except Exception as exc:
            db.rollback()
            logger.warning("Kashmiri TheMealDB enrichment skipped: %s", exc)

    images_backfilled = 0
    images_search_backfilled = 0
    try:
        from app.services.recipe_dedup import remove_duplicate_recipes_from_db

        dup_removed = remove_duplicate_recipes_from_db(db)
        if dup_removed:
            logger.info("Removed %s duplicate recipe rows.", dup_removed)
    except Exception as exc:
        db.rollback()
        logger.warning("Recipe dedupe skipped: %s", exc)

    if os.environ.get("AUTO_DISH_IMAGE_BACKFILL", "1").strip() == "1":
        try:
            from app.services.dish_image_datasets import (
                backfill_recipe_images,
                fill_missing_recipe_images,
            )

            images_backfilled = backfill_recipe_images(db)
            online = os.environ.get("AUTO_THEMEALDB_IMAGE_SEARCH", "1").strip() == "1"
            images_search_backfilled = fill_missing_recipe_images(db, online=online)
        except Exception as exc:
            db.rollback()
            logger.warning("Dish image dataset backfill skipped: %s", exc)

    steps_backfilled = 0
    try:
        steps_backfilled = backfill_structured_steps(db)
        steps_rebuilt = rebuild_all_recipe_steps(db)
        steps_backfilled += steps_rebuilt
        if steps_backfilled:
            logger.info("Structured steps backfill/rebuild updated %s recipes.", steps_backfilled)
    except Exception as exc:
        db.rollback()
        logger.warning("Structured steps backfill skipped: %s", exc)

    after = _recipe_count(db)
    return {
        "before": before,
        "after": after,
        "kaggle_loaded": loaded_from_kaggle,
        "fallback_loaded": loaded_from_fallback,
        "api_loaded": loaded_from_api,
        "themealdb_bundle": themealdb_bundle,
        "kashmiri_themealdb": kashmiri_themealdb,
        "catalog_top_up": catalog_top_up,
        "catalog_merge": catalog_merge,
        "steps_backfilled": steps_backfilled,
        "images_backfilled": images_backfilled,
        "images_search_backfilled": images_search_backfilled,
    }
