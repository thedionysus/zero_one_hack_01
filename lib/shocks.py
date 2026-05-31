"""Forecast shock injectors + decision diff (pure stdlib).

Two shocks on the CORRECTED band, which the decision consumes directly so one
transform re-prices everything on the next solve:
  - level_shift: a uniform factor on every quantile. Moves the EUR magnitude but
    is decision-INERT (a constant factor leaves the cost-min argmin unchanged).
  - trend_shift: a compounding monthly trend that steepens the forward curve, so
    near-term buying becomes relatively cheaper and the decision can flip toward
    BUY_NOW. This is the shock that drives the adaptive demo moment.
plan_diff gives the adaptive old->new render its payload.
"""

from lib.ts_utils import month_index


def level_shift(block, pct):
    """Scale every quantile of every month by (1 + pct). pct=0.30 => +30%.

    Returns a NEW block; does not mutate the input. pct must be > -1 (a >=100%
    drop is non-physical for a price level).
    """
    if pct <= -1.0:
        raise ValueError("pct must be > -1 (a >=100% price drop is non-physical)")
    factor = 1.0 + pct
    return {
        date: {q: value * factor for q, value in band.items()}
        for date, band in block.items()
    }


def trend_shift(block, g_per_month):
    """Apply a compounding monthly trend: chronological month i scaled by (1+g)**i.

    Unlike level_shift (a constant factor, which leaves the cost-min decision
    unchanged), a trend steepens the forward curve -- later months rise more than
    near ones -- so near-term purchasing becomes relatively cheaper and the
    decision can flip toward BUY_NOW. g_per_month is a %/month slider; g=0 is the
    identity. Returns a NEW block; does not mutate. g must be > -1.
    """
    if g_per_month <= -1.0:
        raise ValueError("g_per_month must be > -1 (a >=100% monthly drop is non-physical)")
    if not block:
        return {}
    base = min(month_index(date) for date in block)
    out = {}
    for date in sorted(block, key=month_index):
        i = month_index(date) - base
        factor = (1.0 + g_per_month) ** i
        out[date] = {q: value * factor for q, value in block[date].items()}
    return out


def plan_diff(before, after):
    """Structured old->new diff between two OrderPlans for the adaptive render."""
    return {
        "recommendation": (before.recommendation, after.recommendation),
        "changed": before.recommendation != after.recommendation,
        "target_month": (before.target_month, after.target_month),
        "savings": (before.savings, after.savings),
        "savings_delta": after.savings - before.savings,
        "savings_pct": (before.savings_pct, after.savings_pct),
    }
