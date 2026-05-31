"""AI-assisted recipe ranking — personalized to profile, expiring items, and user notes."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Recipe, User
from app.services.household_utils import get_household_for_user, parse_json_list
from app.services.recipe_catalog import is_app_catalog_cuisine
from app.services.recipe_engine import (
    pantry_normalized_names,
    recipe_ingredient_list,
    recipe_matches_user_filters,
    score_recipe,
)
from app.services.dish_image_datasets import resolve_stored_or_dataset_image
from app.services.recipe_dedup import dedupe_recipe_dicts
from app.services.tfidf_engine import build_recipe_index


def _ingredient_line(r: Recipe) -> str:
    parts = [str(x.get("name", "")) for x in recipe_ingredient_list(r)]
    return ", ".join(parts[:25])


def _expiring_summary(plist: list, within_days: int = 7) -> str:
    today = dt.date.today()
    lines: list[str] = []
    for p in plist:
        if not p.expiration_date:
            continue
        d = (p.expiration_date - today).days
        if d < 0:
            lines.append(f"{p.name} (expired)")
        elif d <= within_days:
            lines.append(f"{p.name} ({d}d left)")
    return "; ".join(lines[:25]) if lines else "none"


def _favorite_cuisines(user: User) -> list[str]:
    return parse_json_list(getattr(user, "favorite_cuisines", None) or "[]")


def _cuisine_boost(recipe: Recipe, favorites: list[str]) -> float:
    if not favorites:
        return 1.0
    c = (recipe.cuisine or "").strip().lower()
    for f in favorites:
        if f.strip().lower() == c:
            return 1.15
    return 1.0


def _parse_diet_tags(recipe: Recipe) -> list[str]:
    try:
        data = json.loads(recipe.diet_tags) if recipe.diet_tags else []
        return [str(x) for x in data] if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _recommendation_dict(
    recipe: Recipe,
    *,
    match_sc: float,
    reason: str,
    ai_score: float | None,
    model: str,
) -> dict[str, Any]:
    return {
        "recipe_id": recipe.id,
        "name": recipe.name,
        "cuisine": recipe.cuisine,
        "image_url": resolve_stored_or_dataset_image(
            getattr(recipe, "image_url", None),
            name=recipe.name,
            cuisine=recipe.cuisine,
        ),
        "ingredient_match_score": round(float(match_sc), 4),
        "ai_score": ai_score,
        "reason": reason[:650],
        "model": model,
        "diet_tags": _parse_diet_tags(recipe),
    }


def _prioritize_kashmiri_first_tuple(rows: list[tuple[float, float, Recipe]]) -> list[tuple[float, float, Recipe]]:
    """Move the highest-ranked Kashmiri row to the front when present (app flagship cuisine)."""
    pos = next(
        (i for i, t in enumerate(rows) if (t[2].cuisine or "").strip().lower() == "kashmiri"),
        None,
    )
    if pos in (None, 0):
        return rows
    t = rows[pos]
    return [t] + [rows[i] for i in range(len(rows)) if i != pos]


def _prioritize_kashmiri_first_scored(scored: list[tuple[float, Recipe]]) -> list[tuple[float, Recipe]]:
    pos = next(
        (i for i, t in enumerate(scored) if (t[1].cuisine or "").strip().lower() == "kashmiri"),
        None,
    )
    if pos in (None, 0):
        return scored
    t = scored[pos]
    return [t] + [scored[i] for i in range(len(scored)) if i != pos]


def _user_persona_block(user: User, plist: list) -> dict[str, Any]:
    dietary = parse_json_list(user.dietary_requirements)
    health = parse_json_list(user.health_conditions)
    fav_c = _favorite_cuisines(user)
    prefs = (getattr(user, "ai_preferences", None) or "").strip()
    target = user.daily_calorie_target
    exp = _expiring_summary(plist, 7)
    return {
        "name": user.full_name,
        "dietary_tags_recipes_must_satisfy": dietary,
        "health_focus_tags_recipes_must_satisfy": health,
        "favorite_cuisines_boost_these": fav_c,
        "daily_calorie_target": target,
        "personal_notes_for_cooking_style": prefs or "none",
        "pantry_items_expiring_soon_priority": exp,
    }


def _build_rule_reason(
    r: Recipe,
    match_sc: float,
    pantry_set: set[str],
    user: User,
    *,
    prefs: str,
    expiring: str,
    fav_lower: set[str],
) -> str:
    miss = score_recipe(r, pantry_set).missing
    miss_s = ", ".join(str(m.get("name")) for m in miss[:6])
    reason = f"You already cover about {match_sc * 100:.0f}% of ingredients."
    if miss_s:
        reason += f" Still need: {miss_s}."
    if expiring and expiring != "none":
        reason += f" Tip: use soon — {expiring[:120]}."
    if prefs:
        reason += " Your personal notes were considered."
    if fav_lower and r.cuisine and r.cuisine.strip().lower() in fav_lower:
        reason += f" Boosted: **{r.cuisine}** matches your favorite cuisines."
    if user.daily_calorie_target:
        kcal = r.calories_per_serving or 0
        if kcal and kcal > user.daily_calorie_target // 2:
            reason += f" Note: ~{kcal} kcal/serving vs your {user.daily_calorie_target} kcal/day target."
    return reason


def _rules_ranked_rows(db: Session, user: User) -> list[tuple[float, float, Recipe]]:
    hh = get_household_for_user(db, user)
    if not hh:
        return []
    from app.models import PantryItem

    plist = db.query(PantryItem).filter(PantryItem.household_id == hh.id).all()
    pantry_set = pantry_normalized_names(plist)
    dietary = parse_json_list(user.dietary_requirements)
    health = parse_json_list(user.health_conditions)
    fav_c = _favorite_cuisines(user)
    fav_lower = {x.strip().lower() for x in fav_c if x.strip()}
    rows: list[tuple[float, float, Recipe]] = []
    for r in db.query(Recipe).all():
        if not is_app_catalog_cuisine(r.cuisine):
            continue
        if not recipe_matches_user_filters(r, dietary, health):
            continue
        scr = score_recipe(r, pantry_set)
        if scr.total <= 0:
            continue
        match_sc = scr.score
        boosted = min(1.0, match_sc * _cuisine_boost(r, fav_c))
        rows.append((boosted, match_sc, r))
    rows.sort(key=lambda x: (-x[0], x[2].name))
    return _prioritize_kashmiri_first_tuple(rows)


def rules_based_recommendations(
    db: Session,
    user: User,
    pantry_names: list[str],
    limit: int,
) -> list[dict[str, Any]]:
    del pantry_names  # pantry is read from DB (kept for call-site compatibility)
    rows = _rules_ranked_rows(db, user)
    if not rows:
        return []
    from app.models import PantryItem

    hh = get_household_for_user(db, user)
    if not hh:
        return []
    plist = db.query(PantryItem).filter(PantryItem.household_id == hh.id).all()
    pantry_set = pantry_normalized_names(plist)
    prefs = (getattr(user, "ai_preferences", None) or "").strip()
    expiring = _expiring_summary(plist, 5)
    fav_c = _favorite_cuisines(user)
    fav_lower = {x.strip().lower() for x in fav_c if x.strip()}

    out: list[dict[str, Any]] = []
    for _boosted, match_sc, r in rows[:limit]:
        reason = _build_rule_reason(r, match_sc, pantry_set, user, prefs=prefs, expiring=expiring, fav_lower=fav_lower)
        out.append(
            _recommendation_dict(
                r,
                match_sc=match_sc,
                reason=reason,
                ai_score=None,
                model="rules+substitutions+profile",
            )
        )
    return dedupe_recipe_dicts(out)


def _inject_kashmiri_if_missing(
    out: list[dict[str, Any]],
    scored: list[tuple[float, Recipe]],
    pantry_set: set[str],
    dietary: list[str],
    health: list[str],
    limit: int,
    *,
    model_label: str,
) -> list[dict[str, Any]]:
    if any((x.get("cuisine") or "").strip().lower() == "kashmiri" for x in out):
        return out
    chosen: Recipe | None = None
    for _, r in scored:
        if (r.cuisine or "").strip().lower() != "kashmiri":
            continue
        if not recipe_matches_user_filters(r, dietary, health):
            continue
        sr = score_recipe(r, pantry_set)
        if sr.total <= 0:
            continue
        chosen = r
        break
    if chosen is None:
        return out
    existing = {int(x["recipe_id"]) for x in out}
    if chosen.id in existing:
        return out
    match_sc = score_recipe(chosen, pantry_set).score
    row = _recommendation_dict(
        chosen,
        match_sc=match_sc,
        reason="Kashmiri cuisine spotlight — a signature of this app. Open for full details and pantry fit.",
        ai_score=None,
        model=model_label,
    )
    merged = [row] + out
    return merged[:limit]


def get_ai_recommendations(db: Session, user: User, limit: int = 12) -> list[dict[str, Any]]:
    hh = get_household_for_user(db, user)
    if not hh:
        return []
    from app.models import PantryItem

    plist = db.query(PantryItem).filter(PantryItem.household_id == hh.id).all()
    pantry_names = [p.name for p in plist]
    pantry_set = pantry_normalized_names(plist)
    dietary = parse_json_list(user.dietary_requirements)
    health = parse_json_list(user.health_conditions)
    persona = _user_persona_block(user, plist)

    candidates: list[Recipe] = []
    for r in db.query(Recipe).all():
        if not is_app_catalog_cuisine(r.cuisine):
            continue
        if not recipe_matches_user_filters(r, dietary, health):
            continue
        if score_recipe(r, pantry_set).total <= 0:
            continue
        candidates.append(r)

    if not candidates:
        return []

    idx = build_recipe_index(candidates)
    tfidf_rank = {r.id: sim for r, sim in idx.pantry_scores(pantry_names)}

    fav_c = _favorite_cuisines(user)
    scored: list[tuple[float, Recipe]] = []
    for r in candidates:
        sc = score_recipe(r, pantry_set).score
        tf = tfidf_rank.get(r.id, 0.0)
        combined = (0.65 * sc + 0.35 * min(tf, 1.0)) * _cuisine_boost(r, fav_c)
        combined = min(1.25, combined)
        scored.append((combined, r))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    scored = _prioritize_kashmiri_first_scored(scored)
    pool = [r for _, r in scored[:35]]

    if not settings.openai_api_key:
        return rules_based_recommendations(db, user, pantry_names, limit)

    brief = [
        {
            "recipe_id": r.id,
            "name": r.name,
            "cuisine": r.cuisine,
            "ingredients": _ingredient_line(r),
            "match": round(score_recipe(r, pantry_set).score, 3),
            "tfidf": round(tfidf_rank.get(r.id, 0.0), 3),
            "calories_per_serving": r.calories_per_serving,
            "prep_minutes": r.prep_minutes,
        }
        for r in pool
    ]
    pantry_blob = ", ".join(pantry_names[:80])

    system = (
        "You are a professional home-cooking assistant. Personalize recipe rankings for THIS user only.\n"
        "Rules:\n"
        "- Only rank recipes from the candidate list (by recipe_id). Never invent recipes.\n"
        "- Strongly prefer recipes that use ingredients listed under expiring_soon.\n"
        "- Respect dietary_tags and health_tags — candidates are pre-filtered but you should still prefer the best fit.\n"
        "- If daily_calorie_target is set, slightly prefer recipes whose calories_per_serving align with a sensible meal.\n"
        "- Boost rankings for favorite_cuisines when all else is similar.\n"
        "- **When any Kashmiri recipe appears in candidates, include at least one Kashmiri recipe in your ranked list** "
        "(unless the user profile explicitly forbids every Kashmiri dish, which should not happen here).\n"
        "- Incorporate personal_notes (tastes, time limits, dislikes) when comparing candidates.\n"
        "- Respond with JSON only: {\"items\":[{\"recipe_id\":number,\"score\":0-1,\"reason\":\"1-2 sentences, friendly\"}]}\n"
        f"- Return at most {limit} items, best first."
    )
    user_msg = json.dumps(
        {
            "user_profile": persona,
            "pantry_all": pantry_blob,
            "candidates": brief,
        }
    )

    try:
        with httpx.Client(timeout=60.0) as client:
            r = client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_model,
                    "temperature": 0.35,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_msg},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"]
            payload = json.loads(content)
    except Exception:
        return rules_based_recommendations(db, user, pantry_names, limit)

    items = payload.get("items") or payload.get("recommendations") or []
    if not isinstance(items, list):
        return rules_based_recommendations(db, user, pantry_names, limit)

    by_id = {x.id: x for x in pool}
    out: list[dict[str, Any]] = []
    for row in items[:limit]:
        try:
            rid = int(row.get("recipe_id"))
        except (TypeError, ValueError):
            continue
        rec = by_id.get(rid)
        if not rec:
            continue
        base_match = score_recipe(rec, pantry_set).score
        try:
            ai_sc = float(row.get("score", 0))
        except (TypeError, ValueError):
            ai_sc = 0.0
        out.append(
            _recommendation_dict(
                rec,
                match_sc=base_match,
                reason=str(row.get("reason", "")),
                ai_score=round(ai_sc, 4),
                model=settings.openai_model,
            )
        )
    if not out:
        return rules_based_recommendations(db, user, pantry_names, limit)
    out = _inject_kashmiri_if_missing(
        out,
        scored,
        pantry_set,
        dietary,
        health,
        limit,
        model_label="catalog-kashmiri-boost",
    )
    return dedupe_recipe_dicts(out)
