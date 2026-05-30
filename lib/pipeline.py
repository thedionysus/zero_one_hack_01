"""Per-fertilizer forward procurement decision over cached Sybilion champions.

Loads the bake-off winning forecast per fertilizer, recalibrates its band from
the non-stale hindcast residuals, scores trust, and solves the procurement
schedule against a warehouse persona. Picks the trust-hero for the demo.
Pure stdlib; reuses the decision core unchanged.
"""
import json
import os

from lib import forecast_scoring as fs
from lib import recalibration as rc
from lib import trust as tr
from lib import decision as dc

# champion refs ("bakeoff/urea/OFF/...") are relative to this directory.
DATA_DIR = os.path.join("data", "forecast_exploration")
CHAMPIONS_PATH = os.path.join(DATA_DIR, "bakeoff", "champions.json")
MANIFEST_PATH = os.path.join(DATA_DIR, "bakeoff", "manifest.json")

EUR_PER_USD = 0.92  # editable headline FX; benchmark prices are USD/kg.

# Realistic mid-size Austrian agri co-op (spec persona); fields are adaptive levers.
AUSTRIAN_UREA_PERSONA = dc.Persona(
    monthly_demand_t=1000.0,      # ~12,000 t/yr
    current_stock_t=3000.0,       # ~3 months runway
    carrying_cost_pct_yr=0.18,    # 18%/yr carrying cost
    risk_quantile="p50",          # neutral; "p70"/"p80" for risk-averse
)


def load_manifest(path=MANIFEST_PATH):
    with open(path) as f:
        return json.load(f)


def load_champions(path=CHAMPIONS_PATH):
    with open(path) as f:
        return json.load(f)


def _resolve_ref(ref):
    return os.path.join(DATA_DIR, ref)


def recalibrate_champion(champ, last_real_date):
    """Corrected band + native/corrected coverage for one champion entry.

    champ["forecast"] is already a {date: {pXX}} block (>= p50 per month);
    recalibrate_block reads only each month's p50, so point-only forward months
    still get a full corrected band.
    """
    native = champ["forecast"]
    with open(_resolve_ref(champ["backtest_trajectories_ref"])) as f:
        traj = json.load(f)
    points, _scored, _excluded = fs.extract_scorable_points(traj, last_real_date)
    offsets = rc.residual_offsets(rc.residuals_from_points(points))
    return {
        "native": native,
        "corrected": rc.recalibrate_block(native, offsets),
        "offsets": offsets,
        "bias": offsets[0.50],
        "cov80_native": fs.band_coverage(points, "0.10", "0.90"),
        "cov80_corrected": rc.coverage_with_offsets(points, offsets, 0.10, 0.90),
    }


def trust_for_champion(champ):
    """Collapse the champion's cached accuracy + native coverage into a trust dict."""
    metrics = dict(champ["accuracy"])
    metrics.update(champ["trust"])  # adds cov80, cov90
    return tr.trust_from_metrics(metrics)


def run_fertilizer(slug, champ, last_real_date, persona):
    cal = recalibrate_champion(champ, last_real_date)
    trust = trust_for_champion(champ)
    plan = dc.solve(cal["corrected"], persona)
    return {
        "fertilizer": slug,
        "calibration": cal,
        "trust": trust,
        "plan": plan,
        "savings_eur": plan.savings * EUR_PER_USD,
    }


def run_all(persona=AUSTRIAN_UREA_PERSONA,
            champions_path=CHAMPIONS_PATH, manifest_path=MANIFEST_PATH):
    last_real_date = load_manifest(manifest_path)["last_real_date"]
    champions = load_champions(champions_path)
    results = {
        slug: run_fertilizer(slug, champ, last_real_date, persona)
        for slug, champ in champions.items()
    }
    hero = max(results.values(), key=lambda r: r["trust"]["score"])["fertilizer"]
    return {"results": results, "hero": hero, "last_real_date": last_real_date}
