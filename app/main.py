"""Streamlit demo: trust-hero procurement decision with live adaptive levers.

Run:  .venv/bin/streamlit run app/main.py
The fixed pipeline (calibrate -> solve -> render) runs the same order every time.
Sliders are the live levers; the chat box is an NL curveball that writes the same
widget state the sliders do (so a curveball moves the sliders and re-solves). The
LLM does only two edge jobs (parse one change, narrate the diff) and degrades to
a deterministic offline path when no ANTHROPIC_API_KEY is present.
"""
import os
import sys

# Make repo root importable when launched via `streamlit run app/main.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402

from app import state as app_state  # noqa: E402
from app import charts  # noqa: E402
from app import agent  # noqa: E402
from app import changes  # noqa: E402
from lib import pipeline  # noqa: E402
from lib import shocks  # noqa: E402

RISK_CHOICES = {"neutral (P50)": "p50", "cautious (P70)": "p70", "averse (P80)": "p80"}

_NUMERIC_KINDS = {"trend", "level", "stock", "demand", "carry"}


@st.cache_data(show_spinner="Calibrating forecasts…")
def get_calibrated():
    return app_state.calibrate_all()


def _risk_label(q):
    for label, key in RISK_CHOICES.items():
        if key == q:
            return label
    return "neutral (P50)"


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _init_session(cal):
    """Seed the widget session_state keys once; they are the source of truth."""
    if "seeded" in st.session_state:
        return
    d = app_state.AppState.default(cal)
    st.session_state.fert = d.fertilizer
    st.session_state.demand = d.monthly_demand_t
    st.session_state.stock = d.current_stock_t
    st.session_state.carry = d.carrying_cost_pct_yr
    st.session_state.risk = _risk_label(d.risk_quantile)
    st.session_state.trend = d.shock_trend_g
    st.session_state.level = d.shock_level_pct
    st.session_state.client = agent.build_client()
    st.session_state.chat_log = []
    st.session_state.seeded = True


def _state_from_session():
    return app_state.AppState(
        fertilizer=st.session_state.fert,
        monthly_demand_t=st.session_state.demand,
        current_stock_t=st.session_state.stock,
        carrying_cost_pct_yr=st.session_state.carry,
        risk_quantile=RISK_CHOICES[st.session_state.risk],
        shock_level_pct=st.session_state.level,
        shock_trend_g=st.session_state.trend)


def _write_change_to_widgets(change):
    """Apply one Change to the widget session_state keys (clamped to slider range)."""
    k, v = change.kind, change.value
    if k == "trend":
        st.session_state.trend = _clamp(float(v), 0.0, 0.30)
    elif k == "level":
        st.session_state.level = _clamp(float(v), -0.50, 0.50)
    elif k == "stock":
        st.session_state.stock = _clamp(float(v), 0.0, 12000.0)
    elif k == "demand":
        st.session_state.demand = _clamp(float(v), 100.0, 5000.0)
    elif k == "carry":
        st.session_state.carry = _clamp(float(v), 0.0, 0.40)
    elif k == "risk":
        st.session_state.risk = _risk_label(str(v))
    elif k == "fertilizer":
        st.session_state.fert = str(v)
    elif k == "reset":
        st.session_state.trend = 0.0
        st.session_state.level = 0.0


def _handle_curveball(prompt, cal):
    """Parse the curveball, write the resulting change to the widgets, and stash a
    pending narration to resolve once the after-plan is computed."""
    change = agent.parse_curveball(prompt, client=st.session_state.client)
    if change is None:
        st.session_state.chat_log.append(("user", prompt))
        st.session_state.chat_log.append(
            ("assistant", "I couldn't turn that into a concrete change — try a "
             "number, e.g. 'prices rising 20% a month' or 'down to 1 month of stock'."))
        return
    if change.kind == "stock_months":  # normalize parser intent -> tonnes
        change = changes.Change("stock", change.value * st.session_state.demand)
    if change.kind in _NUMERIC_KINDS:
        try:
            change = changes.Change(change.kind, float(change.value))
        except (TypeError, ValueError):
            st.session_state.chat_log.append(("user", prompt))
            st.session_state.chat_log.append(
                ("assistant", "I parsed a change but its value wasn't a number — "
                 "try rephrasing with a clear percentage or tonnage."))
            return
    before_plan = app_state.solve_state(_state_from_session(), cal)["current_plan"]
    _write_change_to_widgets(change)
    st.session_state.pending = (prompt, change, before_plan)


def _resolve_pending(after_plan):
    """Narrate the stashed before->after change now that the after-plan exists."""
    pend = st.session_state.pop("pending", None)
    if not pend:
        return
    prompt, change, before_plan = pend
    diff = shocks.plan_diff(before_plan, after_plan)
    note = agent.narrate(diff, change, pipeline.EUR_PER_USD,
                         client=st.session_state.client)
    st.session_state.chat_log.append(("user", prompt))
    st.session_state.chat_log.append(("assistant", note))


def _sidebar(cal):
    st.sidebar.header("Levers")
    st.sidebar.selectbox("Fertilizer", list(cal["by_fert"].keys()), key="fert")
    st.sidebar.slider("Monthly demand (t)", 100.0, 5000.0, step=100.0, key="demand")
    st.sidebar.slider("Current stock (t)", 0.0, 12000.0, step=250.0, key="stock")
    st.sidebar.slider("Carrying cost (%/yr)", 0.0, 0.40, step=0.01, key="carry")
    st.sidebar.select_slider("Risk tolerance", list(RISK_CHOICES.keys()), key="risk")
    st.sidebar.subheader("Forecast shock")
    st.sidebar.slider("Price trend (%/mo)", 0.0, 0.30, step=0.01, key="trend",
                      help="A rising trend can flip WAIT to BUY-NOW.")
    st.sidebar.slider("Price level (±%)", -0.50, 0.50, step=0.05, key="level",
                      help="Uniform shift: moves the € but not the timing.")
    return _state_from_session()


def main():
    st.set_page_config(page_title="Fertilizer Procurement Agent", layout="wide")
    cal = get_calibrated()
    _init_session(cal)

    prompt = st.chat_input("Throw a curveball (e.g. 'gas spiked, prices rising 25% a month')")
    if prompt:
        _handle_curveball(prompt, cal)

    state = _sidebar(cal)
    res = app_state.solve_state(state, cal)
    plan = res["current_plan"]
    _resolve_pending(plan)

    st.title("Fertilizer Procurement Decision Agent")
    st.caption(f"Hero by trust: **{cal['hero']}** · data through {cal['last_real_date']} · "
               "drivers panel: not wired in v1 (needs a separate forecast config)")

    c1, c2, c3 = st.columns(3)
    c1.metric("Recommendation", plan.recommendation,
              delta=None if not res["diff"]["changed"]
              else f"was {res['diff']['recommendation'][0]}")
    c2.metric("Target month", plan.target_month or "—")
    c3.metric("Forward saving vs naive", f"€{res['savings_eur']:,.0f}",
              delta=f"{plan.savings_pct:.1%}")
    st.write(plan.rationale)

    left, right = st.columns([3, 2])
    with left:
        st.plotly_chart(charts.forecast_figure(res["native"], res["corrected"], plan),
                        width="stretch")
        st.plotly_chart(charts.savings_figure(plan), width="stretch")
    with right:
        st.plotly_chart(charts.calibration_figure(res["cov80_native"],
                                                  res["cov80_corrected"]),
                        width="stretch")
        t = res["trust"]
        st.metric("Trust score", f"{t['score']:.2f} ({t['label']})")

    st.subheader("All fertilizers — trust ranking")
    st.dataframe(charts.trust_rows(cal), width="stretch", hide_index=True)

    if st.session_state.chat_log:
        st.subheader("Agent")
        for role, msg in st.session_state.chat_log[-6:]:
            with st.chat_message(role):
                st.write(msg)


main()
