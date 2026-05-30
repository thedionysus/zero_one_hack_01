"""Pure-stdlib scoring for the Sybilion forecast bake-off.

Scores each (fertilizer, variant) cell's backtest hindcast against a lag-12
seasonal-naive baseline, excluding stale windows (forecast_end past the last
real data point). P50 = quantile_forecast["0.50"]. No numpy/pandas/math.
"""
from lib.ts_utils import month_index

SEASON = 12
P50_KEY = "0.50"
BAND_80 = ("0.10", "0.90")
BAND_90 = ("0.05", "0.95")


def _sqrt(x):
    return x ** 0.5


def _ordered_values(series):
    items = sorted(series.items(), key=lambda kv: month_index(kv[0]))
    return [float(v) for _d, v in items]


def seasonal_naive_mae(series, season=SEASON):
    """Mean |y_t - y_{t-season}| over the input history. series: {date: float}."""
    vals = _ordered_values(series)
    diffs = [abs(vals[i] - vals[i - season]) for i in range(season, len(vals))]
    if not diffs:
        raise ValueError("series too short for seasonal naive")
    return sum(diffs) / len(diffs)


def seasonal_naive_rmse(series, season=SEASON):
    """Root-mean-square of seasonal-naive errors over the input history."""
    vals = _ordered_values(series)
    sq = [(vals[i] - vals[i - season]) ** 2 for i in range(season, len(vals))]
    if not sq:
        raise ValueError("series too short for seasonal naive")
    return _sqrt(sum(sq) / len(sq))


def extract_scorable_points(trajectories, last_real_date):
    """Return (points, n_windows_scored, n_windows_excluded_stale).

    trajectories: {"data": [ {"forecast_end", "forecast_series": {date: {actual,
    quantile_forecast}}} ]}. A whole window is EXCLUDED when its forecast_end is
    later than last_real_date (its actuals run past real data -> null/garbage;
    the documented stale-backtest gotcha). Within kept windows, months whose
    actual is None are skipped defensively.
    points: list of (actual_float, quantile_dict).
    """
    cutoff = month_index(last_real_date)
    points = []
    n_scored = 0
    n_excluded = 0
    for window in trajectories["data"]:
        if month_index(window["forecast_end"]) > cutoff:
            n_excluded += 1
            continue
        n_scored += 1
        for _date, entry in window["forecast_series"].items():
            actual = entry.get("actual")
            if actual is None:
                continue
            points.append((float(actual), entry["quantile_forecast"]))
    return points, n_scored, n_excluded


def _p50(qdict):
    return float(qdict[P50_KEY])


def mae_points(points):
    if not points:
        raise ValueError("no scorable points")
    return sum(abs(a - _p50(q)) for a, q in points) / len(points)


def rmse_points(points):
    if not points:
        raise ValueError("no scorable points")
    return _sqrt(sum((a - _p50(q)) ** 2 for a, q in points) / len(points))


def mape_points(points):
    # Denominator is the count of nonzero-actual points; MAE/RMSSE use all points.
    usable = [(a, q) for a, q in points if a != 0]
    if not usable:
        raise ValueError("no nonzero actuals for MAPE")
    return sum(abs(a - _p50(q)) / abs(a) for a, q in usable) / len(usable) * 100.0


def band_coverage(points, lo_key, hi_key):
    if not points:
        raise ValueError("no scorable points")
    covered = sum(1 for a, q in points if float(q[lo_key]) <= a <= float(q[hi_key]))
    return covered / len(points)


def score_cell(series, trajectories, last_real_date):
    """Full metric bundle for one cell. Returns a dict of metrics."""
    points, n_scored, n_excluded = extract_scorable_points(trajectories, last_real_date)
    naive_mae = seasonal_naive_mae(series)
    naive_rmse = seasonal_naive_rmse(series)
    if naive_mae == 0 or naive_rmse == 0:
        raise ValueError("degenerate series: seasonal-naive scale is zero (flat history)")
    return {
        "mase": mae_points(points) / naive_mae,
        "rmsse": rmse_points(points) / naive_rmse,
        "mape": mape_points(points),
        "cov80": band_coverage(points, *BAND_80),
        "cov90": band_coverage(points, *BAND_90),
        "n_points": len(points),
        "n_windows_scored": n_scored,
        "n_windows_excluded_stale": n_excluded,
    }


def rank_variants(cells):
    """cells: {variant: metrics_dict | None}. Returns (winner_variant, ordered_list).

    Ranked by MASE ascending, tiebreak MAPE ascending. None-metric cells sort last.
    """
    if not cells:
        raise ValueError("no variants to rank")

    def key(item):
        _v, m = item
        if m is None:
            return (float("inf"), float("inf"))
        return (m["mase"], m["mape"])
    ordered = sorted(cells.items(), key=key)
    return ordered[0][0], [v for v, _m in ordered]


def forecast_block(forecast_json):
    """From forecast.json -> {date: {"p05":.., "p10":.., ..., "p95":..}}.

    Maps each quantile key "0.05".."0.95" to "p05".."p95" (includes "p50").
    Note: the mean "forecast" key is intentionally excluded; champions.json uses the P50 quantile.
    """
    series = forecast_json["data"]["forecast_series"]
    out = {}
    for date, entry in series.items():
        q = entry["quantile_forecast"]
        out[date] = {"p" + k[2:]: float(v) for k, v in q.items()}
    return out
