"""Scale recipe ingredient amounts for a different number of servings."""

from __future__ import annotations

from typing import Any


def _fmt_amount(x: float) -> str:
    if abs(x - round(x)) < 1e-6:
        return str(int(round(x)))
    s = f"{x:.3f}".rstrip("0").rstrip(".")
    return s or "0"


def scale_ingredient_list(
    ingredients: list[dict[str, Any]],
    base_servings: int,
    target_servings: int,
) -> list[dict[str, Any]]:
    """Return new ingredient dicts with ``amount`` and ``amount_display`` scaled linearly."""
    base = max(1, int(base_servings or 1))
    target = max(1, int(target_servings or 1))
    if target == base:
        return [
            {
                **ing,
                "amount": float(ing.get("amount") or 0),
                "amount_display": _fmt_amount(float(ing.get("amount") or 0)),
            }
            for ing in ingredients
        ]
    factor = target / base
    out: list[dict[str, Any]] = []
    for ing in ingredients:
        raw = float(ing.get("amount") or 0)
        amt = round(raw * factor + 1e-9, 6)
        row = {**ing, "amount": amt, "amount_display": _fmt_amount(amt)}
        out.append(row)
    return out
