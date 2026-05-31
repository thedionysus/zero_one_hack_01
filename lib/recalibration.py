"""Conformal recalibration of Sybilion quantile bands (pure stdlib).

The native bands are overconfident (an 80% band covered ~22% of urea actuals)
and biased low (actuals sat above P50 ~97% of the time during rises). We rebuild
each forecast month's band empirically from the hindcast residuals:

    residual r = actual - P50   (per scorable backtest point)
    corrected_q(tau) = forecast_P50 + empirical_quantile(residuals, tau)

This simultaneously (a) widens the band to the true spread and (b) shifts it to
remove the under-prediction bias (the median residual is added to P50, so a
positive bias pushes the corrected median up). Split-conformal in spirit; the
in-sample coverage on the calibration points hits the nominal level by
construction. Reuses forecast_scoring.extract_scorable_points (which already
drops stale spike-tail windows) so the residual set is clean.
"""
from lib.ts_utils import percentile, month_index
from lib import forecast_scoring as fs

# 19 quantile levels Sybilion emits, as floats. "p05".."p95" keys downstream.
QUANTILE_TAUS = [round(0.05 * k, 2) for k in range(1, 20)]
P50_KEY = "0.50"


def _qkey(tau):
    """0.05 -> 'p05', 0.5 -> 'p50', 0.95 -> 'p95'."""
    return f"p{int(round(tau * 100)):02d}"


def residuals_from_points(points):
    """[(actual, quantile_dict)] -> [actual - P50] list. Raises on empty."""
    if not points:
        raise ValueError("no points to compute residuals")
    return [a - float(q[P50_KEY]) for a, q in points]


def residual_offsets(residuals):
    """{tau: empirical residual quantile} for each of the 19 levels.

    Non-decreasing in tau (percentile is monotone), so corrected bands stay
    monotone. offsets[0.50] is the bias-correction shift added to every P50.
    """
    if not residuals:
        raise ValueError("no residuals")
    return {tau: percentile(residuals, tau * 100.0) for tau in QUANTILE_TAUS}


def recalibrate_block(forecast_block, offsets):
    """Apply residual offsets to a forecast block, centred on each month's P50.

    forecast_block: {date: {"p05":.., "p50":.., "p95":..}} (fs.forecast_block).
    Returns a NEW block {date: {"p05".."p95"}} with corrected, bias-shifted,
    properly-widened quantiles. Does not mutate the input.
    """
    out = {}
    for date, band in forecast_block.items():
        p50 = band["p50"]
        out[date] = {_qkey(tau): p50 + offsets[tau] for tau in QUANTILE_TAUS}
    return out


def coverage_with_offsets(points, offsets, lo_tau=0.10, hi_tau=0.90):
    """In-sample band coverage after recalibration: fraction of actuals inside
    [P50 + offset(lo), P50 + offset(hi)]. Used to show the native->corrected lift.
    """
    if not points:
        raise ValueError("no points")
    covered = 0
    for actual, q in points:
        p50 = float(q[P50_KEY])
        if p50 + offsets[lo_tau] <= actual <= p50 + offsets[hi_tau]:
            covered += 1
    return covered / len(points)


def recalibrate_from_block(native, trajectories, last_real_date):
    """Build conformal offsets from the hindcast and apply them to a native block.

    native: a {date: {pXX}} forecast block (>= p50 per month). Shared core of
    recalibrate() (which first derives the block from forecast.json) and the
    pipeline's champion path (which already has the block).
    """
    points, _scored, _excluded = fs.extract_scorable_points(trajectories, last_real_date)
    offsets = residual_offsets(residuals_from_points(points))
    return {
        "native": native,
        "corrected": recalibrate_block(native, offsets),
        "offsets": offsets,
        "bias": offsets[0.50],
        "cov80_native": fs.band_coverage(points, "0.10", "0.90"),
        "cov80_corrected": coverage_with_offsets(points, offsets, 0.10, 0.90),
    }


def recalibrate(forecast_json, trajectories, last_real_date):
    """End-to-end: derive the native block from forecast.json, then recalibrate.

    Returns a dict with:
      native    : forecast_block from forecast.json (untouched, for the viz)
      corrected : recalibrated block
      offsets   : {tau: offset}
      bias      : offsets[0.50] (the P50 shift; >0 means model under-predicted)
      cov80_native / cov80_corrected : in-sample 80% coverage before/after
    """
    return recalibrate_from_block(
        fs.forecast_block(forecast_json), trajectories, last_real_date)
