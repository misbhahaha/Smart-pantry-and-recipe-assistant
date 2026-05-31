"""Shared Streamlit UI for daily calorie tracking (dashboard + profile)."""

from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd
import streamlit as st

from lib.api_client import PantryAPI


def _totals_by_day(rows: list[dict]) -> dict[dt.date, int]:
    by: dict[dt.date, int] = {}
    for r in rows:
        if not isinstance(r, dict):
            continue
        raw = r.get("entry_date")
        if raw is None:
            continue
        d = dt.date.fromisoformat(str(raw)[:10])
        kcal = int(r.get("calories") or 0)
        by[d] = by.get(d, 0) + kcal
    return by


def render_calorie_tracking(
    api: PantryAPI,
    me: dict[str, Any],
    rows: list[dict],
    *,
    key_prefix: str,
    table_limit: int = 12,
) -> None:
    today = dt.date.today()
    by_day = _totals_by_day(rows)
    today_total = int(by_day.get(today, 0))
    target = me.get("daily_calorie_target")
    target_i = int(target) if target else None

    days = 7
    start = today - dt.timedelta(days=days - 1)
    date_range = [start + dt.timedelta(days=i) for i in range(days)]
    series = [int(by_day.get(d, 0)) for d in date_range]
    week_sum = sum(series)
    avg_7 = week_sum / days

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Today (logged)", f"{today_total} kcal")
    with c2:
        if target_i and target_i > 0:
            delta = today_total - target_i
            st.metric("Daily target", f"{target_i} kcal", delta=f"{delta:+d} kcal vs today")
        else:
            st.metric("Daily target", "—", help="Set a target under Health & diet above.")
    with c3:
        st.metric("7-day average", f"{avg_7:.0f} kcal/day")

    if target_i and target_i > 0:
        ratio = min(1.0, today_total / target_i)
        st.progress(ratio, text=f"Today's progress vs target ({int(ratio * 100)}%)")

    chart_df = pd.DataFrame({"kcal": series}, index=[d.isoformat() for d in date_range])
    st.caption("Last 7 days (total kcal per day)")
    st.bar_chart(chart_df)

    with st.form(f"{key_prefix}_cal_form"):
        st.markdown("##### Log calories")
        day = st.date_input("Date", value=today, key=f"{key_prefix}_cal_day")
        k = st.number_input("Calories (kcal)", min_value=1, max_value=50000, value=400, key=f"{key_prefix}_cal_k")
        note = st.text_input("Notes (optional)", key=f"{key_prefix}_cal_note")
        if st.form_submit_button("Add entry"):
            try:
                api.log_calories(day.isoformat(), int(k), note)
                st.cache_data.clear()
                st.success("Entry saved.")
                st.rerun()
            except Exception as e:
                st.error(str(e))

    st.markdown("##### Recent entries")
    if not rows:
        st.caption("No entries yet — add one above.")
        return
    for row in rows[:table_limit]:
        rid = row.get("id")
        ed = row.get("entry_date")
        kcal = row.get("calories")
        notes = (row.get("notes") or "").strip()
        col_a, col_b = st.columns([4, 1])
        with col_a:
            line = f"**{ed}** — {kcal} kcal"
            if notes:
                line += f" · {notes}"
            st.markdown(line)
        with col_b:
            if rid is not None and st.button("Remove", key=f"{key_prefix}_del_{rid}"):
                try:
                    api.delete_calorie_entry(int(rid))
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
