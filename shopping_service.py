"""Smart shopping lists: missing ingredients for selected recipes."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Recipe, ShoppingList, ShoppingListItem
from app.services.recipe_engine import pantry_normalized_names, score_recipe
from app.services.recipe_scaling import scale_ingredient_list
from app.services.substitutions import pantry_covers_need


def get_list(db: Session, household_id: int) -> ShoppingList | None:
    """Return the household grocery list if it exists (never creates items)."""
    return (
        db.query(ShoppingList)
        .filter(ShoppingList.household_id == household_id)
        .order_by(ShoppingList.id.desc())
        .first()
    )


def get_or_create_list(db: Session, household_id: int) -> ShoppingList:
    """Create an empty list container only when the user adds something."""
    sl = get_list(db, household_id)
    if sl:
        return sl
    sl = ShoppingList(household_id=household_id, name="Grocery list")
    db.add(sl)
    db.flush()
    return sl


def _item_key(name: str, unit: str) -> tuple[str, str]:
    return name.strip().lower(), (unit or "each").strip().lower()


def dedupe_shopping_list(db: Session, shopping_list: ShoppingList) -> int:
    """Remove duplicate rows (same item name + unit), keeping the earliest row."""
    rows = (
        db.query(ShoppingListItem)
        .filter(ShoppingListItem.shopping_list_id == shopping_list.id)
        .order_by(ShoppingListItem.id)
        .all()
    )
    seen: set[tuple[str, str]] = set()
    removed = 0
    for row in rows:
        key = _item_key(row.item_name, row.unit)
        if key in seen:
            db.delete(row)
            removed += 1
        else:
            seen.add(key)
    if removed:
        db.commit()
    return removed


def clear_all_items(db: Session, shopping_list: ShoppingList) -> int:
    n = (
        db.query(ShoppingListItem)
        .filter(ShoppingListItem.shopping_list_id == shopping_list.id)
        .delete()
    )
    db.commit()
    return int(n)


def add_items_from_recipe(
    db: Session,
    shopping_list: ShoppingList,
    recipe: Recipe,
    pantry_set: set[str],
    *,
    target_servings: int | None = None,
    only_ingredient_names: list[str] | None = None,
) -> int:
    """Add pantry-missing ingredients only when explicitly requested. Returns count added."""
    from app.services.recipe_engine import recipe_ingredient_list

    ingredients = recipe_ingredient_list(recipe)
    base = max(1, int(recipe.servings or 4))
    if target_servings is not None and int(target_servings) != base:
        ingredients = scale_ingredient_list(ingredients, base, int(target_servings))

    sc = score_recipe(recipe, pantry_set)
    if not sc.missing:
        return 0
    to_add = list(sc.missing)
    if only_ingredient_names:
        want = {n.strip().lower() for n in only_ingredient_names if n and str(n).strip()}
        to_add = [ing for ing in to_add if str(ing.get("name", "")).strip().lower() in want]
        if not to_add:
            return 0

    existing = {
        _item_key(it.item_name, it.unit)
        for it in db.query(ShoppingListItem)
        .filter(ShoppingListItem.shopping_list_id == shopping_list.id)
        .all()
    }

    added = 0
    for ing in to_add:
        name = str(ing.get("name", "")).strip()
        if not name:
            continue
        if pantry_covers_need(pantry_set, name):
            continue
        unit = str(ing.get("unit") or "each").strip() or "each"
        key = _item_key(name, unit)
        if key in existing:
            continue
        try:
            qty = float(ing.get("amount") or 1)
        except (TypeError, ValueError):
            qty = 1.0
        db.add(
            ShoppingListItem(
                shopping_list_id=shopping_list.id,
                item_name=name[:200],
                quantity=max(0.01, qty),
                unit=unit[:64],
                source_recipe_id=recipe.id,
            )
        )
        existing.add(key)
        added += 1
    return added


def list_items_with_recipe_names(db: Session, shopping_list: ShoppingList) -> list[dict]:
    rows = (
        db.query(ShoppingListItem)
        .filter(ShoppingListItem.shopping_list_id == shopping_list.id)
        .order_by(ShoppingListItem.is_checked, ShoppingListItem.item_name)
        .all()
    )
    recipe_names: dict[int, str] = {}
    rids = {r.source_recipe_id for r in rows if r.source_recipe_id}
    if rids:
        for rec in db.query(Recipe).filter(Recipe.id.in_(rids)).all():
            recipe_names[rec.id] = rec.name
    out: list[dict] = []
    for it in rows:
        out.append(
            {
                "id": it.id,
                "item_name": it.item_name,
                "quantity": it.quantity,
                "unit": it.unit,
                "is_checked": bool(it.is_checked),
                "source_recipe_id": it.source_recipe_id,
                "source_recipe_name": recipe_names.get(it.source_recipe_id) if it.source_recipe_id else None,
            }
        )
    return out
