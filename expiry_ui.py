"""Expiry status for pantry rows (color + human-readable time left)."""

from __future__ import annotations

import datetime as dt


def expiry_badge(expiration_date: object | None, today: dt.date | None = None) -> tuple[str, str, str]:
    """Return (css_background, css_border, label_text) for a pantry item."""
    today = today or dt.date.today()
    if not expiration_date:
        return "rgba(184, 212, 168, 0.35)", "rgba(72, 101, 88, 0.45)", "No expiry set"
    try:
        d = dt.date.fromisoformat(str(expiration_date)[:10])
    except ValueError:
        return "rgba(226, 232, 240, 0.9)", "#CBD5E0", "Invalid date"
    days = (d - today).days
    if days < 0:
        return "rgba(254, 178, 178, 0.55)", "#C53030", f"Expired · {abs(days)}d ago"
    if days <= 3:
        return "rgba(251, 211, 189, 0.65)", "#DD6B20", f"Use soon · {days}d left"
    if days <= 7:
        return "rgba(254, 235, 156, 0.7)", "#D69E2E", f"This week · {days}d left"
    return "rgba(184, 212, 168, 0.35)", "rgba(72, 101, 88, 0.45)", f"Fresh · {days}d left"


def expiry_card_html(name: str, qty: float, unit: str, expiration_date: object | None) -> str:
    bg, border, status = expiry_badge(expiration_date)
    return (
        f'<div style="background:{bg};border:1px solid {border};border-radius:12px;'
        f'padding:10px 12px;margin:6px 0;">'
        f"<strong>{name}</strong> · {qty} {unit}<br/>"
        f'<span style="font-size:0.9rem;font-weight:600;">{status}</span></div>'
    )
