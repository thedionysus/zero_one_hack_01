"""Forecast shock injector + decision diff (pure stdlib).

v1 shock = a uniform level shift applied to the CORRECTED band; the decision
consumes the corrected band directly, so one transform re-prices everything on
the next solve. plan_diff gives the adaptive old->new render its payload.
"""


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
