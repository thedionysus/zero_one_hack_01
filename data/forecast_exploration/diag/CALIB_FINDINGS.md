# Calibration validation at recency=0.0 — gating experiment (2026-05-30)

Job `fffb5762-a3a5-46bc-8920-67e1bade2abe`: **urea, recency_factor=0.0, backtest=true, soft_horizon=12,
full 360-pt series**, keywords on, no category/region filters. Cost **€0.32**, runtime **~1 min**.
Purpose: decide the forecast config for the procurement agent (one config for decision+drivers vs two).

## Finding 1 — recency=0.0 did NOT surface drivers on the full backtested series

`external_signals.json` = **37 B = empty `{}`** again. Cost €0.32 and ~1 min runtime confirm **no driver
search ran** (the DIAG runs that surfaced ~35 drivers cost €2.5–3.3 and took 8–20 min).

**This refutes "recency=0.0 ⇒ drivers."** The driver-bearing DIAG runs (D3 MOP, D4 WTI) used a
**120-pt trimmed series + backtest=false**; this run used 360 pts + backtest=true. So the lever that
surfaces drivers is **series length (~120 pts) and/or backtest=false**, NOT recency alone.
→ **Drivers and the decision forecast require different configs.** The "one coherent config serves both"
plan from the design brief is **not viable** as stated.

## Finding 2 — recency=0.0 calibration is poor and badly biased LOW

Recomputed over all **90 (window, month) hindcast pairs** (13 windows):

| Nominal band | Empirical coverage | Target |
|---|---|---|
| 50% [0.25–0.75] | **7.8%** | 50% |
| 80% [0.10–0.90] | **22.2%** | 80% |
| 90% [0.05–0.95] | **27.8%** | 90% |

- **MAE vs P50 = 0.125, MAPE = 23.6%.**
- **Actual sat ABOVE P50 in 87/90 = 96.7% of months** (mean signed error **+0.124**). Massive
  systematic **under-prediction**.
- Rising months: mean(actual−P50) = **+0.160** (n=54); falling months +0.069 (n=23) → under-predicts
  worst exactly when prices rise.

**This is WORSE than the earlier recency 0.5–0.7 result (48% coverage on the 80% band).** So
`recency=0.0` does not fix calibration — if anything worse.

### Critical caveat — the backtest window is the worst possible case
The API only hindcasts the **last 12 months**, which here is the **2025→2026 urea rally ending in the
2026-03 spike (0.726)** — the latest input point. A mean-reverting model under-predicts a sustained
rally by construction, and the spike tail poisons every window that overlaps it (the known
stale-data-backtest gotcha). So the 22%/97% numbers are partly a **window artifact**, not purely model
error. A fair trust score must **down-weight or exclude spike-tail windows**.

## Decisions for the agent (gating question resolved)

1. **Config = TWO forecasts (forced by the data), not one.**
   - **Decision forecast:** default `recency_factor` (0.5) + `backtest=true` + `soft_horizon=12`,
     full series. recency=0.0 gives no calibration benefit and no drivers, so there's no reason to pay
     for it here.
   - **Driver forecast (optional, visible-reasoning panel only):** the DIAG-style config that actually
     surfaces drivers (~120-pt trimmed, recency=0.0, backtest=false), fetched separately and pre-cached.
   - Accept the coherence cost: the driver panel is labelled "correlated macro context for this series,"
     not "the drivers behind this exact forecast object."

2. **Conformal recalibration + rise-bias correction is NON-NEGOTIABLE** and is the technical centerpiece.
   Raw bands are unusable at any recency (22–48% coverage on an 80% band). Empirically widen from the
   hindcast residuals AND shift up to remove the under-prediction bias.

3. **Trust score must handle the spike tail.** Exclude/down-weight hindcast windows that overlap the
   stale terminal spike, else every fertilizer scores untrustworthy purely from the 2026-03 artifact.

4. **Procurement rule confirmed:** the model lags sustained rises → bias toward **buying earlier** on
   uptrends (the live data shows the model under-predicting a real rally by ~0.16 USD/kg).

## Forward 12-mo forecast (context, USD/kg, P50)
Mean-reverts the 0.726 spike immediately: Apr 0.361, May 0.322, Jun 0.339, Jul 0.382, Aug 0.420,
Sep 0.408, Oct 0.387, Nov 0.365, Dec 0.331, Jan 0.322, Feb 0.393, Mar 0.453. (Apr/May 2026 are in the
past — stale terminal data.)
