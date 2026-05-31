"""Parse and normalize recipe instructions into ordered step lists."""

from __future__ import annotations

import json
import re
from typing import Any

_STEP_LABEL_ONLY = re.compile(r"^step\s*\d+\s*[\):.\-]?\s*$", re.IGNORECASE)
_SECTION_HEADER = re.compile(
    r"^(directions|preparation|instructions?|method|marinade|marinating|sauce|gravy|"
    r"topping|assembly|to serve|serving)\s*:?\s*$",
    re.IGNORECASE,
)
_MIN_STEP_CHARS = 10


def _is_step_label_only(text: str) -> bool:
    return bool(_STEP_LABEL_ONLY.match((text or "").strip()))


def _is_section_header_only(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return True
    if _SECTION_HEADER.match(t):
        return True
    # Short titled lines ending with colon and no real sentence
    if t.endswith(":") and len(t.split()) <= 5 and len(t) < 48:
        return True
    return False


def is_substantive_step(text: str, *, min_chars: int = _MIN_STEP_CHARS) -> bool:
    """True when the step has real cooking instruction text."""
    t = (text or "").strip()
    if not t or _is_step_label_only(t):
        return False
    if _is_section_header_only(t):
        return False
    letters = re.sub(r"[^a-zA-Z]", "", t)
    return len(letters) >= max(6, min_chars - 4) and len(t) >= min_chars


def _merge_step_chunks(steps: list[str]) -> list[str]:
    """Merge section headers into following steps; drop label-only rows."""
    merged: list[str] = []
    pending_header = ""

    for raw in steps:
        t = str(raw or "").strip()
        if not t or _is_step_label_only(t):
            continue
        if _is_section_header_only(t):
            pending_header = f"{pending_header} {t.rstrip(':')}. ".strip() if pending_header else f"{t.rstrip(':')}: "
            continue
        if pending_header:
            t = f"{pending_header}{t[0].lower() + t[1:] if t and t[0].isupper() and len(t) > 1 else t}".strip()
            pending_header = ""
        if t.endswith(":") and len(t.split()) <= 6:
            pending_header = f"{t} "
            continue
        merged.append(t)

    if pending_header and merged:
        merged[0] = f"{pending_header.strip()} {merged[0]}".strip()
    elif pending_header:
        merged.append(pending_header.strip().rstrip(":"))
    return merged


def _default_step_triplet(instructions: str, recipe_name: str) -> list[str]:
    base = (instructions or recipe_name or "").strip().rstrip(".")
    if not base:
        return []
    return [
        "Gather and prep all ingredients (wash, chop, and measure).",
        base,
        "Taste, adjust seasoning, and serve while hot.",
    ]


def sanitize_steps(
    steps: list[str],
    *,
    instructions: str = "",
    recipe_name: str = "",
    min_steps: int = 3,
    allow_expand: bool = True,
) -> list[str]:
    """
    Drop empty/label-only steps, merge section headers into the next step,
    and ensure every step has readable instruction text.
    """
    merged = _merge_step_chunks(steps)
    out = [t for t in merged if is_substantive_step(t)]

    if allow_expand and len(out) < min_steps:
        fallback = expand_to_clear_steps(
            instructions or " ".join(out) or recipe_name,
            min_steps=min_steps,
        )
        out = [s for s in fallback if is_substantive_step(s)]

    if len(out) < 2:
        out = [t for t in _default_step_triplet(instructions, recipe_name) if is_substantive_step(t)]
    return out


def _split_on_step_headers(s: str) -> list[str] | None:
    if not re.search(r"step\s*\d+", s, re.IGNORECASE):
        return None
    chunks = re.split(r"(?:^|\n)\s*step\s*\d+\s*[\):.\-]?\s*", s, flags=re.IGNORECASE)
    cleaned: list[str] = []
    for c in chunks:
        c = c.strip()
        if not c or _is_step_label_only(c):
            continue
        cleaned.append(c)
    return cleaned if len(cleaned) >= 2 else None


def _split_numbered_inline(s: str) -> list[str] | None:
    parts = re.split(r"(?<=\S)(?=\s*\d+\.\s+)", s.strip())
    cleaned = [p.strip() for p in parts if p.strip()]
    if len(cleaned) >= 2:
        return cleaned
    parts2 = re.split(r"(?<=\S)(?=\s*\d+\)\s+)", s.strip())
    cleaned2 = [p.strip() for p in parts2 if p.strip()]
    return cleaned2 if len(cleaned2) >= 2 else None


def _split_sentences(paragraph: str) -> list[str]:
    t = paragraph.strip()
    if not t:
        return []
    raw = re.split(r"(?<=[.!?])\s+(?=\S)", t)
    parts = [x.strip() for x in raw if x.strip()]
    if len(parts) > 1:
        return parts
    if len(t) > 220:
        raw2 = re.split(r"(?:;\s+|\s+and\s+)", t, flags=re.IGNORECASE)
        parts2 = [x.strip() for x in raw2 if x.strip() and len(x.strip()) > 8]
        if len(parts2) > 1:
            return parts2
    return [t]


def _parse_instruction_steps_raw(instructions: str) -> list[str]:
    """Split instructions into step chunks (no merge/sanitize)."""
    if not instructions or not str(instructions).strip():
        return []
    s = str(instructions).strip().replace("\r\n", "\n").replace("\r", "\n")
    raw_steps: list[str] = []

    if re.search(r"(?m)^\s*[-*•]\s+\S", s):
        lines: list[str] = []
        for ln in s.split("\n"):
            ln = ln.strip()
            m = re.match(r"^[-*•]\s+(.*)$", ln)
            if m:
                lines.append(m.group(1).strip())
            elif ln and lines and len(ln) < 80 and not ln[0].isdigit():
                lines[-1] = f"{lines[-1]} {ln}".strip()
            elif ln:
                lines.append(ln)
        raw_steps = [x for x in lines if x]
    elif _split_on_step_headers(s):
        raw_steps = _split_on_step_headers(s) or []
    else:
        lines = [ln.strip() for ln in s.split("\n") if ln.strip()]
        if len(lines) >= 2:
            if sum(1 for ln in lines if re.match(r"^\d+[\).]\s+", ln)) >= max(2, len(lines) // 3):
                raw_steps = [re.sub(r"^\d+[\).]\s+", "", ln).strip() for ln in lines]
            else:
                raw_steps = lines
        elif _split_numbered_inline(s):
            raw_steps = [re.sub(r"^\d+[\).]\s+", "", p).strip() for p in _split_numbered_inline(s) or []]
        else:
            parts = re.split(r"(?<=\S)(?=\s*\d+\.\s+)", s)
            cleaned = [p.strip() for p in parts if p.strip()]
            if len(cleaned) >= 2:
                raw_steps = [re.sub(r"^\d+\.\s+", "", p).strip() for p in cleaned]
            else:
                sent = _split_sentences(s)
                if len(sent) > 1:
                    raw_steps = sent
                elif len(s) > 100 and "," in s:
                    raw_steps = [b.strip() for b in s.split(",") if b.strip() and len(b.strip()) > 6]
                else:
                    raw_steps = [s]

    return raw_steps


def parse_instruction_steps(instructions: str) -> list[str]:
    """Turn free-text or STEP 1 / numbered / bullet instructions into ordered steps."""
    if not instructions or not str(instructions).strip():
        return []
    s = str(instructions).strip()
    return sanitize_steps(
        _parse_instruction_steps_raw(s),
        instructions=s,
        allow_expand=False,
        min_steps=2,
    )


def expand_to_clear_steps(instructions: str, *, min_steps: int = 3) -> list[str]:
    """Ensure at least ``min_steps`` readable steps for short one-line catalog text."""
    steps = sanitize_steps(
        _parse_instruction_steps_raw(instructions or ""),
        instructions=instructions or "",
        allow_expand=False,
        min_steps=2,
    )
    if len(steps) >= min_steps:
        return steps
    if len(steps) == 2:
        return steps
    core = (instructions or "").strip().rstrip(".")
    if not core:
        return steps
    return sanitize_steps(
        _default_step_triplet(core, ""),
        instructions=instructions or "",
        allow_expand=False,
        min_steps=min_steps,
    )


def format_steps_as_instructions(steps: list[str]) -> str:
    """Store steps in a consistent STEP N block (TheMealDB-friendly)."""
    clean = sanitize_steps(steps, min_steps=2, allow_expand=False)
    lines: list[str] = []
    for i, step in enumerate(clean, start=1):
        lines.append(f"STEP {i}\n{step}")
    return "\n\n".join(lines)


def steps_from_dataset_entry(raw: dict[str, Any]) -> list[str]:
    """Optional ``steps`` array in catalog JSON; else parse ``instructions``."""
    text = str(raw.get("instructions") or "").strip()
    name = str(raw.get("name") or "").strip()
    steps_field = raw.get("steps")
    if isinstance(steps_field, list):
        raw_list = [str(x).strip() for x in steps_field if str(x).strip()]
        if len(raw_list) >= 2:
            return sanitize_steps(raw_list, instructions=text, recipe_name=name, min_steps=3)
    if not text:
        return []
    parsed = parse_instruction_steps(text)
    if len(parsed) >= 3:
        return parsed
    return expand_to_clear_steps(text, min_steps=3)


def structured_steps_json_for_row(raw: dict[str, Any]) -> str | None:
    steps = steps_from_dataset_entry(raw)
    if len(steps) < 2:
        return None
    return json.dumps(steps)


def steps_for_recipe(
    instructions: str,
    structured_steps_json: str | None = None,
    *,
    recipe_name: str = "",
) -> list[str]:
    """Best available step list for a DB recipe row."""
    if structured_steps_json and str(structured_steps_json).strip():
        try:
            data = json.loads(structured_steps_json)
            if isinstance(data, list):
                raw = [str(x) for x in data]
                clean = sanitize_steps(raw, instructions=instructions, recipe_name=recipe_name, min_steps=3)
                if len(clean) >= 2:
                    return clean
        except json.JSONDecodeError:
            pass
    steps = expand_to_clear_steps(instructions or "", min_steps=3)
    if len(steps) >= 2:
        return steps
    return sanitize_steps(parse_instruction_steps(instructions or ""), instructions=instructions, recipe_name=recipe_name)


def rebuild_all_recipe_steps(db, *, batch_size: int = 200) -> int:
    """Re-sanitize structured steps for every recipe (fixes empty/label-only steps)."""
    from app.models import Recipe

    updated = 0
    offset = 0
    while True:
        rows = db.query(Recipe).order_by(Recipe.id).offset(offset).limit(batch_size).all()
        if not rows:
            break
        for r in rows:
            steps = steps_for_recipe(r.instructions or "", r.structured_steps_json, recipe_name=r.name)
            if len(steps) < 2:
                continue
            new_json = json.dumps(steps)
            new_instr = format_steps_as_instructions(steps)
            if r.structured_steps_json != new_json or r.instructions != new_instr:
                r.structured_steps_json = new_json
                r.instructions = new_instr
                updated += 1
        db.commit()
        offset += batch_size
    return updated


def backfill_structured_steps(db, *, batch_size: int = 500) -> int:
    """Persist parsed steps for recipes missing ``structured_steps_json``."""
    from app.models import Recipe

    updated = 0
    while True:
        rows = (
            db.query(Recipe)
            .filter(
                (Recipe.structured_steps_json.is_(None))
                | (Recipe.structured_steps_json == "")
            )
            .limit(batch_size)
            .all()
        )
        if not rows:
            break
        for r in rows:
            steps = steps_for_recipe(r.instructions or "", None, recipe_name=r.name)
            if len(steps) < 2:
                continue
            r.structured_steps_json = json.dumps(steps)
            r.instructions = format_steps_as_instructions(steps)
            updated += 1
        db.commit()
    return updated
