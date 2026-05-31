# Procurement Decision Core (Pipeline + Impact + Shocks) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the deterministic Python core that turns the cached Sybilion bake-off champions into a per-fertilizer buy/wait/split decision, a trust-ranked hero pick, a rigorous backtested €-saving, and an instant shock re-solve — everything the Streamlit UI (separate plan) will wire together.

**Architecture:** Three new pure-stdlib modules over the existing decision core. `lib/pipeline.py` loads `champions.json` + hindcast trajectories, recalibrates each forecast band, scores trust, solves the procurement schedule against a warehouse persona, and picks the trust-hero. `lib/impact.py` runs the Tier-1 rigorous hindcast backtest (decide-on-forecast / pay-on-actuals, leave-one-out recalibration to avoid leakage) plus a perfect-hindsight ceiling. `lib/shocks.py` applies a uniform level shift to the corrected band and diffs two decisions for the adaptive old→new render. A thin `scripts/pipeline_report.py` wires them into a headless summary for manual verification.

**Tech Stack:** Pure Python 3 standard library (json, os, dataclasses). Tests via `python3 -m unittest` (no pip, pytest, numpy, or pandas available in this environment). Reuses `lib/forecast_scoring.py`, `lib/recalibration.py`, `lib/trust.py`, `lib/decision.py`, `lib/ts_utils.py`.

---

## Background the implementer needs

**This environment has no pip/pytest/numpy.** Run tests with:
```bash
python3 -m unittest tests.test_pipeline -v
```
Run the whole suite with `python3 -m unittest discover -s tests -q` (currently 91 tests, all green). All code is stdlib only.

**Data shapes (verified against the real files):**

`data/forecast_exploration/bakeoff/champions.json` is `{slug: champ}` for the 5 slugs
`urea, dap, mop, tsp, phosphate-rock`. Each `champ`:
```python
{
  "winner_variant": "OFF",
  "config": {...},
  "forecast": {                      # ALREADY a {date: {pXX: float}} block
    "2026-04-01": {"p05":0.28,...,"p50":0.36,...,"p95":0.44},  # urea/dap: full 19 quantiles
    "2026-05-01": {"p50": 0.38},     # mop/tsp/phosphate-rock forward months: p50 ONLY
    ...                              # 12 months, 2026-04-01 .. 2027-03-01
  },
  "forward_bands_available": true,   # false for mop/tsp/phosphate-rock
  "backtest_trajectories_ref": "bakeoff/urea/OFF/backtest_trajectories.json",  # relative to data/forecast_exploration/
  "external_signals_ref": "bakeoff/urea/OFF/external_signals.json",
  "accuracy": {"mase":1.097,"rmsse":0.80,"mape":20.77,"n_points":24,"n_windows_scored":2,"n_windows_excluded_stale":11},
  "trust": {"cov80":0.208,"cov90":0.333},
  "beats_naive": false, "tie": true
}
```

`data/forecast_exploration/bakeoff/manifest.json` has top-level `"last_real_date": "2026-03-01"`.

A `backtest_trajectories.json` (resolved from the ref) is:
```python
{"version": "...", "data": [
  {"forecast_start":"2025-03-01", "forecast_end":"2026-02-01", "metrics":{...},
   "forecast_series": {"2025-03-01": {"actual":0.3945, "quantile_forecast":{"0.05":..,"0.50":..,"0.95":..}}, ...}}
  ...  # 13 windows; only windows with forecast_end <= last_real_date are scorable (2 of them)
]}
```

**Key reuse — existing signatures (do NOT reimplement):**
- `forecast_scoring.extract_scorable_points(traj, last_real_date) -> (points, n_scored, n_excluded)` where `points` is `[(actual_float, quantile_dict)]`; quantile_dict keys are `"0.05".."0.95"`.
- `forecast_scoring.band_coverage(points, lo_key, hi_key) -> float` (keys like `"0.10"`).
- `recalibration.residuals_from_points(points) -> [actual - P50]`.
- `recalibration.residual_offsets(residuals) -> {tau_float: offset}` (taus 0.05..0.95).
- `recalibration.recalibrate_block(block, offsets) -> {date: {pXX: float}}` (reads only `band["p50"]`, emits all 19 quantiles; pure, no mutation).
- `recalibration.coverage_with_offsets(points, offsets, 0.10, 0.90) -> float`.
- `trust.trust_from_metrics(metrics) -> {score,label,calibration,skill,accuracy}` — needs keys `cov80, cov90, mase, mape`.
- `decision.Persona(monthly_demand_t, current_stock_t=0.0, carrying_cost_pct_yr=0.18, risk_quantile="p50")` — frozen dataclass; `.monthly_carry`, `.runway_months` properties.
- `decision.solve(forecast_block, persona) -> OrderPlan` with fields `months, prices, orders_t, purchase_for, optimal_cost, baseline_cost, savings, savings_pct, recommendation, target_month, rationale`. `purchase_for` maps `demand_month_date -> purchase_month_date`. `decision.KG_PER_TONNE == 1000.0`.
- `ts_utils.month_index(date_str) -> int`.

**Invariants that hold by construction (use in tests):**
- `decision.solve` never does worse than buy-as-you-go → `plan.savings >= 0` on any forecast block.
- Perfect-hindsight saving is an upper bound → for every backtest window, realized `saving <= ceiling_saving` (+ float epsilon).

---

## File Structure

- Create `lib/pipeline.py` — champion loading, per-fertilizer recalibrate→trust→solve, `run_all`, trust-hero pick, persona preset, EUR FX. One responsibility: orchestrate the per-fertilizer forward decision.
- Create `lib/impact.py` — Tier-1 rigorous hindcast backtest + perfect-hindsight ceiling. One responsibility: historical validation of the policy.
- Create `lib/shocks.py` — corrected-band level shift + decision diff. One responsibility: the adaptive shock transform.
- Create `scripts/pipeline_report.py` — headless wiring + printout for manual verification (not imported by other modules).
- Create `tests/test_pipeline.py`, `tests/test_impact.py`, `tests/test_shocks.py`.

---

## Task 1: `lib/pipeline.py` — per-fertilizer forward decision + trust-hero

**Files:**
- Create: `lib/pipeline.py`
- Test: `tests/test_pipeline.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_pipeline.py`:
```python
import unittest
from lib import pipeline
from lib import decision as dc

SLUGS = {"urea", "dap", "mop", "tsp", "phosphate-rock"}


class TestPipeline(unittest.TestCase):
    def test_persona_runway(self):
        p = pipeline.AUSTRIAN_UREA_PERSONA
        self.assertEqual(p.monthly_demand_t, 1000.0)
        self.assertEqual(p.runway_months, 3.0)

    def test_last_real_date_from_manifest(self):
        self.assertEqual(pipeline.load_manifest()["last_real_date"], "2026-03-01")

    def test_run_all_covers_five_fertilizers(self):
        run = pipeline.run_all()
        self.assertEqual(set(run["results"].keys()), SLUGS)
        self.assertIn(run["hero"], SLUGS)

    def test_each_result_shape_and_savings_nonnegative(self):
        run = pipeline.run_all()
        for slug, r in run["results"].items():
            self.assertIsInstance(r["plan"], dc.OrderPlan)
            self.assertGreaterEqual(r["plan"].savings, 0.0)        # solve invariant
            self.assertGreaterEqual(r["savings_eur"], 0.0)
            self.assertIn(r["plan"].recommendation,
                          {"BUY_NOW", "WAIT", "SPLIT", "COVERED"})
            self.assertIn(r["trust"]["label"], {"high", "medium", "low"})

    def test_recalibration_lifts_coverage(self):
        # The whole point of recalibration: corrected 80% band covers more of the
        # in-sample actuals than the native band did.
        run = pipeline.run_all()
        cal = run["results"]["urea"]["calibration"]
        self.assertGreater(cal["cov80_corrected"], cal["cov80_native"])

    def test_hero_is_argmax_trust(self):
        run = pipeline.run_all()
        hero_score = run["results"][run["hero"]]["trust"]["score"]
        for r in run["results"].values():
            self.assertLessEqual(r["trust"]["score"], hero_score + 1e-12)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_pipeline -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lib.pipeline'`.

- [ ] **Step 3: Write minimal implementation**

Create `lib/pipeline.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_pipeline -v`
Expected: PASS (6 tests). If `test_recalibration_lifts_coverage` fails, the recalibration math regressed — stop and inspect, do not weaken the assertion.

- [ ] **Step 5: Commit**

```bash
git add lib/pipeline.py tests/test_pipeline.py
git commit -m "feat: per-fertilizer forward decision pipeline + trust-hero pick"
```

---

## Task 2: `lib/impact.py` — Tier-1 rigorous hindcast backtest

This is the rigorous economic-impact proof from spec §4/§9: for each non-stale
hindcast window, recalibrate using leave-one-out residuals (no leakage of that
window's own actuals), solve the schedule on the corrected forecast, then
re-price those exact purchase decisions on the window's REALIZED actuals.
Decide on the forecast, pay on the truth. Add a perfect-hindsight ceiling so we
can say "agent captures N% of achievable savings."

**Files:**
- Create: `lib/impact.py`
- Test: `tests/test_impact.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_impact.py`:
```python
import json
import os
import unittest

from lib import impact
from lib import pipeline

UREA_TRAJ = os.path.join(pipeline.DATA_DIR, "bakeoff", "urea", "OFF",
                         "backtest_trajectories.json")


def _load(path):
    with open(path) as f:
        return json.load(f)


class TestImpact(unittest.TestCase):
    def setUp(self):
        self.traj = _load(UREA_TRAJ)
        self.persona = pipeline.AUSTRIAN_UREA_PERSONA
        self.last_real = "2026-03-01"

    def test_scorable_windows_match_scoring(self):
        # Two windows are non-stale (forecast_end <= last_real_date), matching
        # the champions' n_windows_scored.
        wins = impact._scorable_windows(self.traj, self.last_real)
        self.assertEqual(len(wins), 2)

    def test_backtest_shape(self):
        res = impact.backtest(self.traj, self.last_real, self.persona)
        self.assertEqual(res["n_windows"], 2)
        self.assertEqual(len(res["per_window"]), 2)
        for w in res["per_window"]:
            for key in ("agent_cost", "baseline_cost", "saving",
                        "ceiling_saving", "capture_ratio", "recommendation"):
                self.assertIn(key, w)

    def test_ceiling_bounds_agent_saving(self):
        # Perfect hindsight is an upper bound on any realized policy saving.
        res = impact.backtest(self.traj, self.last_real, self.persona)
        for w in res["per_window"]:
            self.assertLessEqual(w["saving"], w["ceiling_saving"] + 1e-6)

    def test_totals_consistent(self):
        res = impact.backtest(self.traj, self.last_real, self.persona)
        tot = sum(w["saving"] for w in res["per_window"])
        self.assertAlmostEqual(res["total_saving"], tot, places=6)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_impact -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lib.impact'`.

- [ ] **Step 3: Write minimal implementation**

Create `lib/impact.py`:
```python
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
    """Max achievable saving with full knowledge of the realized prices."""
    carry = persona.monthly_carry
    demand = persona.monthly_demand_t
    covered = int(persona.runway_months)
    prices = [actuals[m] for m in months]
    agent = 0.0
    baseline = 0.0
    for d in range(covered, len(months)):
        best = prices[d]  # buy-as-you-go always allowed
        for p in range(d + 1):
            cost = prices[p] * (1.0 + carry * (d - p))
            if cost < best:
                best = cost
        agent += demand * KG * best
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_impact -v`
Expected: PASS (4 tests). The `test_ceiling_bounds_agent_saving` invariant is the correctness guard — if it fails, the realized-cost or ceiling logic is wrong.

- [ ] **Step 5: Commit**

```bash
git add lib/impact.py tests/test_impact.py
git commit -m "feat: Tier-1 rigorous hindcast backtest with perfect-hindsight ceiling"
```

---

## Task 3: `lib/shocks.py` — corrected-band level shift + decision diff

The adaptive moment (spec §9.2/§9.4): a "+30%" price-outlook shock is a uniform
level shift on the **corrected** band; the decision consumes the corrected band
directly, so one transform + re-solve flips the recommendation. `plan_diff`
gives the UI the old→new render.

**Files:**
- Create: `lib/shocks.py`
- Test: `tests/test_shocks.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_shocks.py`:
```python
import unittest

from lib import shocks
from lib import pipeline
from lib import decision as dc


class TestLevelShift(unittest.TestCase):
    def test_scales_every_quantile(self):
        block = {"2026-04-01": {"p05": 1.0, "p50": 2.0, "p95": 4.0}}
        out = shocks.level_shift(block, 0.30)
        self.assertAlmostEqual(out["2026-04-01"]["p50"], 2.6)
        self.assertAlmostEqual(out["2026-04-01"]["p95"], 5.2)

    def test_does_not_mutate_input(self):
        block = {"2026-04-01": {"p50": 2.0}}
        shocks.level_shift(block, 0.5)
        self.assertEqual(block["2026-04-01"]["p50"], 2.0)

    def test_rejects_full_drop(self):
        with self.assertRaises(ValueError):
            shocks.level_shift({"d": {"p50": 1.0}}, -1.0)


class TestPlanDiff(unittest.TestCase):
    def test_detects_recommendation_change(self):
        before = dc.OrderPlan([], [], {}, {}, 100.0, 100.0, 0.0, 0.0, "WAIT", "x", "r")
        after = dc.OrderPlan([], [], {}, {}, 80.0, 100.0, 20.0, 0.2, "BUY_NOW", "y", "r")
        diff = shocks.plan_diff(before, after)
        self.assertTrue(diff["changed"])
        self.assertEqual(diff["recommendation"], ("WAIT", "BUY_NOW"))
        self.assertAlmostEqual(diff["savings_delta"], 20.0)


class TestShockIntegration(unittest.TestCase):
    def test_shock_resolves_on_hero(self):
        run = pipeline.run_all()
        hero = run["results"][run["hero"]]
        corrected = hero["calibration"]["corrected"]
        persona = pipeline.AUSTRIAN_UREA_PERSONA
        before = dc.solve(corrected, persona)
        after = dc.solve(shocks.level_shift(corrected, 0.30), persona)
        diff = shocks.plan_diff(before, after)
        self.assertGreaterEqual(after.savings, 0.0)
        self.assertIn("changed", diff)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_shocks -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'lib.shocks'`.

- [ ] **Step 3: Write minimal implementation**

Create `lib/shocks.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_shocks -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/shocks.py tests/test_shocks.py
git commit -m "feat: forecast level-shift shock + decision diff for adaptive re-solve"
```

---

## Task 4: `scripts/pipeline_report.py` — headless verification wiring

A small runnable script that wires the three modules into a readable summary:
the trust-ranked table across all 5 fertilizers, the hero pick, the forward
decision + forward €-saving, and the hero's backtest headline. Not imported by
any module — it is the manual end-to-end verification artifact.

**Files:**
- Create: `scripts/pipeline_report.py`

- [ ] **Step 1: Write the script**

Create `scripts/pipeline_report.py`:
```python
"""Headless end-to-end report: trust table, hero pick, forward decision, backtest.

Run from the repo root:  python3 -m scripts.pipeline_report
"""
import json
import os

from lib import pipeline
from lib import impact


def _load_traj(champ):
    with open(os.path.join(pipeline.DATA_DIR, champ["backtest_trajectories_ref"])) as f:
        return json.load(f)


def main():
    run = pipeline.run_all()
    persona = pipeline.AUSTRIAN_UREA_PERSONA
    champions = pipeline.load_champions()

    print(f"last_real_date = {run['last_real_date']}   hero = {run['hero']}\n")
    print(f"{'fertilizer':16}{'trust':>7}{'label':>8}{'rec':>9}"
          f"{'target':>12}{'fwd_eur':>12}")
    ranked = sorted(run["results"].values(),
                    key=lambda r: r["trust"]["score"], reverse=True)
    for r in ranked:
        plan = r["plan"]
        print(f"{r['fertilizer']:16}{r['trust']['score']:7.3f}"
              f"{r['trust']['label']:>8}{plan.recommendation:>9}"
              f"{(plan.target_month or '-'):>12}{r['savings_eur']:12.0f}")

    hero = run["results"][run["hero"]]
    cal = hero["calibration"]
    print(f"\nHero {run['hero']}: 80% band coverage "
          f"{cal['cov80_native']:.1%} -> {cal['cov80_corrected']:.1%} after recalibration")

    bt = impact.backtest(_load_traj(champions[run["hero"]]),
                         run["last_real_date"], persona)
    print(f"\nBacktest ({bt['n_windows']} non-stale windows): "
          f"total saving ${bt['total_saving']:,.0f} "
          f"({bt['total_saving_pct']:.1%} vs buy-as-you-go)")
    for w in bt["per_window"]:
        print(f"  {w['forecast_start']}->{w['forecast_end']}: "
              f"{w['recommendation']:8} saving ${w['saving']:,.0f} "
              f"capture {w['capture_ratio']:.0%}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the report and verify output**

Run: `python3 -m scripts.pipeline_report`
Expected: a trust table with 5 rows (sorted high→low trust), a hero line showing the coverage lift (native% → corrected%, corrected should be higher), and a backtest block with 2 windows and a total saving figure. No traceback. Eyeball that recommendations are in {BUY_NOW, WAIT, SPLIT, COVERED} and `fwd_eur >= 0`.

- [ ] **Step 3: Run the full suite to confirm nothing regressed**

Run: `python3 -m unittest discover -s tests -q`
Expected: `OK`, test count = 91 prior + 15 new = 106.

- [ ] **Step 4: Commit**

```bash
git add scripts/pipeline_report.py
git commit -m "feat: headless pipeline report wiring pipeline + impact + shocks"
```

---

## Self-Review (completed during planning)

**Spec coverage (build order §9 steps 1–3):**
- Step 1 "data-loading/caching layer → run all 5 → pick trust-hero" → Task 1 (`run_all`, `hero`).
- Step 2 "two-track impact backtest → real € savings" → Task 2 Tier-1 rigorous track + perfect-hindsight ceiling. *Deferred to the UI plan / stretch:* the supporting "30yr surrogate-forecast replay" illustrative track (spec §9 calls it "supporting (illustrative)"; the rigorous track is the headline and is fully covered here).
- Step 3 "`lib/shocks.py` (level shift on corrected band) + Persona re-solve path" → Task 3 `level_shift` + `plan_diff`; the Persona re-solve path is already `dc.solve(corrected, new_persona)` (Persona is immutable), exercised in Task 3's integration test.
- Q1/Q2/Q3 (timing spine) answered by the recalibrated forward decision (Task 1) + shock re-solve (Task 3). Native-vs-corrected coverage (visible reasoning) surfaced via `calibration` dict (Task 1) and the report (Task 4).

**Explicitly out of scope for this plan (separate follow-up plan):** build-order steps 4 (Streamlit + Plotly UI) and 5 (Claude chat shell), the landed-cost sourcing calculator (Q4/Q5), and the drivers layer (Q6–Q8, needs a separate trimmed driver-forecast config — `external_signals.json` is empty in the bake-off data). The 30yr surrogate-replay illustrative backtest is a stretch.

**Placeholder scan:** none — every code step is complete and runnable.

**Type consistency:** `recalibrate_champion` returns `corrected` consumed by `dc.solve` and `shocks.level_shift`; `run_fertilizer` result keys (`calibration`, `trust`, `plan`, `savings_eur`) match every test and the report's access. `plan.purchase_for` / `plan.months` usage in `impact._realized_cost` matches the `OrderPlan` definition. `trust_from_metrics` is fed the merged `accuracy`+`trust` dict providing exactly `cov80, cov90, mase, mape`.
