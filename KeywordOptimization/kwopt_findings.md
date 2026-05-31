# kwopt — Findings on the Sybilion Forecast API
### From "keyword optimizer" to forecastability triage — an evidence-driven pivot
*ZeroOne Hack · all numbers below are reproducible from the cited job IDs (Sybilion async-jobs dashboard).*

---

## TL;DR

- We built **kwopt**, an engine to find the keyword set that minimizes a target's Sybilion **12-month backtest MAPE**, then "uses itself" by reusing past wins.
- Controlled experiments (incl. a target **synthetically built from real Brent + S&P 500** so its true drivers are *provably in Sybilion's catalog*) show: **keyword *content* has zero effect on accuracy** — on 4 targets, including one rigged in keywords' favor.
- **The driver layer is where Sybilion's value lives** (one target: 10% → **2.7%** MAPE, ~73% error reduction, matching Sybilion's stated 30–70%). But the core drivers are **auto-selected from the series shape** (Similarity-TS) and are **not steerable** by any input we send.
- **Attachment ≠ value:** a target can attach 100 KB of drivers that add *zero* predictive value (potash). So the useful product isn't keyword tuning — it's **triage**: cheaply predict which portfolio series Sybilion will forecast *well*, and only pay for those.

---

## What we built

`kwopt` — a headless Python engine over the Sybilion REST API:
- `/drivers` **relevance screen** (cheap pre-filter; validated as a proxy: **6/6** of forecast-used drivers also surfaced as `/drivers` candidates).
- Parallel forecast **orchestration** + **order-invariant cache** (sqlite) so no keyword set is ever re-run.
- **MAPE objective**, no-keyword baseline, lift accounting, and a **controlled-experiment harness**.
- REST only — evaluated the Sybilion **MCP** server and rejected it for headless loops (OAuth/per-call approval).

## Method

Monthly series, `pipeline_version v1`, `backtest=true`. Targets: 2 real World Bank fertilizer benchmarks (urea, potash/MOP), 1 real US industrial-robot import series, and 1 **synthetic control** (`macro_index`) whose growth is a function of real contemporaneous oil returns + **lagged** equity returns — engineered so Energy + Equities *must* be the true drivers. **MAPE is the only usable metric** (see Observations).

---

## Results — every lever Sybilion exposes, tested

| Lever | What it should do | Verdict | Evidence |
|---|---|---|---|
| **Keyword content** | steer driver selection → lower MAPE | **No effect** | macro: `correct`=`wrong`=**2.924%** (both *worse* than no-kw 2.661%); urea: 3 sets all **10.091%** |
| Keywords (any vs none) | — | small, **unpredictable sign** | robots **+0.92pp** (helped), macro **−0.26pp** (hurt), urea 0.0 |
| **Recency (`recency_factor`)** | temporal weighting → lower MAPE | **Real but coarse & unreliable** | macro: ~1pp swing, **4 quantized buckets**, best@0.6; **urea & MOP: 0.00pp** (inert) |
| **Filters (`categories`)** | hard-constrain driver pool | **Not enforced** | "wrong" filter (Agri/Health/Tourism) → top drivers still **Energy-US, Global-risk, Services** (out-of-filter); MAPE **2.924%** = unconstrained bucket |

**Keyword controlled experiment (the decisive one), `macro_index`, recency 0.6:**

| Run | 12m MAPE |
|---|---|
| No keywords (baseline) | **2.661%** ← best |
| `correct_drivers` (oil/energy/equities) | 2.924% |
| `wrong_drivers` (agriculture/tourism) | 2.924% |

Correct keywords (naming the *true* drivers) did **not** beat wrong keywords, and both *underperformed* sending none — even though the series is built from oil + equities and the model **did** find Energy(#1) + Equities(#3) at importance 100 *on its own*.

---

## The mechanism (why nothing steers it)

Sybilion runs 3 candidate searches; **Similarity-TS needs no keywords** and dominates. Across recency/keyword/filter changes, the **high-importance core spine is stable** (Energy, Equities, Global-risk), while only the **low-importance tail churns**:

- macro recency 0.0 vs 0.6: driver sets only **~40% overlap** (16 shared / 11+12 unique) — yet the shared 16 carry the importance-100 drivers, so MAPE stays in-ballpark.
- The ~1pp macro gain at recency 0.6 comes entirely from a better **secondary** basket (it swaps in US labour + trade-price detail). All three metrics (MAPE/MASE/RMSSE) agree on the **same 4 buckets** → recency maps to discrete model configs, not a smooth knob.

**Net:** the core drivers are a function of the *target's own history*. Keywords and category filters are accepted but do not move the core; recency only re-rolls the tail, which usually doesn't change accuracy.

## Key insight: attachment ≠ value

| Target | Baseline MAPE | Signals | Recency lever | Drivers *useful*? |
|---|---|---|---|---|
| macro (synthetic) | **2.661%** | rich (50–68 KB) | **active (1pp)** | **Yes** (10%→2.7%) |
| robot imports | 9.424% | rich (~18 KB) | n/a | partial |
| urea | 10.091% | **empty (37 B)** | inert | No (none attach) |
| **MOP / potash** | 9.729% | **rich (41–107 KB), varies w/ recency** | inert | **No** |

Potash is the sharpest result: recency **demonstrably changes its driver set** (signals jump 41→107 KB), yet MAPE is **byte-identical (9.7287%) across all 6 recencies**. Drivers attach, change, and contribute **nothing** — the forecast rides the series' own autoregression. **Driver presence is not driver value.**

---

## The pivot — forecastability triage (the actual product)

Since no input steers driver selection, keyword/filter/recency *optimization* is a dead end. The real, buildable value for a multi-series portfolio (≈20k units, many series):

> **kwopt as a triage layer:** for each series, cheaply estimate whether Sybilion's driver engine **adds predictive value**, and route spend only to the series where it does.

- The signal is **lift over a naive/no-external baseline**, *not* whether drivers attach (potash proves attachment is a false positive).
- Cheap to compute; saves paying ~€3 × thousands of forecasts on series (e.g. administered fertilizer prices) where Sybilion correctly reduces to univariate.
- Turns "which keywords?" (flat, unanswerable) into "which *targets*?" (real, decision-relevant).

---

## Observations for the Sybilion team *(offered as constructive feedback)*

1. **`timeseries_metadata.keywords`**: accepted and echoed in `input.json`, but keyword *content* did not change backtest error in any completed run. Appears to act, at most, as a weak hint the Similarity-TS core overrides.
2. **`filters.categories`**: forecasts ignored the constraint — out-of-category drivers (Energy, Global-risk, Services) dominated a run restricted to Agriculture/Health/Tourism. Possibly intended as soft, or a usage/version nuance worth documenting.
3. **`backtest_metrics` MASE / RMSSE appear off-scale**: e.g. MASE ≈ **1623** for a **2.66%** MAPE forecast (and ~10⁷ on another target) — unusable as-is; we relied solely on MAPE. RMSE == MAE exactly in our artifacts.
4. **Latency variance**: identical driver-rich forecasts settled in **11–57 min**; concurrency >2 appeared to slow throughput. Param `soft_horizon` (not `horizon`) was required.

---

## Evidence appendix (verifiable job IDs)

| Run | Job ID | 12m MAPE |
|---|---|---|
| Robot baseline (no-kw) | `b334e08f` | 9.424% |
| Robot keyworded (2 sets) | `98ee0c6d`, `b9a5ea40` | 8.506% (both) |
| Urea baseline | `9d992d09` | 10.091% |
| MOP recency sweep (6 jobs) | `4b9af782`…`180b759c` | 9.7287% (all) |
| Macro baseline (recency 0.6) | `49254b4d` | **2.661%** |
| Macro keywords correct/wrong | `4d36a13f`, `7b3393f5` | 2.924% (both) |
| Macro recency best / plateau | sweep `bkw7ri582` | 0.6→2.661; 0.5/0.7/0.8/1.0→2.924 |
| Macro filter "wrong" (not enforced) | `3ac73567` | 2.924% |

*Cost: ~€100 total this session. One night of evidence-first testing closed an expensive premise (keyword distillation) before it was built — and surfaced the triage product instead.*
