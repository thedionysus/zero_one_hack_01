"""Tier-1 rigorous procurement backtest over Sybilion hindcast windows.

For each non-stale window: recalibrate that window's quantile forecast using
leave-one-out residuals from the OTHER windows (no leakage), solve the purchase
schedule on the corrected forecast, then re-price those decisions on the
window's REALIZED actuals -- decide on the forecast, pay on the truth. Reports
agent vs buy-as-you-go saving plus a perfect-hindsight ceiling. Pure stdlib.
"""
from lib import recalibration as rc
from lib import decision as dc
from lib.ts_utils import month_index

KG = dc.KG_PER_TONNE


def _scorable_windows(traj, last_real_date):
    """Windows whose actuals run no later than the last real data point."""
    cutoff = month_index(last_real_date)
    return [w for w in traj["data"]
            if month_index(w["forecast_end"]) <= cutoff]


def _window_block(window):
    """{date: {pXX: float}} from a window's quantile forecasts ('0.05'->'p05')."""
    return {
        date: {"p" + k[2:]: float(v) for k, v in entry["quantile_forecast"].items()}
        for date, entry in window["forecast_series"].items()
    }


def _window_actuals(window):
    """{date: actual_float}. Scorable windows have a non-None actual every month."""
    return {date: float(entry["actual"])
            for date, entry in window["forecast_series"].items()}


def _points_excluding(windows, skip_idx):
    """(actual, quantile_dict) points from every window except skip_idx."""
    points = []
    for i, w in enumerate(windows):
        if i == skip_idx:
            continue
        for _date, entry in w["forecast_series"].items():
            if entry.get("actual") is not None:
                points.append((float(entry["actual"]), entry["quantile_forecast"]))
    return points


def _realized_cost(plan, actuals, persona):
    """Re-price the plan's purchase decisions on realized actual prices."""
    months = plan.months
    pos = {m: i for i, m in enumerate(months)}
    carry = persona.monthly_carry
    demand = persona.monthly_demand_t
    covered = int(persona.runway_months)
    agent = 0.0
    baseline = 0.0
    for d in range(covered, len(months)):
        dmon = months[d]
        pmon = plan.purchase_for[dmon]
        gap = d - pos[pmon]
        agent += demand * KG * actuals[pmon] * (1.0 + carry * gap)
        baseline += demand * KG * actuals[dmon]
    return agent, baseline


def _perfect_ceiling(actuals, months, persona):
    """Max achievable saving with full knowledge of the realized prices.

    Reuses the decision core's per-month argmin (over ACTUAL prices here) so the
    ceiling cannot silently desync from the cost model the policy optimizes.
    """
    carry = persona.monthly_carry
    demand = persona.monthly_demand_t
    covered = int(persona.runway_months)
    prices = [actuals[m] for m in months]
    agent = 0.0
    baseline = 0.0
    for d in range(covered, len(months)):
        _p, best_unit = dc._optimal_purchase_index(prices, d, carry)
        agent += demand * KG * best_unit
        baseline += demand * KG * prices[d]
    return baseline - agent


def backtest(traj, last_real_date, persona):
    """Run the leave-one-out hindcast backtest. Returns a summary dict."""
    windows = _scorable_windows(traj, last_real_date)
    per_window = []
    for i, w in enumerate(windows):
        actuals = _window_actuals(w)
        block = _window_block(w)
        points = _points_excluding(windows, i)
        offsets = rc.residual_offsets(rc.residuals_from_points(points))
        corrected = rc.recalibrate_block(block, offsets)
        plan = dc.solve(corrected, persona)
        agent, baseline = _realized_cost(plan, actuals, persona)
        ceiling = _perfect_ceiling(actuals, plan.months, persona)
        saving = baseline - agent
        per_window.append({
            "forecast_start": w["forecast_start"],
            "forecast_end": w["forecast_end"],
            "agent_cost": agent,
            "baseline_cost": baseline,
            "saving": saving,
            "saving_pct": (saving / baseline) if baseline else 0.0,
            "ceiling_saving": ceiling,
            "capture_ratio": (saving / ceiling) if ceiling > 0 else 0.0,
            "recommendation": plan.recommendation,
        })
    tot_base = sum(x["baseline_cost"] for x in per_window)
    tot_save = sum(x["saving"] for x in per_window)
    return {
        "n_windows": len(per_window),
        "per_window": per_window,
        "total_saving": tot_save,
        "total_saving_pct": (tot_save / tot_base) if tot_base else 0.0,
    }
