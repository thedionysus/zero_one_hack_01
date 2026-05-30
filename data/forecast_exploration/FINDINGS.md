# Sybilion forecast exploration — Urea (spike, 2026-05-30)

Throwaway exploration to learn the Sybilion API surface and output, **not** a tuned forecast.
Two backtested 6-month forecasts on the urea series (`data/processed/dataset1/urea.json`, 360 monthly pts).

| Run | job_id | knobs | cost |
|-----|--------|-------|------|
| A baseline | `59b5874f…` | soft_horizon=6, backtest=true, no keywords/filters, recency default | €0.89 |
| B driver-targeted | `3cf6f0cc…` | + 12 keywords, categories [46,25,28,11], region World, recency_factor=0.7 | €0.86 |

## Q1 — What's tunable, and what actually moved the needle

Knobs available on `submit_forecast`: `soft_horizon` (1–12), `hard_horizon` (fallback floor),
`backtest` (on/off), `recency_factor` (0=full archive … 1=last ~5 days), `filters.categories`,
`filters.regions`, `filters.limit`, and `timeseries_metadata.keywords` (≤20).

**Biggest finding: on this series, the driver knobs did nothing.** Runs A and B returned
**byte-for-byte identical** `forecast.json` and `backtest_metrics.json`, and **both** had
`external_signals.json == {}` (no external drivers used). So keywords + category/region filters +
recency_factor had **zero effect** — Sybilion found no usable correlated drivers in its archive for a
global FOB urea benchmark, with or without hints. The forecast is effectively **univariate**.
Implication for the track's "driver importance" angle: it does not apply to this dataset as-is.
The v1 API does not let us inject our **own** exogenous series (e.g. natural-gas prices) — Sybilion
only auto-selects from its archive. Levers that *would* matter here: `soft_horizon`/`hard_horizon`
(shape/length) and `backtest` (evaluation). Driver hints only matter for series Sybilion can match.

**`info.json` was 404 on both** (no pipeline message). When present it explains driver-less fallbacks.

## Q2 — The output, and how it powers decisions

`forecast.json`: per forecast month, a **point `forecast` (= P50)** plus **19 quantiles** (P05…P95).
The quantile bands are the decision-grade signal (procurement risk, not just a point).

6-month urea forecast (USD/kg): Apr 0.428, May 0.360, Jun 0.348, Jul 0.411, Aug 0.406, Sep 0.380.
**The model mean-reverted the Mar-2026 spike** (input ended 0.726; Apr forecast 0.428) — it treated the
spike as noise. (Stale-data note: data ends 2026-03, so Apr/May 2026 forecasts fall in the past;
only Jun–Sep are genuine future. Used `accept_stale_latest_data=true`.)

**Backtest is the part that drives trust — and `backtest_metrics.json` is NOT enough:**
- `backtest_metrics.json` reported ONE metric set (MAE 0.084, MAPE 19.3%, MASE 5.10, RMSSE 3.75)
  duplicated across the 6m/12m/24m/60m labels — misleading; don't rely on it alone.
- `backtest_trajectories.json` has the truth: **13 real 6-month hindcast windows** with `actual` +
  19 quantiles per month (no mean). Recomputed from it:
  - **Band calibration is poor / overconfident:** 80% band covered only **48%** of actuals (want ~80%);
    90% band covered **54%** (want ~90%). MASE 5.1 / RMSSE 3.75 (≫1) ⇒ worse than naive seasonal.
  - **Systematic under-prediction during rises:** through 2025 every actual sat *above* P50 and mostly
    *outside* the band, because mean-reversion fought the uptrend.

### How to use this in the sourcing/stock-up decision
1. Use **P50 for the central buy-or-wait signal**, but **don't trust the native bands** — they're too
   tight. Widen them (treat P90 ≈ a P70) or derive empirical bands from the 13-window hindcast errors.
2. The model **under-reacts to sustained rises** → bias procurement toward **buying earlier** when the
   recent trend is up (the forecast will lag a real rally).
3. Compute a per-fertilizer **trust score from `backtest_trajectories.json`** (coverage + MAPE) and
   down-weight low-trust forecasts (e.g. phosphate-rock's flat tail) in the decision.
4. Quantile spread (P90−P10) is a ready-made **risk measure** per month for stock-up sizing.

## Practical API notes
- Jobs are async; ~3 min each with backtest. `external_signals.json` size ~37 B = empty = no drivers.
- Real per-window accuracy lives in `backtest_trajectories.json`, not `backtest_metrics.json`.
- Chart: `data/forecast_exploration/urea_forecast.svg` (24mo history + 6mo P50 + 80/90 bands).
- Cost ≈ €0.85–0.89 per backtested 6-month forecast (tier 4); ample headroom in the hackathon grant.

## Bake-off (2026-05-30): best config per fertilizer

Ran **15 fresh backtested forecasts** — 3 recency variants × 5 fertilizers — all `soft_horizon=12`,
`backtest=true`, `accept_stale_latest_data=true`. Variants: **ON** `recency_factor=0.0`, **MID** `=0.3`,
**OFF** default. Total cost **€17.64**. Each cell scored from its own `backtest_trajectories.json`
(13 windows; **11 stale windows excluded** — `forecast_end` past the 2026-03 data end) with `score_bakeoff.py`:
MASE/RMSSE of P50 vs a **lag-12 seasonal-naive** baseline (MASE<1 ⇒ beats naive). Winner = lowest MASE.
Artifacts + `champions.json` (the agent's input contract) live in `data/forecast_exploration/bakeoff/`.

| fertilizer | winner | MASE | MAPE | beats naive? | drivers (ON) | fwd bands |
|---|---|---|---|---|---|---|
| urea | OFF† | 1.10 | 20.8% | **no** | 0 | native |
| dap | OFF† | 1.18 | 17.1% | **no** | 0 | native |
| mop | ON | **0.63** | 16.0% | **YES** | 37 | missing |
| tsp | OFF | 1.22 | 21.4% | **no** | 56 | missing |
| phosphate-rock | OFF | **0.62** | 18.3% | **YES** | 64 | missing |

**Headline: Sybilion beats seasonal-naive on only 2 of 5 fertilizers (mop, phosphate-rock).** Key findings:
1. **recency does NOTHING for urea & dap** — all 3 variants returned **byte-identical** scores (0 drivers found
   even at `recency=0.0`). Confirms these two series are effectively **univariate** for Sybilion. †`champions.json`
   sets `tie=true` and picks **OFF** (the cheapest run, ~€0.43, and it carries native forward bands) so the agent
   doesn't waste money on the equivalent driver-aware config.
2. **Drivers help mop** (monotone: ON 0.63 < MID 0.66 < OFF 0.68) but **hurt tsp** (ON/MID 1.40 vs OFF 1.22) and
   **badly hurt phosphate-rock** (ON/MID MASE **2.10**, MAPE 61.7%, vs OFF 0.62). So "turn drivers on" is **not**
   universally good — it must be chosen per series by backtest, which is exactly what the bake-off does.
3. **Driver-rich series (mop/tsp/phosphate-rock) return point-only FORWARD forecasts — no native quantile bands.**
   The backtest windows still carry quantiles (so scoring works), but `champions.json` flags
   `forward_bands_available=false` for these → the agent must **derive forward bands from the hindcast trajectories**.
4. **Native bands are poorly calibrated** at scale: cov80 mostly **21–50%** (want ~80%) ⇒ overconfident, as before.
   phosphate-rock's cov80 **100%** across all variants is the opposite — a **flat-tail / degenerate-band artifact**
   (trust-flag it, don't celebrate it). Both directions argue for the agent's recalibration layer.

**Decision-layer takeaways:** pick the bake-off winner per fertilizer from `champions.json`; for mop/tsp/phosphate-rock
get forward bands from `backtest_trajectories_ref`; down-weight urea/dap/tsp (lose to naive) and phosphate-rock's
flat tail in any trust score.
