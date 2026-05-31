"""Per-fertilizer trust score (pure stdlib).

Collapses the forecast_scoring metric bundle into one [0, 1] reliability number
plus a label, so the decision layer can down-weight forecasts the model cannot
get right (e.g. phosphate-rock's flat tail) and the UI can rank fertilizers.

Three components, each mapped to [0, 1] (higher = better), then weighted:
  calibration : how close the native 80%/90% bands are to nominal coverage
  skill       : MASE (<=1 means it beats the seasonal-naive baseline)
  accuracy    : MAPE (lower error = higher score)
The native bands are recalibrated elsewhere; calibration here measures how
trustworthy the raw model was, which is what should gate the decision weight.
"""

W_CALIBRATION = 0.4
W_SKILL = 0.4
W_ACCURACY = 0.2

# Mapping anchors (documented, tunable).
CAL_ZERO_AT = 0.5     # summed |coverage error| at which calibration score hits 0
MAPE_ZERO_AT = 50.0   # MAPE (%) at which accuracy score hits 0

HIGH_TRUST = 0.66
LOW_TRUST = 0.40


def _clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def calibration_score(cov80, cov90):
    """1.0 when bands are perfectly calibrated, decaying with total coverage error."""
    err = abs(cov80 - 0.80) + abs(cov90 - 0.90)
    return _clamp(1.0 - err / CAL_ZERO_AT)


def skill_score(mase):
    """1.0 when MASE <= 1 (beats naive); decays as it gets worse than naive."""
    if mase <= 0:
        raise ValueError("mase must be positive")
    return _clamp(1.0 / mase)


def accuracy_score(mape):
    """1.0 at 0% MAPE, linearly to 0 at MAPE_ZERO_AT."""
    return _clamp(1.0 - mape / MAPE_ZERO_AT)


def trust_label(score):
    if score >= HIGH_TRUST:
        return "high"
    if score >= LOW_TRUST:
        return "medium"
    return "low"


def trust_from_metrics(metrics):
    """metrics: a forecast_scoring.score_cell dict. Returns a trust dict.

    {score, label, calibration, skill, accuracy} — components exposed for the
    'why this trust level' breakdown in the UI.
    """
    cal = calibration_score(metrics["cov80"], metrics["cov90"])
    skl = skill_score(metrics["mase"])
    acc = accuracy_score(metrics["mape"])
    score = W_CALIBRATION * cal + W_SKILL * skl + W_ACCURACY * acc
    return {
        "score": score,
        "label": trust_label(score),
        "calibration": cal,
        "skill": skl,
        "accuracy": acc,
    }


def relative_weights(scores_by_fertilizer):
    """{fertilizer: trust_score} -> {fertilizer: normalized weight summing to 1}.

    Used to down-weight low-trust series in any cross-fertilizer aggregate.
    All-zero input returns uniform weights (avoid divide-by-zero).
    """
    total = sum(scores_by_fertilizer.values())
    n = len(scores_by_fertilizer)
    if n == 0:
        return {}
    if total <= 0:
        return {k: 1.0 / n for k in scores_by_fertilizer}
    return {k: v / total for k, v in scores_by_fertilizer.items()}
