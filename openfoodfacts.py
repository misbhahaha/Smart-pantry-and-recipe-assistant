from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

OFF_URL = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"


def fetch_product(barcode: str) -> dict[str, Any] | None:
    digits = "".join(c for c in barcode if c.isdigit())
    if len(digits) < 8:
        return None
    url = OFF_URL.format(barcode=digits)
    req = Request(url, headers={"User-Agent": "PantryFlow/1.0 (education)"})
    try:
        with urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None
    if payload.get("status") != 1 or not payload.get("product"):
        return None
    p = payload["product"]
    nutriments = p.get("nutriments") or {}
    kcal = nutriments.get("energy-kcal_100g") or nutriments.get("energy-kcal")
    if kcal is None and nutriments.get("energy-kj_100g"):
        try:
            kcal = float(nutriments["energy-kj_100g"]) / 4.184
        except (TypeError, ValueError):
            kcal = None
    return {
        "barcode": digits,
        "name": p.get("product_name") or p.get("product_name_en") or "Unknown product",
        "brand": p.get("brands", ""),
        "category": (p.get("categories", "") or "").split(",")[0].strip() or "general",
        "calories_per_100g": float(kcal) if kcal is not None else None,
        "nutriments": nutriments,
        "image_url": p.get("image_front_small_url") or p.get("image_url"),
    }
