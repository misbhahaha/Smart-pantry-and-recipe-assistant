from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import Recipe, User
from app.schemas.recommendation import RecommendationOut
from app.services.household_utils import get_household_for_user, parse_json_list
from app.services.recipe_catalog import is_app_catalog_cuisine
from app.services.recipe_engine import pantry_normalized_names, recipe_matches_user_filters, score_recipe

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/rules", response_model=list[RecommendationOut])
def recommendations_rules(limit: int = 20, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Classic overlap + substitution scoring (no LLM)."""
    from app.services.ai_recommendations import rules_based_recommendations

    rows = rules_based_recommendations(db, user, [], limit)
    return [RecommendationOut(**r) for r in rows]


@router.get("/ai", response_model=list[RecommendationOut])
def recommendations_ai(limit: int = 12, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Hybrid TF-IDF + pantry match; OpenAI rerank when OPENAI_API_KEY is set."""
    from app.services.ai_recommendations import get_ai_recommendations

    rows = get_ai_recommendations(db, user, limit=limit)
    return [RecommendationOut(**r) for r in rows]


@router.get("/tfidf-debug")
def tfidf_debug(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Raw TF-IDF scores vs pantry (for demos)."""
    from app.models import PantryItem
    from app.services.tfidf_engine import build_recipe_index

    hh = get_household_for_user(db, user)
    if not hh:
        return {"scores": []}
    plist = db.query(PantryItem).filter(PantryItem.household_id == hh.id).all()
    names = [p.name for p in plist]
    pantry_set = pantry_normalized_names(plist)
    dietary = parse_json_list(user.dietary_requirements)
    health = parse_json_list(user.health_conditions)
    cands = [
        r
        for r in db.query(Recipe).all()
        if is_app_catalog_cuisine(r.cuisine) and recipe_matches_user_filters(r, dietary, health)
    ]
    idx = build_recipe_index(cands)
    out = []
    for r, sim in idx.pantry_scores(names)[:20]:
        out.append(
            {
                "recipe_id": r.id,
                "name": r.name,
                "cuisine": r.cuisine,
                "tfidf_similarity": round(sim, 4),
                "ingredient_match": round(score_recipe(r, pantry_set).score, 4),
            }
        )
    return {"scores": out}
