"""Plotly figure builders for the demo UI. Pure functions: data in, Figure out.

Kept import-isolated (plotly only) so the rest of the app's logic stays stdlib
and unit-testable without the UI stack.
"""
# Eagerly fully-initialize numpy here, at module import (main load), BEFORE any
# chart is built. Plotly probes numpy via get_module("numpy", should_load=False),
# i.e. it reads sys.modules without finishing the import. Under Streamlit, plotly's
# own lazy first-import of numpy runs in the ScriptRunner worker thread; if a rerun
# interrupts it, a *partially initialized* numpy is left cached and every later
# render crashes with "partially initialized module 'numpy' ... circular import"
# until the process restarts. Importing it fully here closes that window.
import numpy  # noqa: F401

import plotly.graph_objects as go

from lib.ts_utils import month_index

_BLUE = "#1f77b4"
_GREY = "#888888"
_GREEN = "#2ca02c"


def _ordered(block):
    return sorted(block.keys(), key=month_index)


def forecast_figure(native, corrected, plan):
    """Corrected P10-P90 band + P50 line, native P50 overlay, purchase markers."""
    months = _ordered(corrected)
    p50 = [corrected[m]["p50"] for m in months]
    p10 = [corrected[m]["p10"] for m in months]
    p90 = [corrected[m]["p90"] for m in months]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=months + months[::-1], y=p90 + p10[::-1],
                             fill="toself", fillcolor="rgba(31,119,180,0.15)",
                             line=dict(width=0), hoverinfo="skip",
                             name="corrected 80% band"))
    fig.add_trace(go.Scatter(x=months, y=p50, mode="lines",
                             line=dict(color=_BLUE, width=2),
                             name="corrected P50"))
    nat_months = [m for m in months if m in native and "p50" in native[m]]
    nat_vals = [native[m]["p50"] for m in nat_months]
    if nat_vals:
        fig.add_trace(go.Scatter(x=nat_months, y=nat_vals, mode="lines",
                                 line=dict(color=_GREY, width=1, dash="dash"),
                                 name="native P50"))
    buy_months = [m for m in months if plan.orders_t.get(m, 0) > 0]
    if buy_months:
        sizes = [8 + 0.01 * plan.orders_t[m] for m in buy_months]
        ys = [corrected[m]["p50"] for m in buy_months]
        fig.add_trace(go.Scatter(x=buy_months, y=ys, mode="markers",
                                 marker=dict(color=_GREEN, size=sizes,
                                             line=dict(color="white", width=1)),
                                 name="scheduled buy"))
    fig.update_layout(title="Forecast (recalibrated) & purchase schedule",
                      yaxis_title="USD/kg", xaxis_title="month",
                      margin=dict(l=10, r=10, t=40, b=10), height=380)
    return fig


def calibration_figure(cov80_native, cov80_corrected):
    """Two bars: native vs corrected 80% coverage, with the 0.80 target line."""
    fig = go.Figure(go.Bar(
        x=["native", "corrected"],
        y=[cov80_native, cov80_corrected],
        marker_color=[_GREY, _BLUE],
        text=[f"{cov80_native:.0%}", f"{cov80_corrected:.0%}"],
        textposition="outside"))
    fig.add_hline(y=0.80, line=dict(color=_GREEN, dash="dot"),
                  annotation_text="80% target")
    fig.update_layout(title="80% band coverage: native vs recalibrated",
                      yaxis=dict(range=[0, 1.05], tickformat=".0%"),
                      margin=dict(l=10, r=10, t=40, b=10), height=300)
    return fig


def savings_figure(plan):
    """Bar of scheduled purchase tonnage per month (the decision surface)."""
    months = plan.months
    tonnes = [plan.orders_t.get(m, 0.0) for m in months]
    colors = [_GREEN if m == plan.target_month else _BLUE for m in months]
    fig = go.Figure(go.Bar(x=months, y=tonnes, marker_color=colors))
    fig.update_layout(title="Scheduled purchase (tonnes per month)",
                      yaxis_title="tonnes", xaxis_title="month",
                      margin=dict(l=10, r=10, t=40, b=10), height=300)
    return fig


def trust_rows(calibrated):
    """Trust table rows for all fertilizers, sorted by trust score descending."""
    rows = []
    for slug, f in calibrated["by_fert"].items():
        rows.append({
            "fertilizer": slug,
            "trust": f["trust"]["score"],
            "label": f["trust"]["label"],
            "cov80_native": f["cov80_native"],
            "cov80_corrected": f["cov80_corrected"],
        })
    rows.sort(key=lambda r: r["trust"], reverse=True)
    return rows
