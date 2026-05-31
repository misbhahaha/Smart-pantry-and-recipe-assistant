"""Render recipe method steps with clear visual breaks between each step."""

from __future__ import annotations

import html

import streamlit as st

from lib.recipe_steps import expand_to_clear_steps, instructions_to_steps, is_substantive_step, sanitize_steps


def inject_recipe_step_css() -> None:
    if st.session_state.get("_pf_recipe_step_css"):
        return
    st.markdown(
        """
        <style>
        .pf-recipe-step {
          margin: 0.5rem 0 0.25rem 0;
          padding: 0.9rem 1.05rem;
          background: #f8fafc;
          border-radius: 12px;
          border-left: 4px solid #4a6b7c;
        }
        .pf-recipe-step-num {
          font-size: 0.95rem;
          font-weight: 800;
          color: #2d3748;
          margin-bottom: 0.35rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state["_pf_recipe_step_css"] = True


def render_plain_steps(steps: list[str], *, key_prefix: str = "") -> None:
    """One card per step with a divider between steps."""
    inject_recipe_step_css()
    clean = sanitize_steps([str(s) for s in steps], min_steps=2)
    clean = [s for s in clean if is_substantive_step(s)]
    if not clean:
        st.warning("No step-by-step instructions are available for this recipe yet.")
        return
    for i, step in enumerate(clean, start=1):
        st.markdown(
            f'<div class="pf-recipe-step">'
            f'<div class="pf-recipe-step-num">Step {i}</div>'
            f"{html.escape(step)}</div>",
            unsafe_allow_html=True,
        )
        if i < len(clean):
            st.divider()


def render_guide_steps(guide_rows: list, *, key_prefix: str = "") -> None:
    """Spoonacular guide rows: instruction + optional ingredient/equipment captions."""
    inject_recipe_step_css()
    blocks: list[tuple[int, str, list, list]] = []
    for row in guide_rows:
        if not isinstance(row, dict):
            continue
        inst = str(row.get("instruction") or "").strip()
        if not inst or not is_substantive_step(inst):
            continue
        num = int(row.get("number") or 0) or len(blocks) + 1
        ings = row.get("ingredients") if isinstance(row.get("ingredients"), list) else []
        eqp = row.get("equipment") if isinstance(row.get("equipment"), list) else []
        blocks.append((num, inst, ings, eqp))
    for i, (num, inst, ings, eqp) in enumerate(blocks):
        st.markdown(
            f'<div class="pf-recipe-step">'
            f'<div class="pf-recipe-step-num">Step {num}</div>'
            f"{html.escape(inst)}</div>",
            unsafe_allow_html=True,
        )
        if ings:
            lab = ", ".join(str(x) for x in ings[:28] if str(x).strip())
            if lab:
                st.caption(f"Ingredients this step: {lab}")
        if eqp:
            lab2 = ", ".join(str(x) for x in eqp[:16] if str(x).strip())
            if lab2:
                st.caption(f"Equipment: {lab2}")
        if i < len(blocks) - 1:
            st.divider()


def resolve_display_steps(det: dict) -> tuple[list[str], str, list]:
    """
    Return (plain_steps, source_label, guide_rows).
    source_label: spoonacular | catalog | parsed
    """
    guide_rows = det.get("cooking_guide_steps") or []
    if isinstance(guide_rows, list) and len(guide_rows) >= 2:
        return [], "spoonacular", guide_rows

    sp = sanitize_steps(list(det.get("structured_steps") or []), instructions=det.get("instructions") or "")
    if len(sp) >= 2:
        src = str(det.get("step_source") or "catalog").strip() or "catalog"
        return sp, src, []

    instr = det.get("instructions") or ""
    steps = expand_to_clear_steps(instr, min_steps=3)
    return steps, "parsed" if steps else "", []
