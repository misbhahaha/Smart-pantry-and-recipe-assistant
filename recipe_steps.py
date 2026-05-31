"""Split stored recipe instructions into ordered steps for display."""

from __future__ import annotations

import re

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
    if t.endswith(":") and len(t.split()) <= 5 and len(t) < 48:
        return True
    return False


def is_substantive_step(text: str, *, min_chars: int = _MIN_STEP_CHARS) -> bool:
    t = (text or "").strip()
    if not t or _is_step_label_only(t) or _is_section_header_only(t):
        return False
    letters = re.sub(r"[^a-zA-Z]", "", t)
    return len(letters) >= max(6, min_chars - 4) and len(t) >= min_chars


def _merge_step_chunks(steps: list[str]) -> list[str]:
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


def _default_step_triplet(instructions: str) -> list[str]:
    base = (instructions or "").strip().rstrip(".")
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
    min_steps: int = 3,
    allow_expand: bool = True,
) -> list[str]:
    merged = _merge_step_chunks(steps)
    out = [t for t in merged if is_substantive_step(t)]
    if allow_expand and len(out) < min_steps:
        out = expand_to_clear_steps(instructions or " ".join(out), min_steps=min_steps)
        out = [t for t in out if is_substantive_step(t)]
    if len(out) < 2:
        out = [t for t in _default_step_triplet(instructions) if is_substantive_step(t)]
    return out


def _split_on_step_headers(s: str) -> list[str] | None:
    if not re.search(r"step\s*\d+", s, re.IGNORECASE):
        return None
    chunks = re.split(r"(?:^|\n)\s*step\s*\d+\s*[\):.\-]?\s*", s, flags=re.IGNORECASE)
    cleaned = [c.strip() for c in chunks if c.strip() and not _is_step_label_only(c)]
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


def _instructions_to_raw_steps(instructions: str) -> list[str]:
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
        raw_steps = lines
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
                raw_steps = sent if len(sent) > 1 else [s]

    return raw_steps


def instructions_to_steps(instructions: str) -> list[str]:
    if not instructions or not str(instructions).strip():
        return []
    s = str(instructions).strip()
    return sanitize_steps(_instructions_to_raw_steps(s), instructions=s, allow_expand=False, min_steps=2)


def expand_to_clear_steps(instructions: str, *, min_steps: int = 3) -> list[str]:
    steps = sanitize_steps(
        _instructions_to_raw_steps(instructions or ""),
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
    return sanitize_steps(_default_step_triplet(core), instructions=instructions or "", allow_expand=False, min_steps=min_steps)


def overview_and_steps(instructions: str) -> tuple[str, list[str]]:
    t = (instructions or "").strip()
    if not t:
        return "", []
    if "\n\n" in t:
        head, _, tail = t.partition("\n\n")
        head, tail = head.strip(), tail.strip()
        if head and tail:
            step_list = instructions_to_steps(tail) or ([tail] if tail else [])
            return head, step_list
    return "", instructions_to_steps(t)
