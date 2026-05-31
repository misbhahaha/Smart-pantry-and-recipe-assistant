from __future__ import annotations

MOCK_BARCODE_PRODUCTS: dict[str, dict[str, str | int | float | None]] = {
    "0001234567890": {"name": "Organic Long-Grain Rice", "category": "grains", "default_unit": "g", "suggested_qty": 1000},
    "0085000026514": {"name": "Extra Virgin Olive Oil", "category": "oils", "default_unit": "ml", "suggested_qty": 500},
    "0049000043256": {"name": "Whole Milk", "category": "dairy", "default_unit": "ml", "suggested_qty": 1000},
    "0012345678905": {"name": "Canned Chickpeas", "category": "canned", "default_unit": "g", "suggested_qty": 400},
}


def lookup_barcode(code: str) -> dict[str, str | int | float | None] | None:
    cleaned = "".join(c for c in code if c.isdigit())
    return MOCK_BARCODE_PRODUCTS.get(cleaned)
