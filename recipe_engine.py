import json
from dataclasses import dataclass

from app.models import PantryItem, Recipe
from app.services.substitutions import pantry_covers_need


def _norm(s: str) -> str:
    return s.strip().lower()


def recipe_ingredient_list(recipe: Recipe) -> list[dict]:
    try:
        data = json.loads(recipe.ingredients_json)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        pass
    return []


def pantry_normalized_names(items: list[PantryItem]) -> set[str]:
    return {_norm(i.name) for i in items}


def recipe_matches_user_filters(recipe: Recipe, dietary: list[str], health: list[str]) -> bool:
    try:
        diet_tags = set(json.loads(recipe.diet_tags)) if recipe.diet_tags else set()
    except json.JSONDecodeError:
        diet_tags = set()
    try:
        health_notes = set(json.loads(recipe.health_notes)) if recipe.health_notes else set()
    except json.JSONDecodeError:
        health_notes = set()

    for d in dietary:
        if d and d not in diet_tags:
            return False
    for h in health:
        if h and h not in health_notes:
            return False
    return True


@dataclass
class RecipeScore:
    recipe: Recipe
    matched: int
    total: int
    missing: list[dict]

    @property
    def score(self) -> float:
        if self.total <= 0:
            return 0.0
        return self.matched / self.total


def score_recipe(recipe: Recipe, pantry: set[str]) -> RecipeScore:
    ingredients = recipe_ingredient_list(recipe)
    total = len(ingredients)
    matched = 0
    missing: list[dict] = []
    for ing in ingredients:
        name = str(ing.get("name", ""))
        if not name:
            continue
        if pantry_covers_need(pantry, name):
            matched += 1
        else:
            missing.append(ing)
    return RecipeScore(recipe=recipe, matched=matched, total=total, missing=missing)


def missing_for_recipes(recipes: list[Recipe], pantry: set[str]) -> list[tuple[str, dict]]:
    out: list[tuple[str, dict]] = []
    seen: set[str] = set()
    for recipe in recipes:
        sc = score_recipe(recipe, pantry)
        for ing in sc.missing:
            key = _norm(str(ing.get("name", "")))
            if key and key not in seen:
                seen.add(key)
                out.append((recipe.name, ing))
    return out
