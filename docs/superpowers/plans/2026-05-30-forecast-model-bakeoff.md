# Forecast Model Bake-off Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select the best Sybilion forecast configuration per fertilizer by backtest accuracy, and package the raw winning forecasts as `champions.json` for the procurement agent.

**Architecture:** A pure-stdlib scoring library (`lib/forecast_scoring.py`) computes MASE/RMSSE/MAPE of each cell's hindcast (P50 = `quantile_forecast["0.50"]`) versus a lag-12 seasonal-naive baseline, excluding stale backtest windows. An operator runbook submits 15 fresh backtested `soft_horizon=12` Sybilion jobs (3 recency variants × 5 fertilizers) via the `mcp__sybilion__*` tools and saves their artifacts. `score_bakeoff.py` ranks the variants per fertilizer and emits `BAKEOFF_RESULTS.md` + `champions.json`.

**Tech Stack:** Python 3.14 stdlib only (NO numpy/pandas/pip — matches the existing pipeline), `unittest`, Sybilion MCP tools.

**Spec:** `docs/superpowers/specs/2026-05-30-forecast-model-bakeoff-design.md`

**Key facts confirmed before planning:**
- `backtest_trajectories.json` shape: `{"data": [ {"forecast_end": "YYYY-MM-DD", "forecast_series": {"YYYY-MM-DD": {"actual": float|null, "quantile_forecast": {"0.05":..,"0.50":..,"0.95":..}}}} ]}`. Backtest months carry `actual` + `quantile_forecast` only — **P50 = `quantile_forecast["0.50"]`** (no mean in backtest windows).
- `forecast.json` shape: `{"data": {"forecast_start":.., "forecast_end":.., "forecast_series": {"YYYY-MM-DD": {"forecast": mean, "quantile_forecast": {19 levels}}}}}`.
- `last_real_date = 2026-03-01` (all dataset1 series, 360 monthly points).
- **The spec's reuse caveat fires:** D3 MOP (`1517c8d1`) ran `backtest=false` (no trajectories) and urea Run A (`59b5874f`) ran `soft_horizon=6` (6-month windows, not comparable to 12). So **all 15 cells are fresh `backtest=true, soft_horizon=12` runs**; the paid D3 `external_signals.json` is kept only as a drivers cross-check, and WTI (`b6127f17`) stays as driver-mechanism reference.
- `math` is importable, but follow the codebase style and use `** 0.5` for square roots.
- Test runner: `python3 -m unittest tests.test_forecast_scoring -v` (single module) / `python3 -m unittest discover -s tests -q` (all).

**Fertilizers:** `urea`, `dap`, `mop`, `tsp`, `phosphate-rock` · **Variants:** `ON` (recency=0.0), `MID` (recency=0.3), `OFF` (recency default, omitted).

---

## File Structure

| File | Responsibility |
|---|---|
| `lib/forecast_scoring.py` (create) | Pure scoring functions: seasonal-naive scale, stale-window exclusion, MASE/RMSSE/MAPE/coverage, cell scoring, variant ranking, payload builder, forecast block extractor. |
| `tests/test_forecast_scoring.py` (create) | Unit tests for every function in `lib/forecast_scoring.py`. |
| `build_payloads.py` (create) | CLI: writes one submit payload JSON per cell to `data/forecast_exploration/bakeoff/payloads/` + a `manifest.json` skeleton. |
| `score_bakeoff.py` (create) | CLI: walks the bake-off dir, scores + ranks all cells, writes `BAKEOFF_RESULTS.md` + `champions.json`. |
| `data/forecast_exploration/bakeoff/` (create, runbook) | `manifest.json`, `payloads/`, `<fertilizer>/<variant>/{forecast,backtest_trajectories,external_signals}.json`, outputs. |
| `data/forecast_exploration/FINDINGS.md` (modify) | Append bake-off results section. |

---

## Task 1: Seasonal-naive scale functions

**Files:**
- Create: `lib/forecast_scoring.py`
- Test: `tests/test_forecast_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
import unittest
from lib import forecast_scoring as fs
from lib import ts_utils as tu


class TestSeasonalNaive(unittest.TestCase):
    def test_naive_mae_lag(self):
        series = {"2020-01-01": 10.0, "2020-02-01": 12.0,
                  "2020-03-01": 11.0, "2020-04-01": 15.0}
        # lag-2 diffs: |11-10|=1, |15-12|=3 -> mean 2.0
        self.assertAlmostEqual(fs.seasonal_naive_mae(series, season=2), 2.0)

    def test_naive_rmse_lag(self):
        series = {"2020-01-01": 10.0, "2020-02-01": 12.0,
                  "2020-03-01": 11.0, "2020-04-01": 15.0}
        # sqrt((1 + 9)/2) = sqrt(5)
        self.assertAlmostEqual(fs.seasonal_naive_rmse(series, season=2), 5.0 ** 0.5)

    def test_naive_too_short_raises(self):
        with self.assertRaises(ValueError):
            fs.seasonal_naive_mae({"2020-01-01": 1.0}, season=2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_forecast_scoring.TestSeasonalNaive -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'lib.forecast_scoring'`.

- [ ] **Step 3: Write minimal implementation**

Create `lib/forecast_scoring.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_forecast_scoring.TestSeasonalNaive -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/forecast_scoring.py tests/test_forecast_scoring.py
git commit -m "feat: seasonal-naive scale functions for forecast scoring"
```

---

## Task 2: Stale-window exclusion + point extraction

**Files:**
- Modify: `lib/forecast_scoring.py`
- Test: `tests/test_forecast_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
class TestExtractPoints(unittest.TestCase):
    def _traj(self):
        return {"data": [
            {"forecast_end": "2025-08-01", "forecast_series": {
                "2025-07-01": {"actual": 10.0, "quantile_forecast": {"0.50": 8.0}},
                "2025-08-01": {"actual": 20.0, "quantile_forecast": {"0.50": 16.0}},
            }},
            {"forecast_end": "2026-09-01", "forecast_series": {  # STALE: past last_real
                "2026-09-01": {"actual": None, "quantile_forecast": {"0.50": 1.0}},
            }},
        ]}

    def test_excludes_stale_window(self):
        pts, scored, excluded = fs.extract_scorable_points(self._traj(), "2026-03-01")
        self.assertEqual(scored, 1)
        self.assertEqual(excluded, 1)
        self.assertEqual(len(pts), 2)
        self.assertEqual(pts[0], (10.0, {"0.50": 8.0}))

    def test_skips_none_actual_in_kept_window(self):
        traj = {"data": [
            {"forecast_end": "2025-08-01", "forecast_series": {
                "2025-07-01": {"actual": None, "quantile_forecast": {"0.50": 8.0}},
                "2025-08-01": {"actual": 20.0, "quantile_forecast": {"0.50": 16.0}},
            }},
        ]}
        pts, scored, excluded = fs.extract_scorable_points(traj, "2026-03-01")
        self.assertEqual((scored, excluded, len(pts)), (1, 0, 1))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_forecast_scoring.TestExtractPoints -v`
Expected: FAIL — `AttributeError: module 'lib.forecast_scoring' has no attribute 'extract_scorable_points'`.

- [ ] **Step 3: Write minimal implementation**

Append to `lib/forecast_scoring.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_forecast_scoring.TestExtractPoints -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/forecast_scoring.py tests/test_forecast_scoring.py
git commit -m "feat: stale-window exclusion + scorable-point extraction"
```

---

## Task 3: Point metrics — MAE/RMSE/MAPE/coverage

**Files:**
- Modify: `lib/forecast_scoring.py`
- Test: `tests/test_forecast_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
class TestPointMetrics(unittest.TestCase):
    POINTS = [
        (10.0, {"0.05": 4.0, "0.10": 5.0, "0.50": 8.0, "0.90": 9.0, "0.95": 9.5}),
        (20.0, {"0.05": 12.0, "0.10": 14.0, "0.50": 16.0, "0.90": 22.0, "0.95": 25.0}),
    ]

    def test_mae(self):
        self.assertAlmostEqual(fs.mae_points(self.POINTS), 3.0)  # (2+4)/2

    def test_rmse(self):
        self.assertAlmostEqual(fs.rmse_points(self.POINTS), 10.0 ** 0.5)  # sqrt((4+16)/2)

    def test_mape(self):
        # (0.2 + 0.2)/2 * 100
        self.assertAlmostEqual(fs.mape_points(self.POINTS), 20.0)

    def test_coverage_80(self):
        # pt1: 5..9 does NOT cover 10 -> miss; pt2: 14..22 covers 20 -> hit => 0.5
        self.assertAlmostEqual(fs.band_coverage(self.POINTS, *fs.BAND_80), 0.5)

    def test_coverage_90(self):
        # pt1: 4..9.5 misses 10; pt2: 12..25 covers 20 => 0.5
        self.assertAlmostEqual(fs.band_coverage(self.POINTS, *fs.BAND_90), 0.5)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            fs.mae_points([])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_forecast_scoring.TestPointMetrics -v`
Expected: FAIL — `AttributeError: ... has no attribute 'mae_points'`.

- [ ] **Step 3: Write minimal implementation**

Append to `lib/forecast_scoring.py`:

```python
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
    usable = [(a, q) for a, q in points if a != 0]
    if not usable:
        raise ValueError("no nonzero actuals for MAPE")
    return sum(abs(a - _p50(q)) / abs(a) for a, q in usable) / len(usable) * 100.0


def band_coverage(points, lo_key, hi_key):
    if not points:
        raise ValueError("no scorable points")
    covered = sum(1 for a, q in points if float(q[lo_key]) <= a <= float(q[hi_key]))
    return covered / len(points)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_forecast_scoring.TestPointMetrics -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/forecast_scoring.py tests/test_forecast_scoring.py
git commit -m "feat: point metrics (MAE/RMSE/MAPE/band coverage)"
```

---

## Task 4: Cell scoring + variant ranking

**Files:**
- Modify: `lib/forecast_scoring.py`
- Test: `tests/test_forecast_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
class TestScoreAndRank(unittest.TestCase):
    def test_score_cell(self):
        # series rises by 1/month for 24 months -> y_t - y_{t-12} == 12 always
        series = {tu.index_to_month(24240 + i): float(i) for i in range(24)}
        last_real = tu.index_to_month(24240 + 23)
        traj = {"data": [
            {"forecast_end": tu.index_to_month(24240 + 10), "forecast_series": {
                tu.index_to_month(24240 + 9): {
                    "actual": 10.0,
                    "quantile_forecast": {"0.05": 4.0, "0.10": 5.0, "0.50": 8.0,
                                          "0.90": 9.0, "0.95": 9.5}},
                tu.index_to_month(24240 + 10): {
                    "actual": 20.0,
                    "quantile_forecast": {"0.05": 12.0, "0.10": 14.0, "0.50": 16.0,
                                          "0.90": 22.0, "0.95": 25.0}},
            }},
        ]}
        m = fs.score_cell(series, traj, last_real)
        self.assertAlmostEqual(m["mase"], 3.0 / 12.0)        # mae 3 / naive 12
        self.assertAlmostEqual(m["rmsse"], (10.0 ** 0.5) / 12.0)
        self.assertAlmostEqual(m["mape"], 20.0)
        self.assertEqual(m["n_points"], 2)
        self.assertEqual(m["n_windows_scored"], 1)
        self.assertEqual(m["n_windows_excluded_stale"], 0)

    def test_rank_by_mase_then_mape(self):
        cells = {
            "ON": {"mase": 0.5, "mape": 10.0},
            "MID": {"mase": 0.3, "mape": 12.0},
            "OFF": {"mase": 0.3, "mape": 8.0},
        }
        winner, ordered = fs.rank_variants(cells)
        self.assertEqual(winner, "OFF")          # tie on mase -> lower mape wins
        self.assertEqual(ordered, ["OFF", "MID", "ON"])

    def test_rank_puts_none_last(self):
        cells = {"ON": {"mase": 0.5, "mape": 10.0}, "BAD": None}
        winner, ordered = fs.rank_variants(cells)
        self.assertEqual(winner, "ON")
        self.assertEqual(ordered[-1], "BAD")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_forecast_scoring.TestScoreAndRank -v`
Expected: FAIL — `AttributeError: ... has no attribute 'score_cell'`.

- [ ] **Step 3: Write minimal implementation**

Append to `lib/forecast_scoring.py`:

```python
def score_cell(series, trajectories, last_real_date):
    """Full metric bundle for one cell. Returns a dict of metrics."""
    points, n_scored, n_excluded = extract_scorable_points(trajectories, last_real_date)
    naive_mae = seasonal_naive_mae(series)
    naive_rmse = seasonal_naive_rmse(series)
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
    def key(item):
        _v, m = item
        if m is None:
            return (float("inf"), float("inf"))
        return (m["mase"], m["mape"])
    ordered = sorted(cells.items(), key=key)
    return ordered[0][0], [v for v, _m in ordered]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_forecast_scoring.TestScoreAndRank -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add lib/forecast_scoring.py tests/test_forecast_scoring.py
git commit -m "feat: cell scoring bundle + variant ranking"
```

---

## Task 5: Forecast-block extractor (for champions.json)

**Files:**
- Modify: `lib/forecast_scoring.py`
- Test: `tests/test_forecast_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
class TestForecastBlock(unittest.TestCase):
    def test_block_maps_quantiles_to_p_keys(self):
        forecast_json = {"data": {"forecast_series": {
            "2026-06-01": {"forecast": 0.5, "quantile_forecast": {
                "0.05": 0.4, "0.10": 0.42, "0.50": 0.5, "0.90": 0.58, "0.95": 0.6}},
        }}}
        block = fs.forecast_block(forecast_json)
        self.assertEqual(set(block.keys()), {"2026-06-01"})
        row = block["2026-06-01"]
        self.assertAlmostEqual(row["p50"], 0.5)
        self.assertAlmostEqual(row["p05"], 0.4)
        self.assertAlmostEqual(row["p95"], 0.6)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_forecast_scoring.TestForecastBlock -v`
Expected: FAIL — `AttributeError: ... has no attribute 'forecast_block'`.

- [ ] **Step 3: Write minimal implementation**

Append to `lib/forecast_scoring.py`:

```python
def forecast_block(forecast_json):
    """From forecast.json -> {date: {"p05":.., "p10":.., ..., "p95":..}}.

    Maps each quantile key "0.05".."0.95" to "p05".."p95" (includes "p50").
    """
    series = forecast_json["data"]["forecast_series"]
    out = {}
    for date, entry in series.items():
        q = entry["quantile_forecast"]
        out[date] = {"p" + k[2:]: float(v) for k, v in q.items()}
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_forecast_scoring.TestForecastBlock -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add lib/forecast_scoring.py tests/test_forecast_scoring.py
git commit -m "feat: forecast-block extractor for champions output"
```

---

## Task 6: Payload builder + manifest skeleton

**Files:**
- Modify: `lib/forecast_scoring.py` (add `build_cell_payload`)
- Create: `build_payloads.py`
- Test: `tests/test_forecast_scoring.py`

- [ ] **Step 1: Write the failing test**

```python
class TestBuildPayload(unittest.TestCase):
    def _series(self):
        return {tu.index_to_month(24000 + i): float(i + 1) for i in range(130)}

    def test_on_variant_sets_recency_zero(self):
        p = fs.build_cell_payload("urea", self._series(), "ON")
        self.assertEqual(p["recency_factor"], 0.0)
        self.assertEqual(p["soft_horizon"], 12)
        self.assertTrue(p["backtest"])
        self.assertEqual(p["frequency"], "monthly")
        self.assertEqual(p["pipeline_version"], "v1")
        self.assertGreaterEqual(len(p["timeseries_metadata"]["title"]), 20)

    def test_mid_variant_sets_recency_point_three(self):
        p = fs.build_cell_payload("dap", self._series(), "MID")
        self.assertEqual(p["recency_factor"], 0.3)

    def test_off_variant_omits_recency(self):
        p = fs.build_cell_payload("mop", self._series(), "OFF")
        self.assertNotIn("recency_factor", p)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_forecast_scoring.TestBuildPayload -v`
Expected: FAIL — `AttributeError: ... has no attribute 'build_cell_payload'`.

- [ ] **Step 3: Write minimal implementation**

Append to `lib/forecast_scoring.py`:

```python
FERTILIZERS = ["urea", "dap", "mop", "tsp", "phosphate-rock"]
VARIANTS = ["ON", "MID", "OFF"]
RECENCY = {"ON": 0.0, "MID": 0.3}  # OFF omits recency_factor (API default 0.5)


def build_cell_payload(slug, series, variant):
    """Assemble a submit_forecast payload dict for one bake-off cell.

    variant in VARIANTS. ON/MID set recency_factor; OFF omits it.
    """
    title = (f"World Bank {slug} fertilizer FOB benchmark spot price, "
             "monthly USD per kg")
    payload = {
        "pipeline_version": "v1",
        "frequency": "monthly",
        "soft_horizon": 12,
        "backtest": True,
        "timeseries": series,
        "timeseries_metadata": {
            "title": title[:511],
            "description": (
                f"Monthly {slug} fertilizer benchmark spot price in USD/kg, "
                "World Bank Pink Sheet, 1996-2026. Bake-off variant "
                f"{variant} for a procurement-timing forecast."
            )[:2048],
        },
    }
    if variant in RECENCY:
        payload["recency_factor"] = RECENCY[variant]
    return payload
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_forecast_scoring.TestBuildPayload -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Write `build_payloads.py`**

Create `build_payloads.py`:

```python
"""Generate submit_forecast payloads + a manifest skeleton for the bake-off.

Writes one payload JSON per (fertilizer, variant) cell and an empty manifest
the operator fills in as jobs are submitted. Pure stdlib; no network calls.
"""
import json
import os

from lib import forecast_scoring as fs

PROCESSED = "data/processed/dataset1"
BAKEOFF = "data/forecast_exploration/bakeoff"
LAST_REAL_DATE = "2026-03-01"
REFERENCE_JOBS = {
    "mop_drivers_D3_backtest_false": "1517c8d1-3ddf-479c-aaf5-e062fba00fa6",
    "wti_D4_reference": "b6127f17-e68e-4efe-ad7a-86fa292d9027",
    "urea_runA_sh6": "59b5874f-a40f-465c-b903-b33c5a17dcb1",
}


def load_series(slug):
    with open(os.path.join(PROCESSED, f"{slug}.json")) as fh:
        return json.load(fh)


def main():
    payloads_dir = os.path.join(BAKEOFF, "payloads")
    os.makedirs(payloads_dir, exist_ok=True)
    cells = {}
    for slug in fs.FERTILIZERS:
        series = load_series(slug)
        cells[slug] = {}
        for variant in fs.VARIANTS:
            payload = fs.build_cell_payload(slug, series, variant)
            path = os.path.join(payloads_dir, f"{slug}__{variant}.json")
            with open(path, "w") as fh:
                json.dump(payload, fh)
            cells[slug][variant] = {"job_id": None, "status": "pending",
                                    "eur_cost": None}
    manifest = {
        "config": {"soft_horizon": 12, "backtest": True,
                   "accept_stale_latest_data": True,
                   "recency_factor": {"ON": 0.0, "MID": 0.3, "OFF": None}},
        "last_real_date": LAST_REAL_DATE,
        "reference_jobs": REFERENCE_JOBS,
        "cells": cells,
    }
    with open(os.path.join(BAKEOFF, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(f"Wrote {len(fs.FERTILIZERS) * len(fs.VARIANTS)} payloads + manifest skeleton")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run the generator and verify output**

Run: `python3 build_payloads.py && ls data/forecast_exploration/bakeoff/payloads/ | wc -l`
Expected: prints "Wrote 15 payloads + manifest skeleton" and `15`.

- [ ] **Step 7: Commit**

```bash
git add lib/forecast_scoring.py build_payloads.py tests/test_forecast_scoring.py \
        data/forecast_exploration/bakeoff/payloads data/forecast_exploration/bakeoff/manifest.json
git commit -m "feat: bake-off payload builder + manifest skeleton"
```

---

## Task 7: OPERATOR RUNBOOK — submit jobs + save artifacts

> **Not TDD.** This task is executed by the agent via the `mcp__sybilion__*` tools (no Python entry point — the MCP tools are not callable from scripts here). Work the 15 cells; submit the slow ones first so they run while you handle the rest. Money is not a constraint (~€10k, the €10k tranche expires **2026-06-01**); wall-clock is.

**Files:**
- Modify: `data/forecast_exploration/bakeoff/manifest.json`
- Create: `data/forecast_exploration/bakeoff/<fertilizer>/<variant>/{forecast,backtest_trajectories,external_signals}.json`

- [ ] **Step 1: Dry-run validate every payload (free, no credits)**

For each of the 15 files in `bakeoff/payloads/`, call `mcp__sybilion__validate_forecast_data` with that payload's fields plus `accept_stale_latest_data: true`. Expected: all pass (urea + phosphate-rock are documented to pass at `soft_horizon=12` with the stale flag; the other three share the same 360-pt monthly shape). If any fails, fix the payload and re-run `build_payloads.py` before submitting — do NOT submit a failing payload.

- [ ] **Step 2: Submit the 10 slow cells first (ON + MID)**

For each `(slug, variant)` in the 5 fertilizers × {ON, MID}: call `mcp__sybilion__submit_forecast` with the payload fields plus `accept_stale_latest_data: true`. Record the returned job UUID into `manifest.json` at `cells[slug][variant].job_id` and set `status` to `"running"`. These use `recency_factor` 0.0/0.3 and run ~8–20 min each.

- [ ] **Step 3: Submit the 5 fast cells (OFF)**

For each `(slug, "OFF")`: submit the payload (no `recency_factor`) plus `accept_stale_latest_data: true`. Record job_id + `status="running"`. These run ~3 min.

- [ ] **Step 4: Poll each job to completion**

For each running job, call `mcp__sybilion__get_forecast(job_id)` and let the MCP's built-in spacing pace the polls — **do NOT use Bash `sleep`**. On `status=="failed"`: pull `errors.json` via `get_forecast_artifact`, write the message into `manifest.json` at `cells[slug][variant].error`, set `status="failed"`, and continue (a failed cell becomes a `None`-metric variant in scoring). On `status=="completed"`: proceed to Step 5.

- [ ] **Step 5: Pull and save artifacts for each completed job**

For each completed `(slug, variant)`, create `data/forecast_exploration/bakeoff/<slug>/<variant>/` and save the **raw inner JSON** (the `{...}` object, not the MCP markdown wrapper) of:
- `forecast.json` ← `get_forecast_artifact(job_id, "forecast.json")`
- `backtest_trajectories.json` ← `get_forecast_artifact(job_id, "backtest_trajectories.json")`
- `external_signals.json` ← `get_forecast_artifact(job_id, "external_signals.json")` (will be `{}` for OFF cells; populated for ON, maybe MID)

Set `status="completed"` in the manifest.

- [ ] **Step 6: Record costs**

Call `mcp__sybilion__get_usage(page=1, limit=50, sort="created_at", order="desc")`, match each `async_job_id` to its cell, and write `eur_cost = eur_cents_charged / 100` into `manifest.json`.

- [ ] **Step 7: Sanity-check the saved artifacts**

Run:
```bash
python3 -c "
import json, glob
for f in sorted(glob.glob('data/forecast_exploration/bakeoff/*/*/backtest_trajectories.json')):
    d = json.load(open(f))
    assert 'data' in d and isinstance(d['data'], list), f
    print(f, 'windows=', len(d['data']))
"
```
Expected: one line per completed cell, each with a window count > 0.

- [ ] **Step 8: Commit**

```bash
git add data/forecast_exploration/bakeoff
git commit -m "data: bake-off forecast artifacts (15 cells) + filled manifest"
```

---

## Task 8: `score_bakeoff.py` — champions.json + BAKEOFF_RESULTS.md

**Files:**
- Create: `score_bakeoff.py`
- Test: `tests/test_forecast_scoring.py` (integration test on a tmp dir)

- [ ] **Step 1: Write the failing integration test**

```python
import json
import os
import tempfile


class TestScoreBakeoffIntegration(unittest.TestCase):
    def test_assemble_picks_lower_mase_winner(self):
        import score_bakeoff
        series = {tu.index_to_month(24240 + i): float(i) for i in range(24)}
        last_real = tu.index_to_month(24240 + 23)

        def traj(p50_a, p50_b):
            return {"data": [{"forecast_end": tu.index_to_month(24240 + 10),
                "forecast_series": {
                    tu.index_to_month(24240 + 9): {"actual": 10.0,
                        "quantile_forecast": {"0.05": 4.0, "0.10": 5.0,
                            "0.50": p50_a, "0.90": 9.0, "0.95": 9.5}},
                    tu.index_to_month(24240 + 10): {"actual": 20.0,
                        "quantile_forecast": {"0.05": 12.0, "0.10": 14.0,
                            "0.50": p50_b, "0.90": 22.0, "0.95": 25.0}},
                }}]}

        fcast = {"data": {"forecast_series": {"2026-06-01": {"forecast": 0.5,
            "quantile_forecast": {"0.05": 0.4, "0.10": 0.42, "0.50": 0.5,
                                  "0.90": 0.58, "0.95": 0.6}}}}}

        with tempfile.TemporaryDirectory() as tmp:
            proc = os.path.join(tmp, "processed")
            bake = os.path.join(tmp, "bakeoff")
            os.makedirs(proc)
            with open(os.path.join(proc, "urea.json"), "w") as fh:
                json.dump(series, fh)
            # OFF is near-perfect (p50 ~ actual); ON is far -> OFF must win
            variants = {"ON": traj(2.0, 2.0), "MID": traj(6.0, 12.0),
                        "OFF": traj(10.0, 20.0)}
            for v, t in variants.items():
                d = os.path.join(bake, "urea", v)
                os.makedirs(d)
                json.dump(t, open(os.path.join(d, "backtest_trajectories.json"), "w"))
                json.dump(fcast, open(os.path.join(d, "forecast.json"), "w"))
            manifest = {"last_real_date": last_real, "cells": {"urea": {
                "ON": {"job_id": "a", "status": "completed"},
                "MID": {"job_id": "b", "status": "completed"},
                "OFF": {"job_id": "c", "status": "completed"}}}}
            json.dump(manifest, open(os.path.join(bake, "manifest.json"), "w"))

            champions, md = score_bakeoff.assemble(
                manifest, proc, bake, fertilizers=["urea"])

        self.assertEqual(champions["urea"]["winner_variant"], "OFF")
        self.assertTrue(champions["urea"]["beats_naive"])  # OFF mase < 1
        self.assertIn("2026-06-01", champions["urea"]["forecast"])
        self.assertIn("urea", md)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_forecast_scoring.TestScoreBakeoffIntegration -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'score_bakeoff'`.

- [ ] **Step 3: Write `score_bakeoff.py`**

Create `score_bakeoff.py`:

```python
"""Score the bake-off: rank variants per fertilizer, emit champions + report.

Reads data/forecast_exploration/bakeoff/manifest.json + saved artifacts, scores
each cell with lib.forecast_scoring, picks the lowest-MASE config per fertilizer,
and writes champions.json (agent input contract) + BAKEOFF_RESULTS.md.
"""
import json
import os

from lib import forecast_scoring as fs

PROCESSED = "data/processed/dataset1"
BAKEOFF = "data/forecast_exploration/bakeoff"


def _load(path):
    with open(path) as fh:
        return json.load(fh)


def _score_variant(series, bake_dir, slug, variant, last_real):
    traj_path = os.path.join(bake_dir, slug, variant, "backtest_trajectories.json")
    if not os.path.exists(traj_path):
        return None
    try:
        return fs.score_cell(series, _load(traj_path), last_real)
    except (ValueError, KeyError):
        return None


def assemble(manifest, processed_dir, bake_dir, fertilizers=None):
    """Return (champions_dict, markdown_report). Pure given the inputs/dirs."""
    fertilizers = fertilizers or fs.FERTILIZERS
    last_real = manifest["last_real_date"]
    champions = {}
    rows = []
    for slug in fertilizers:
        series = _load(os.path.join(processed_dir, f"{slug}.json"))
        cells = {v: _score_variant(series, bake_dir, slug, v, last_real)
                 for v in fs.VARIANTS}
        winner, ordered = fs.rank_variants(cells)
        wm = cells[winner]
        fcast = _load(os.path.join(bake_dir, slug, winner, "forecast.json"))
        champions[slug] = {
            "winner_variant": winner,
            "job_id": manifest["cells"][slug][winner].get("job_id"),
            "config": {"recency_factor": fs.RECENCY.get(winner),
                       "soft_horizon": 12, "backtest": True,
                       "accept_stale_latest_data": True},
            "forecast": fs.forecast_block(fcast),
            "backtest_trajectories_ref":
                f"bakeoff/{slug}/{winner}/backtest_trajectories.json",
            "external_signals_ref":
                f"bakeoff/{slug}/{winner}/external_signals.json",
            "accuracy": {k: wm[k] for k in ("mase", "rmsse", "mape", "n_points",
                                            "n_windows_scored",
                                            "n_windows_excluded_stale")},
            "trust": {"cov80": wm["cov80"], "cov90": wm["cov90"]},
            "beats_naive": wm["mase"] < 1.0,
        }
        rows.append((slug, winner, ordered, cells))
    return champions, _render_markdown(rows)


def _render_markdown(rows):
    out = ["# Bake-off results\n",
           "Winner per fertilizer = lowest MASE (tiebreak MAPE), scored from",
           "backtest_trajectories.json with stale windows excluded. MASE/RMSSE < 1",
           "means the config beats a lag-12 seasonal-naive baseline.\n",
           "| fertilizer | winner | MASE | RMSSE | MAPE% | cov80 | cov90 | beats naive? |",
           "|---|---|---|---|---|---|---|---|"]
    for slug, winner, _ordered, cells in rows:
        m = cells[winner]
        out.append(f"| {slug} | {winner} | {m['mase']:.2f} | {m['rmsse']:.2f} | "
                   f"{m['mape']:.1f} | {m['cov80']:.0%} | {m['cov90']:.0%} | "
                   f"{'YES' if m['mase'] < 1.0 else 'no'} |")
    out.append("\n## Per-variant detail\n")
    for slug, winner, ordered, cells in rows:
        out.append(f"### {slug} (winner: {winner})")
        for v in ordered:
            m = cells[v]
            if m is None:
                out.append(f"- {v}: no data (failed or missing)")
            else:
                out.append(f"- {v}: MASE {m['mase']:.2f}, MAPE {m['mape']:.1f}%, "
                           f"cov80 {m['cov80']:.0%}, "
                           f"{m['n_windows_excluded_stale']} stale windows excluded")
    return "\n".join(out) + "\n"


def main():
    manifest = _load(os.path.join(BAKEOFF, "manifest.json"))
    champions, md = assemble(manifest, PROCESSED, BAKEOFF)
    with open(os.path.join(BAKEOFF, "champions.json"), "w") as fh:
        json.dump(champions, fh, indent=2)
    with open(os.path.join(BAKEOFF, "BAKEOFF_RESULTS.md"), "w") as fh:
        fh.write(md)
    print("Wrote champions.json + BAKEOFF_RESULTS.md")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_forecast_scoring.TestScoreBakeoffIntegration -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m unittest discover -s tests -q`
Expected: OK, test count = 36 (existing) + the new scoring tests.

- [ ] **Step 6: Generate the real outputs (after Task 7 artifacts exist)**

Run: `python3 score_bakeoff.py && python3 -c "import json;print(json.dumps({k:v['winner_variant'] for k,v in json.load(open('data/forecast_exploration/bakeoff/champions.json')).items()}, indent=2))"`
Expected: prints "Wrote champions.json + BAKEOFF_RESULTS.md" then the winning variant per fertilizer.

- [ ] **Step 7: Commit**

```bash
git add score_bakeoff.py tests/test_forecast_scoring.py \
        data/forecast_exploration/bakeoff/champions.json \
        data/forecast_exploration/bakeoff/BAKEOFF_RESULTS.md
git commit -m "feat: bake-off scorer -> champions.json + results report"
```

---

## Task 9: Update FINDINGS.md + project memory

**Files:**
- Modify: `data/forecast_exploration/FINDINGS.md`
- Modify: `/home/vscode/.claude/projects/-workspaces-zero-one-hack-01/memory/fertilizer-data-engineering-pipeline.md` (+ MEMORY.md pointer if a new memory is warranted)

- [ ] **Step 1: Append a bake-off section to FINDINGS.md**

Add a section titled `## Bake-off (2026-05-30): best config per fertilizer` summarizing, from `BAKEOFF_RESULTS.md`: the winning variant per fertilizer, whether any config **beat seasonal-naive** (MASE < 1), the band-coverage trust caveat, and the phosphate-rock degeneracy note. Quote actual numbers from the generated report — no placeholders.

- [ ] **Step 2: Update the project memory**

In `fertilizer-data-engineering-pipeline.md`, append one line recording: the bake-off ran 15 fresh `sh=12 backtest=true` cells (3 recency variants × 5 fertilizers), the winner-selection rule (lowest MASE vs lag-12 seasonal-naive, stale windows excluded), that `champions.json` is the agent's input contract, and the headline beat-naive verdict. Keep it factual and short.

- [ ] **Step 3: Commit**

```bash
git add data/forecast_exploration/FINDINGS.md
git commit -m "docs: record bake-off results + winning configs"
```

---

## Self-Review notes (addressed)

- **Spec coverage:** Tier-1 set = OFF cells (Task 6/7); Tier-2 bake-off = all 15 cells (Task 7); MASE-vs-seasonal-naive selection with stale exclusion (Tasks 1–4); `champions.json` contract incl. `backtest_trajectories_ref`/`external_signals_ref`/`beats_naive` (Task 8); `BAKEOFF_RESULTS.md` with beat-naive verdict + phosphate-rock honesty (Task 8/9); `manifest.json` source of truth (Task 6/7); FINDINGS + memory (Task 9). Recalibration/trust-solver explicitly out of scope (lives in the agent spec).
- **Reuse caveat resolved:** D3 was `backtest=false` and Run A was `sh=6`, so all 15 cells are fresh — recorded in the header and Task 7; reference jobs retained in the manifest only.
- **Type consistency:** `score_cell` emits `mase/rmsse/mape/cov80/cov90/n_points/n_windows_scored/n_windows_excluded_stale`; `rank_variants`, `assemble`, and `_render_markdown` consume exactly those keys. `forecast_block` emits `p05..p95` keys consumed by `champions.json`. `FERTILIZERS`/`VARIANTS`/`RECENCY` defined once in `lib/forecast_scoring.py` and reused by both scripts.
- **soft_horizon=12** consistent across payload builder, manifest config, and champions config.
