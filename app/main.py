"""Streamlit demo: trust-hero procurement decision with live adaptive levers.

Run:  .venv/bin/streamlit run app/main.py
The fixed pipeline (calibrate -> solve -> render) runs the same order every time;
sliders are the live levers. The chat shell (app/agent) is wired in a later task.
"""
import os
import sys

# Make repo root importable when launched via `streamlit run app/main.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st  # noqa: E402

from app import state as app_state  # noqa: E402
from app import charts  # noqa: E402
from lib import pipeline  # noqa: E402

RISK_CHOICES = {"neutral (P50)": "p50", "cautious (P70)": "p70", "averse (P80)": "p80"}


@st.cache_data(show_spinner="Calibrating forecasts…")
def get_calibrated():
    return app_state.calibrate_all()


def _risk_label(q):
    for label, key in RISK_CHOICES.items():
        if key == q:
            return label
    return "neutral (P50)"


def _sidebar(cal, current):
    st.sidebar.header("Levers")
    keys = list(cal["by_fert"].keys())
    fert = st.sidebar.selectbox("Fertilizer", keys,
                                index=keys.index(current.fertilizer), key="fert")
    demand = st.sidebar.slider("Monthly demand (t)", 100.0, 5000.0,
                               current.monthly_demand_t, 100.0, key="demand")
    stock = st.sidebar.slider("Current stock (t)", 0.0, 12000.0,
                              current.current_stock_t, 250.0, key="stock")
    carry = st.sidebar.slider("Carrying cost (%/yr)", 0.0, 0.40,
                              current.carrying_cost_pct_yr, 0.01, key="carry")
    risk_label = st.sidebar.select_slider("Risk tolerance", list(RISK_CHOICES.keys()),
                                          value=_risk_label(current.risk_quantile),
                                          key="risk")
    st.sidebar.subheader("Forecast shock")
    trend = st.sidebar.slider("Price trend (%/mo)", 0.0, 0.30, current.shock_trend_g,
                              0.01, key="trend",
                              help="A rising trend can flip WAIT to BUY-NOW.")
    level = st.sidebar.slider("Price level (±%)", -0.50, 0.50, current.shock_level_pct,
                              0.05, key="level",
                              help="Uniform shift: moves the € but not the timing.")
    return app_state.AppState(
        fertilizer=fert, monthly_demand_t=demand, current_stock_t=stock,
        carrying_cost_pct_yr=carry, risk_quantile=RISK_CHOICES[risk_label],
        shock_level_pct=level, shock_trend_g=trend)


def main():
    st.set_page_config(page_title="Fertilizer Procurement Agent", layout="wide")
    cal = get_calibrated()
    if "app_state" not in st.session_state:
        st.session_state.app_state = app_state.AppState.default(cal)

    state = _sidebar(cal, st.session_state.app_state)
    st.session_state.app_state = state
    res = app_state.solve_state(state, cal)
    plan = res["current_plan"]

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


main()
