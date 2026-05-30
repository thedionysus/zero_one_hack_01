# Forecast Model Bake-off — Design Spec

**Date:** 2026-05-30 · **Track:** Forecasting AI (Sybilion) · **Branch:** `feat/data-engineering-prep`
**Status:** design approved, ready for implementation plan

Produces the **forecasting models** that feed the Fertilizer Procurement Decision Agent
(`docs/superpowers/specs/2026-05-30-fertilizer-procurement-agent-design.md`). Source context:
`data/forecast_exploration/FINDINGS.md`, `data/forecast_exploration/diag/DIAG_FINDINGS.md`,
the two project memories (fertilizer-data-engineering-pipeline, sybilion-stale-data-backtest-gotcha).

---

## 1. What "a model" means here (scope)

We do **not** train anything locally — this devcontainer's Python is stripped (no numpy/pandas/pip).
**A "model" = one Sybilion forecast configuration.** We submit a fertilizer's monthly price history plus
settings; Sybilion returns a forecast (point **P50 + 19 quantile bands P05–P95** per month) and, with
`backtest=true`, a set of hindcast windows we score for accuracy.

**In scope:** selecting the best Sybilion *config* per fertilizer by backtest accuracy, and packaging
the raw winning forecasts for the agent.
**Out of scope (lives downstream in the agent layer, already specced):** conformal band recalibration,
trust scoring, the cost-min decision solver. This deliverable feeds those layers the **raw** forecast +
`backtest_trajectories.json` + `external_signals.json`; it does not modify Sybilion's output.

### Fertilizers (all 5)
`urea`, `dap`, `mop`, `tsp`, `phosphate-rock` — inputs at `data/processed/dataset1/<slug>.json`
(360 monthly points, `YYYY-MM-01` keys, USD/kg, gapless).

---

## 2. Two tiers

### Tier 1 — the simple model (agent ships on this first)
- **Config:** drivers OFF (`recency_factor`=default), `backtest=true`, `accept_stale_latest_data=true`,
  `soft_horizon=12`. Cheap (~€0.85), fast (~3 min).
- One per fertilizer. This is **identical to the "drivers OFF" cell of the Tier-2 grid** — so Tier 1 is
  not extra work, it's the fast subset the agent can consume immediately while the slower driver cells run.
- Agent consumes the raw P50 + native bands (recalibration happens later, in the agent).

### Tier 2 — the best model (per-fertilizer bake-off)
- **Grid:** 3 variants × 5 fertilizers = **15 cells**.
  | variant | `recency_factor` | drivers | runtime |
  |---|---|---|---|
  | ON | 0.0 (full archive) | ~35 surfaced | 8–20 min |
  | MID | ≈0.3 | uncertain | medium |
  | OFF | default | none | ~3 min |
- All variants: `backtest=true`, `accept_stale_latest_data=true`, `soft_horizon=12`. No keyword/category/
  region hints — proven to make zero difference on these series (DIAG_FINDINGS); recency is the only lever.
- **Winner per fertilizer** = the config the agent upgrades to. The OFF cells double as the Tier-1 set.

### Relationship to the agent spec's gating experiment
The agent design (§6) had one open item: "run urea at recency=0.0, backtest, soft_horizon=12; decide
one-config vs two-config." **This bake-off resolves that item and generalizes it to all 5 fertilizers** —
the urea ON cell *is* that experiment. If a fertilizer's ON cell wins on accuracy, it serves decision +
drivers from one config (the agent spec's "preferred" path); if OFF/MID wins, that fertilizer uses the
cheap forecast for decisions and keeps the ON cell only for its drivers.

---

## 3. Selection metric

Computed by a pure-stdlib `score_bakeoff.py` (no numpy/pandas — consistent with the existing pipeline),
per cell, from **`backtest_trajectories.json`** (the real per-window truth — **not** `backtest_metrics.json`,
which duplicates one metric set across all horizon labels):

1. **Exclude stale windows** whose `forecast_end` > last real data point (2026-03-01). Extending the
   horizon to 12 pushes recent hindcast windows past the last real data → null `actual`s → garbage
   metrics. This is the documented gotcha; dropping them is mandatory before aggregating.
2. **Primary metric — MASE** (and RMSSE) of P50 vs a **seasonal-naive baseline** (lag-12). MASE/RMSSE < 1
   means Sybilion beats naive; > 1 means worse. (Urea baseline was MASE 5.1 — worse than naive — so the
   bake-off must be able to report "Sybilion loses to naive" honestly.)
3. **Tiebreak — MAPE.**
4. **Reported, not used for selection — 80/90 band coverage** (a trust caveat; the agent recalibrates
   bands downstream, so coverage does not pick the winner here).

Rank the 3 variants within each fertilizer; lowest MASE wins (tiebreak MAPE).

**phosphate-rock caveat:** FINDINGS flagged its "flat tail / low trust." Its scores may be degenerate;
report that honestly rather than forcing a winner.

---

## 4. Artifacts & storage

```
data/forecast_exploration/bakeoff/
  manifest.json                      # (fertilizer,variant) -> {job_id, config, status, eur_cost, reused}
  <fertilizer>/<variant>/
    forecast.json                    # P50 + P05..P95 per month
    backtest_trajectories.json       # per-window actual + quantiles (scoring input)
    external_signals.json            # drivers (ON cells; {} otherwise)
  BAKEOFF_RESULTS.md                 # human-readable: winner per fertilizer + "does Sybilion beat naive?"
  champions.json                     # machine-readable agent input contract (see §5)
  score_bakeoff.py                   # pure-stdlib scorer
```

`manifest.json` is the single source of truth for what was run vs reused.

---

## 5. `champions.json` — the agent input contract

Per fertilizer, the object the agent's offline stage reads:

```json
{
  "<fertilizer>": {
    "winner_variant": "ON|MID|OFF",
    "job_id": "...",
    "config": { "recency_factor": 0.0, "soft_horizon": 12, "backtest": true,
                "accept_stale_latest_data": true },
    "forecast": { "YYYY-MM-01": { "p50": 0.0, "p05": 0.0, "...": 0.0, "p95": 0.0 } },
    "backtest_trajectories_ref": "bakeoff/<fertilizer>/<variant>/backtest_trajectories.json",
    "external_signals_ref": "bakeoff/<fertilizer>/<variant>/external_signals.json",
    "accuracy": { "mase": 0.0, "rmsse": 0.0, "mape": 0.0,
                  "n_windows_scored": 0, "n_windows_excluded_stale": 0 },
    "trust": { "cov80": 0.0, "cov90": 0.0 },
    "beats_naive": true
  }
}
```

The agent recalibrates bands and computes its own trust score from `backtest_trajectories_ref`; it reads
`external_signals_ref` for the driver layer (Q6–Q8). We hand it raw, complete artifacts — no transforms.

---

## 6. Job list (15 cells: 13 new, 2 reused)

| fertilizer | ON (recency 0.0) | MID (≈0.3) | OFF (default) |
|---|---|---|---|
| urea | **new** | **new** | reuse `59b5874f` |
| mop | reuse `1517c8d1` | **new** | **new** |
| dap | **new** | **new** | **new** |
| tsp | **new** | **new** | **new** |
| phosphate-rock | **new** | **new** | **new** |

- **Reuse caveat:** reused jobs were run at `soft_horizon`=6 (Run A) / different trims, not 12. If a reused
  artifact's horizon/length doesn't match the grid, re-run it at the standard config rather than scoring
  apples-to-oranges. Verify each reuse against `manifest.json` before trusting it.
- WTI (`b6127f17`) and natgas runs are **driver-mechanism reference only**, not part of the 5 — keep as
  documentation in DIAG_FINDINGS, not in the bake-off.

### Execution
- Submit all async via `mcp__sybilion__submit_forecast`; poll with `get_forecast` using the MCP's built-in
  spacing (**no Bash `sleep`**). Pull artifacts with `get_forecast_artifact`.
- Wall-clock, not money, is the constraint: €10,027 available, ~€7 spent; the **€10k tranche expires
  2026-06-01** (~36 h). ON/MID cells run 8–20 min; OFF cells ~3 min. ~13 new jobs fit comfortably.
- On `failed`: pull `errors.json`, record in manifest, continue. `info.json` 404 is normal (no message).

---

## 7. Deliverables

1. Submitted/reused jobs + `manifest.json`.
2. `score_bakeoff.py` (pure stdlib) + `BAKEOFF_RESULTS.md` (winner per fertilizer; headline beat-naive
   verdict; phosphate-rock honesty note).
3. `champions.json` — Tier-1 set (OFF cells) + Tier-2 winners — the agent's input contract (§5).
4. Updated `FINDINGS.md` and project memory.

---

## 8. Out of scope (explicit)

- Conformal/empirical band recalibration, trust score, cost-min decision solver, the Streamlit/agent UI —
  all live in the agent spec and consume this deliverable's output.
- Keyword/category/region tuning — proven inert on these series.
- Local/hand-rolled forecasting models — rejected (stripped Python; and the user chose Sybilion-only).
- Sourcing (Dataset2) and driver post-processing — separate concerns owned by the agent spec.
