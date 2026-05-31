"""Expand stored recipe text into a detailed, step-by-step method (OpenAI)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings


def expand_recipe_method(
    *,
    name: str,
    cuisine: str,
    prep_minutes: int,
    base_servings: int,
    scaled_servings: int | None,
    ingredient_lines: list[str],
    original_instructions: str,
) -> dict[str, Any]:
    """Return dict with keys steps, prep_checklist, serving_notes. Raises on API/parse errors."""
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    scaled_note = ""
    if scaled_servings is not None and scaled_servings != base_servings:
        scaled_note = (
            f"The cook is scaling the dish to **{scaled_servings} people** "
            f"(original recipe yield was **{base_servings}**). "
            "Adjust batch size, pan choice, and cooking time in the steps accordingly; "
            "do not change ingredient names—only timing/pan/portion cues."
        )

    system = (
        "You are an expert home-cooking instructor. You receive a recipe's metadata, ingredient list, "
        "and often brief or messy source instructions.\n"
        "Write a **clear, safe, ordered method** a confident beginner can follow.\n\n"
        "Requirements:\n"
        "- Output **JSON only** with this shape:\n"
        '  {"steps":["..."],"prep_checklist":["..."],"serving_notes":"..."}\n'
        "- **steps**: 10–28 short strings (prefer more smaller steps over few long ones). "
        "Each step is one main action or closely related actions. Use imperative mood.\n"
        "- Cover **mise en place** first (wash, peel, chop sizes where it matters), then cooking order.\n"
        "- For each cooking phase specify **approximate time**, **heat level** (low/medium/medium-high/high), "
        "and **equipment** (pan type, pot size) when it matters.\n"
        "- Describe **textures and doneness**: color, sizzle, sauce thickness, "
        "when vegetables are crisp-tender, when protein is cooked through, resting meat, etc.\n"
        "- Say **when** to add ingredients relative to the pan state (e.g. after aromatics soften, "
        "before liquid reduces).\n"
        "- Mention **sensory cues** (aroma, bubbling, browning edges) where helpful.\n"
        "- If the source text is vague, infer standard technique for this dish type—stay plausible "
        "and do **not** invent ingredients that are not in the ingredient list.\n"
        "- **prep_checklist**: optional 3–10 bullets of things to gather/do before heat goes on.\n"
        "- **serving_notes**: 1–3 sentences on plating, resting, or common accompaniments.\n"
        "- Keep temperatures in everyday language unless the source used Celsius explicitly.\n"
        "- Food safety: mention cooking poultry/meat until no pink juices / firm, "
        "and reheating leftovers hot throughout when relevant.\n"
    )

    user_payload = {
        "recipe_name": name,
        "cuisine": cuisine,
        "prep_minutes_estimate": prep_minutes,
        "base_servings": base_servings,
        "scaling_note": scaled_note or None,
        "ingredients": ingredient_lines,
        "original_instructions": (original_instructions or "").strip() or None,
    }
    user_msg = json.dumps(user_payload, ensure_ascii=False)

    with httpx.Client(timeout=90.0) as client:
        r = client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.openai_model,
                "temperature": 0.4,
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
    steps = payload.get("steps") or []
    if not isinstance(steps, list):
        steps = []
    cleaned_steps = [str(x).strip() for x in steps if str(x).strip()]
    if len(cleaned_steps) < 4:
        raise ValueError("Model returned too few steps")

    checklist = payload.get("prep_checklist") or []
    if not isinstance(checklist, list):
        checklist = []
    cleaned_check = [str(x).strip() for x in checklist if str(x).strip()]

    notes = payload.get("serving_notes")
    serving = str(notes).strip() if notes is not None else ""

    return {
        "steps": cleaned_steps[:36],
        "prep_checklist": cleaned_check[:16],
        "serving_notes": serving or None,
        "model": settings.openai_model,
    }
