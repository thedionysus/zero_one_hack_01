"""The one-concrete-change model + NL parse + deterministic narration (stdlib).

A Change is the single edit the chat shell (or a slider) produces. apply_change
returns a new AppState. rule_based_parse is the offline NL fallback; the LLM
edge (app/agent.py) produces the same Change type. narrate_template is the
offline before->after narration; the LLM may rephrase it.
"""
import re
from dataclasses import dataclass

VALID_KINDS = {
    "fertilizer", "demand", "stock", "carry", "risk", "level", "trend", "reset",
}

# rising-dynamic words => a percentage means a sustained upward TREND (flips the
# decision); a plain "higher/up" => a flat LEVEL shift (moves EUR, not timing).
_RISING = ("spike", "spiking", "spiked", "rally", "surge", "soar", "soaring",
           "rising", "rise", "climb", "climbing", "jump", "jumping")
_PER_MONTH = ("/mo", "per month", "a month", "/month", "monthly")


@dataclass(frozen=True)
class Change:
    kind: str
    value: object  # float for numeric kinds, str for fertilizer/risk, None for reset


def apply_change(state, change):
    """Return a NEW AppState with the single change applied. Pure."""
    k, v = change.kind, change.value
    if k == "fertilizer":
        return state.replaced(fertilizer=str(v))
    if k == "demand":
        return state.replaced(monthly_demand_t=float(v))
    if k == "stock":
        return state.replaced(current_stock_t=float(v))
    if k == "carry":
        return state.replaced(carrying_cost_pct_yr=float(v))
    if k == "risk":
        return state.replaced(risk_quantile=str(v))
    if k == "level":
        return state.replaced(shock_level_pct=float(v))
    if k == "trend":
        return state.replaced(shock_trend_g=float(v))
    if k == "reset":
        return state.replaced(shock_level_pct=0.0, shock_trend_g=0.0)
    raise ValueError(f"unknown change kind: {k}")


def _first_pct(text):
    """First percentage in the text as a fraction (e.g. '30%' -> 0.30), or None."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    return float(m.group(1)) / 100.0 if m else None


def _first_months(text):
    """First 'N month(s)' count as a float, or None."""
    m = re.search(r"(\d+(?:\.\d+)?)\s*month", text)
    return float(m.group(1)) if m else None


def rule_based_parse(text):
    """Deterministic offline NL -> Change. Returns None if nothing parseable.

    Magnitude always comes from the user's number; no value is hardcoded.
    """
    t = text.lower()
    pct = _first_pct(t)
    rising = any(w in t for w in _RISING)
    per_month = any(p in t for p in _PER_MONTH)

    # company-situation: runway / stock change ("1 month of stock left").
    # Returns a parser-level 'stock_months' intent (months); the UI normalizes
    # it to a 'stock' Change (tonnes) using the current monthly demand.
    if ("stock" in t or "runway" in t or "supplier" in t) and "month" in t:
        months = _first_months(t)
        if months is not None:
            return Change("stock_months", months)

    if pct is not None:
        if rising or per_month:
            return Change("trend", pct)        # sustained upward push
        return Change("level", pct)            # flat level shift

    if any(w in t for w in ("reset", "clear", "undo", "back to normal")):
        return Change("reset", None)
    return None


def _change_phrase(change):
    k, v = change.kind, change.value
    if k == "trend":
        return f"A sustained +{v * 100:.0f}%/mo price trend"
    if k == "level":
        return f"A flat +{v * 100:.0f}% price level"
    if k in ("stock", "stock_months"):
        return "The new stock level"
    if k == "risk":
        return f"Risk tolerance {v}"
    if k == "fertilizer":
        return f"Switching to {v}"
    if k == "reset":
        return "Clearing the shocks"
    return "That change"


def narrate_template(diff, change, eur_per_usd):
    """Deterministic before->after narration in EUR. The LLM may rephrase this."""
    rb, ra = diff["recommendation"]
    sb = diff["savings"][0] * eur_per_usd
    sa = diff["savings"][1] * eur_per_usd
    head = _change_phrase(change) + " "
    if diff["changed"]:
        ta = diff["target_month"][1]
        body = (f"flips the call from {rb} to {ra}"
                + (f", now targeting {ta}" if ta else "") + ". ")
    else:
        body = f"keeps the call at {ra}. "
    tail = f"Forward saving moves from €{sb:,.0f} to €{sa:,.0f}."
    return head + body + tail
