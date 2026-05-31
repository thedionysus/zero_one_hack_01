"""App state model + persona-independent calibration cache (pure stdlib).

The fixed pipeline: calibrate_all() recalibrates all five champions ONCE
(persona-independent), then solve_state() applies any shock to the selected
fertilizer's corrected band and re-solves against the current persona, diffing
the result against the no-shock baseline for the adaptive old->new render.
"""
from dataclasses import dataclass, replace

from lib import pipeline
from lib import decision as dc
from lib import shocks


def calibrate_all():
    """Recalibrate every champion (persona-independent). Cache this in the UI."""
    last_real_date = pipeline.load_manifest()["last_real_date"]
    champions = pipeline.load_champions()
    by_fert = {}
    scores = {}
    for slug, champ in champions.items():
        cal = pipeline.recalibrate_champion(champ, last_real_date)
        trust = pipeline.trust_for_champion(champ)
        by_fert[slug] = {
            "native": cal["native"],
            "corrected": cal["corrected"],
            "cov80_native": cal["cov80_native"],
            "cov80_corrected": cal["cov80_corrected"],
            "trust": trust,
        }
        scores[slug] = trust["score"]
    hero = max(scores, key=scores.get)
    return {"by_fert": by_fert, "hero": hero, "last_real_date": last_real_date}


@dataclass(frozen=True)
class AppState:
    """Everything a single render needs: which fertilizer, the persona levers,
    and the two forecast shocks. Immutable; changes return a new instance."""
    fertilizer: str
    monthly_demand_t: float
    current_stock_t: float
    carrying_cost_pct_yr: float
    risk_quantile: str
    shock_level_pct: float = 0.0
    shock_trend_g: float = 0.0

    @classmethod
    def default(cls, calibrated):
        p = pipeline.AUSTRIAN_UREA_PERSONA
        return cls(
            fertilizer=calibrated["hero"],
            monthly_demand_t=p.monthly_demand_t,
            current_stock_t=p.current_stock_t,
            carrying_cost_pct_yr=p.carrying_cost_pct_yr,
            risk_quantile=p.risk_quantile,
        )

    def to_persona(self):
        return dc.Persona(
            monthly_demand_t=self.monthly_demand_t,
            current_stock_t=self.current_stock_t,
            carrying_cost_pct_yr=self.carrying_cost_pct_yr,
            risk_quantile=self.risk_quantile,
        )

    def replaced(self, **changes):
        return replace(self, **changes)


def _apply_shocks(corrected, state):
    block = corrected
    if state.shock_trend_g:
        block = shocks.trend_shift(block, state.shock_trend_g)
    if state.shock_level_pct:
        block = shocks.level_shift(block, state.shock_level_pct)
    return block


def solve_state(state, calibrated):
    """Solve the selected fertilizer at the current persona + shocks.

    Returns the corrected & shocked blocks, the no-shock baseline plan, the
    current (shocked) plan, their diff, trust/coverage, and the EUR saving.
    """
    fert = calibrated["by_fert"][state.fertilizer]
    corrected = fert["corrected"]
    persona = state.to_persona()
    shocked = _apply_shocks(corrected, state)
    baseline_plan = dc.solve(corrected, persona)
    current_plan = dc.solve(shocked, persona)
    return {
        "persona": persona,
        "native": fert["native"],
        "corrected": corrected,
        "shocked": shocked,
        "baseline_plan": baseline_plan,
        "current_plan": current_plan,
        "diff": shocks.plan_diff(baseline_plan, current_plan),
        "trust": fert["trust"],
        "cov80_native": fert["cov80_native"],
        "cov80_corrected": fert["cov80_corrected"],
        "savings_eur": current_plan.savings * pipeline.EUR_PER_USD,
    }
