from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.models import PantryItem


def load_nutrition_csv(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.is_file():
        return pd.DataFrame()
    return pd.read_csv(p)


def pantry_nutrition_frame(items: list[PantryItem], nutrition_df: pd.DataFrame) -> pd.DataFrame:
    if not items:
        return pd.DataFrame()
    rows = []
    for it in items:
        rows.append(
            {
                "id": it.id,
                "name": it.name,
                "quantity": it.quantity,
                "unit": it.unit,
                "barcode": it.barcode or "",
                "expiration_date": it.expiration_date,
            }
        )
    p_df = pd.DataFrame(rows)
    if nutrition_df.empty or not len(nutrition_df.columns):
        p_df["calories_estimated"] = pd.NA
        return p_df

    n = nutrition_df.copy()
    if "barcode" in n.columns:
        n["barcode"] = n["barcode"].astype(str).str.strip()
    p_df["barcode_key"] = p_df["barcode"].astype(str).str.strip()
    merged = p_df.merge(n, left_on="barcode_key", right_on="barcode", how="left", suffixes=("", "_nut"))

    if "product_name" in n.columns and "calories_100g" in merged.columns and merged["calories_100g"].isna().any():
        p_df["name_key"] = p_df["name"].str.lower().str.strip()
        n["name_key"] = n["product_name"].str.lower().str.strip()
        fill = p_df.merge(n, on="name_key", how="left", suffixes=("", "_name"))
        if "calories_100g" in fill.columns:
            merged["calories_100g"] = merged["calories_100g"].fillna(fill["calories_100g"])

    def est_kcal(row: Any) -> float:
        k = row.get("calories_100g")
        if pd.isna(k):
            return float("nan")
        unit = str(row.get("unit", "")).lower()
        qty = float(row.get("quantity") or 0)
        if unit in ("g", "gram", "grams") and qty:
            return float(k) * qty / 100.0
        if unit in ("ml", "milliliter") and qty:
            return float(k) * qty / 100.0
        return float(k) * max(qty, 1.0) / 10.0

    if "calories_100g" in merged.columns:
        merged["calories_estimated"] = merged.apply(est_kcal, axis=1)
    else:
        merged["calories_estimated"] = pd.NA

    return merged


def total_estimated_calories(merged: pd.DataFrame) -> float:
    if merged.empty or "calories_estimated" not in merged.columns:
        return 0.0
    s = pd.to_numeric(merged["calories_estimated"], errors="coerce")
    return float(s.fillna(0).sum())
