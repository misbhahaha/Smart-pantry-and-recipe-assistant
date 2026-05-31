from __future__ import annotations

import csv
import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Recipe
from app.services.instruction_steps import (
    expand_to_clear_steps,
    format_steps_as_instructions,
    parse_instruction_steps,
)
from app.services.recipe_catalog import normalize_cuisine_label
from app.services.recipe_image_urls import ensure_recipe_image_url, placeholder_image_url


def import_recipes_csv(db: Session, path: str | Path) -> int:
    p = Path(path)
    if not p.is_file():
        return 0
    count = 0
    with p.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            cuisine_label = normalize_cuisine_label(row.get("cuisine"))
            if cuisine_label is None:
                continue
            ing_raw = row.get("ingredients") or ""
            ingredients = []
            for part in ing_raw.split(";"):
                part = part.strip()
                if not part:
                    continue
                if ":" in part:
                    n, rest = part.split(":", 1)
                    if ":" in rest:
                        a, u = rest.split(":", 1)
                        try:
                            amt = float(a)
                        except ValueError:
                            amt = 1.0
                        ingredients.append({"name": n.strip(), "amount": amt, "unit": u.strip()})
                    else:
                        try:
                            amt = float(rest)
                        except ValueError:
                            amt = 1.0
                        ingredients.append({"name": n.strip(), "amount": amt, "unit": "each"})
                else:
                    ingredients.append({"name": part, "amount": 1.0, "unit": "each"})
            diet = [x.strip() for x in (row.get("diet_tags") or "").split("|") if x.strip()]
            health = [x.strip() for x in (row.get("health_notes") or "").split("|") if x.strip()]
            raw_img = (row.get("image_url") or "").strip()
            image_url = ensure_recipe_image_url(raw_img) if raw_img else placeholder_image_url(count)
            instr = (row.get("instructions") or "See package.").strip()
            steps = parse_instruction_steps(instr)
            if len(steps) < 3:
                steps = expand_to_clear_steps(instr, min_steps=3)
            if len(steps) >= 3:
                instr = format_steps_as_instructions(steps)
            r = Recipe(
                name=name[:200],
                cuisine=cuisine_label[:80],
                instructions=instr,
                prep_minutes=int(row.get("prep_minutes") or 30),
                calories_per_serving=int(float(row.get("calories_per_serving") or 0)),
                servings=int(float(row.get("servings") or 4)),
                image_url=image_url[:512],
                ingredients_json=json.dumps(ingredients),
                diet_tags=json.dumps(diet),
                health_notes=json.dumps(health),
            )
            if len(steps) >= 2:
                r.structured_steps_json = json.dumps(steps)
            db.add(r)
            count += 1
    db.commit()
    return count
