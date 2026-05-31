from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None  # type: ignore

try:
    from pyzbar import pyzbar
except ImportError:
    pyzbar = None  # type: ignore


@dataclass
class BarcodeResult:
    data: str
    type: str


def decode_barcodes(image_bytes: bytes) -> list[BarcodeResult]:
    if cv2 is None or pyzbar is None:
        return []
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return []
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    decoded = pyzbar.decode(gray)
    out: list[BarcodeResult] = []
    for d in decoded:
        try:
            text = d.data.decode("utf-8")
        except Exception:
            text = str(d.data)
        out.append(BarcodeResult(data=text, type=d.type))
    return out


_ocr_reader: Any = None


def easyocr_read_text(image_bytes: bytes) -> list[str]:
    global _ocr_reader
    if cv2 is None:
        return []
    try:
        import easyocr
    except ImportError:
        return []

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return []
    if _ocr_reader is None:
        _ocr_reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    lines = _ocr_reader.readtext(img, detail=0)
    return [str(x).strip() for x in lines if str(x).strip()]


_SKIP_LINE = re.compile(
    r"^(may contain|contains|nutrition|energy|allergen|ingredients?:\s*|store in|best before|batch|"
    r"manufactured|distributed|www\.|http)",
    re.I,
)


def parse_ingredients_from_ocr_lines(lines: list[str]) -> list[dict[str, Any]]:
    """Turn noisy OCR lines into pantry-style rows (name, quantity, unit)."""
    raw: list[str] = []
    for ln in lines:
        if not ln or _SKIP_LINE.match(ln.strip()):
            continue
        for part in re.split(r"[\n;,•·]| {2,}", ln):
            p = part.strip(" \t-–•·")
            if len(p) < 2 or _SKIP_LINE.match(p):
                continue
            raw.append(p)

    qty_first = re.compile(
        r"^\s*(\d+(?:[./]\d+)?)\s*(g|kg|mg|ml|l|cl|tbsp|tsp|cup|cups|oz|lb|lbs|pcs?|pc|each|x|×)\s*[:\-]?\s*(.+)$",
        re.I,
    )
    name_first = re.compile(
        r"^\s*(.+?)\s+(\d+(?:[./]\d+)?)\s*(g|kg|mg|ml|l|cl|tbsp|tsp|cup|cups|oz|lb|each)\s*$",
        re.I,
    )

    def parse_qty(s: str) -> float | None:
        s = s.strip().replace(",", ".")
        if "/" in s and s.count("/") == 1:
            a, _, b = s.partition("/")
            try:
                return float(a) / float(b)
            except (ValueError, ZeroDivisionError):
                return None
        try:
            return float(s)
        except ValueError:
            return None

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for seg in raw:
        name = seg
        qty = 1.0
        unit = "each"
        m = qty_first.match(seg)
        if m:
            q = parse_qty(m.group(1))
            if q is not None:
                qty = q
            unit = m.group(2).lower()
            name = m.group(3).strip()
        else:
            m2 = name_first.match(seg)
            if m2:
                name = m2.group(1).strip()
                q = parse_qty(m2.group(2))
                if q is not None:
                    qty = q
                unit = m2.group(3).lower()
        name = re.sub(r"\s+", " ", name).strip(" ,.;:-")
        if len(name) < 2:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name[:200], "quantity": float(qty), "unit": unit[:32]})
    return out
