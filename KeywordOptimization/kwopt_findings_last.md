# kwopt — Findings on the Sybilion Forecast API
### From "keyword optimizer" to a forecastability-triage proposal — an evidence-driven pivot
*ZeroOne Hack. Every quantitative claim maps to a cited job ID (verifiable on the Sybilion async-jobs dashboard). Where we did not measure something, we say so.*

---

## Original aim & premise

We built **kwopt** to find the keyword set that minimizes a target's Sybilion **12-month backtest MAPE**, then have it **"use itself"** — reuse past wins to propose keywords for new series in one pass (eventually a local distilled model). The entire design rested on one premise:

> **Keyword choice → which drivers Sybilion attaches → backtest MAPE.**

(Full design: `kwopt_original_plan.md`.) Phases 0–2 were deliberately structured to **test that premise cheaply before** building the expensive distillation. This report is what the testing revealed.

## TL;DR

- **Keyword *content* has no measurable effect on accuracy** — 3 targets, incl. a synthetic one built from real Brent + S&P 500 (drivers provably in-catalog) and rigged in keywords' favor.
- We tested **every input lever Sybilion exposes.** Keywords: inert. Category filters: inert. Recency: works on only 1 of 3 driver-bearing targets, quantized, optimum = our own default. **`filters.limit` (driver *count*): the one lever that genuinely works** — but it controls *how many* drivers, not *which*, and the default (max) is already best.
- **Drivers genuinely help — now measured by ablation:** suppressing them on macro (`limit=0`) raised MAPE 2.661% → 3.453% (**≈0.79pp, ~23% relative**). But Sybilion **selects which drivers itself from the series' shape** — unsteerable by keywords or category filters.
- **Attachment ≠ value:** potash attaches 41–107 KB of drivers whose *variation* moves error by zero.
- Conclusion → the useful product isn't input tuning; it's **forecastability triage** (rank which series Sybilion forecasts well, spend only there). **Proposed, not yet built.**

## What we built

`kwopt` — a headless Python engine over the Sybilion REST API: a `/drivers` **relevance screen** (validated proxy — **6/6** of a robot forecast's used drivers also appeared as candidates), parallel forecast **orchestration**, an **order-invariant cache** (sqlite), a **MAPE objective**, and a **controlled-experiment harness**. (The keyword-distillation/"reuse past wins" layer was designed but left as a stub — the experiments below are *why*.) REST only; the Sybilion MCP server was evaluated and rejected for headless loops (OAuth/per-call approval).

## Method

Monthly series, `pipeline_version v1`, `backtest=true`, `soft_horizon` (not `horizon`). Targets: 2 real World Bank fertilizer benchmarks (urea, potash/MOP), 1 real US industrial-robot import series, and 1 **synthetic control** (`macro_index`), growth = `0.4·oil_return + 0.6·lagged_equity_return + noise` — engineered so Energy + Equities *must* be its true drivers, built from real series so they exist in the catalog. **MAPE is the only usable error metric** (MASE/RMSSE off-scale — see Observations).

---

## Results — every lever Sybilion exposes, tested

| Lever | What it should do | Verdict | Evidence |
|---|---|---|---|
| **Keyword content** | steer *which* drivers attach | **No effect** | macro `correct`=`wrong`=**2.924%** (both worse than no-kw 2.661%); urea 3 sets all **10.091%**; robots 2 sets both **8.506%** |
| Keywords (any vs none) | — | tiny, unpredictable; robot gain uncontrolled | macro **−0.26pp** (clean controlled run); robots **+0.92pp** (*suggestive* — recovered jobs, not a controlled run); urea 0.0 |
| **Recency** | temporal weighting → MAPE | works on **1 of 3** driver-bearing targets; quantized; optimum = our default | macro ~1pp swing, **4 buckets / 9 points**, best @0.6 — **and 0.6 is kwopt's own default**; urea & MOP **0.00pp** |
| **Category filter** | constrain *which* drivers | **Inert (not enforced)** | macro relevant `[25,40,46,42,6]` vs wrong `[28,10,26]`: **identical to 6 decimals** (MAPE/MASE/RMSSE) + same drivers; "wrong" arm's #1 driver is **Energy-US (out of filter)** |
| **Driver count (`filters.limit`)** | cap *how many* drivers | **Works — the only lever that does** | macro: 0 drivers→**3.453%**, 15→**2.924%**, 28(full)→**2.661%**; quantized (`limit`=1 and =5 both return 15 drivers) |

**Keyword controlled experiment (the decisive one), `macro_index`, recency 0.6:**

| Run | 12m MAPE | job |
|---|---|---|
| No keywords (baseline) | **2.661%** ← best | `49254b4d` |
| `correct_drivers` (oil/energy/equities) | 2.924% | `4d36a13f` |
| `wrong_drivers` (agriculture/tourism) | 2.924% | `7b3393f5` |

Correct keywords (naming the *true* drivers) did **not** beat wrong keywords, and both *underperformed* sending none — even though the no-keyword baseline found **Energy (#1) + Equities (#3) at importance 100 on its own** (verified in `49254b4d`).

---

## The driver ablation — measured driver value *(fills the earlier gap)*

`filters.limit` is enforced, so `limit=0` gave us the driver-free macro forecast we previously lacked. Holding recency 0.6, no keywords:

| drivers | 12m MAPE | via |
|---|---|---|
| 0 | 3.453% | `limit=0` |
| 15 | 2.924% | `limit=1`, `limit=5` |
| 28 | 2.661% | full (baseline `49254b4d`) |

→ **On macro, external drivers contribute ≈0.79pp (~23% relative error reduction).** This is a *measured* driver value, not a cross-target inference. Three caveats: (1) `limit` is **quantized** — 1 and 5 both yield 15 drivers, so it's not a literal top-N cap; (2) the **specific driver set** matters, not just the count — keyword/filter runs with 29–34 drivers still landed in the worse 2.924% bucket, so "more drivers = better" holds only *within* this controlled sweep, not as a general law; (3) `limit` only caps *below* what Sybilion selects at max (28), so **no limit value beats the full baseline**.

## The mechanism

Across keyword / recency / filter changes, the **high-importance core spine is stable** (Energy, Equities, Global-risk) while only the **low-importance tail churns** (macro recency 0.0 vs 0.6: ~40% overlap, but the shared 16 carry the importance-100 drivers). Recency's effect is **quantized** (9 inputs → 4 MAPE buckets; best 0.6 = 2.661%, plateau 0.5/0.7/0.8/1.0 = 2.924%, 0.0/0.1 = 3.657%).

**Corrected one-line model:** Sybilion **does** use external drivers (the `limit` ablation proves it), but **selects which ones itself from the series' shape** — keywords and category filters can't steer that. Only the *count* is user-exposed (`limit`), and it's already optimal at the default. So driver value is real but auto-managed; the inputs meant to steer it don't.

## Cross-target summary — the structural picture

| Target | Type | Baseline MAPE | Signals | Recency | Drivers useful? |
|---|---|---|---|---|---|
| Robots (`b334e08f`) | US robot imports $ | 9.424% | rich ~18 KB | not swept | partial (keywords reshuffle, MAPE flat) |
| Urea (`9d992d09`) | WB fertilizer price | 10.091% | **empty 37 B** | inert | no (none attach) |
| MOP (`4b9af782`) | WB fertilizer price | 9.729% | rich 41–107 KB, varies | inert | no (variation adds nothing) |
| Macro (`49254b4d`) | synthetic cyclical | **2.661%** | rich 67 KB | active ~1pp | **yes — ~0.79pp / ~23% (via `limit=0`)** |

The two WB fertilizer benchmarks are essentially **autoregressive** series the macro driver basket can't improve; the synthetic index responds (to recency, and to driver count). The backend anchors on a fixed Energy/Equities/Global-risk spine regardless of keywords or filters.

## Attachment ≠ value

Potash is the sharpest case: recency **changes its driver set** (signals jump 41→107 KB across recencies) while MAPE is **byte-identical (9.7287%) across all 6 recencies**. The driver *variation* carries **zero marginal value** — the forecast rides the series' own autoregression.

---

## The pivot — forecastability triage *(proposed, not yet built)*

Since driver *selection* isn't steerable and the *count* is already maxed, input optimization is a dead end. The real value for a multi-series portfolio (≈20k units):

> **kwopt as a triage layer:** for each series, cheaply estimate whether Sybilion **adds value over a no-driver baseline**, and route ~€3 forecast spend only where it does.

- The signal is **lift over a baseline**, *not* whether drivers attach (potash proves attachment is a false positive).
- The `limit=0` result hands us an **API-native triage measurement**: a cheap "Sybilion-univariate" forecast vs the full forecast → the gap *is* the driver value (the ablation is the triage test). A free local seasonal-naive baseline works too.
- This is a **specification, not running code** — the baseline + lift-scoring component is designed, not yet implemented.

## Honesty note (boundaries of what we measured)

- **Driver contribution is now measured** (via `limit=0`): ≈0.79pp / ~23% on macro. (This replaces any cross-target hand-wave; it's specific to macro and below Sybilion's marketed 30–70%, which uses a different baseline.)
- **Recency / limit value beyond n=1 is unproven** — only the synthetic macro target responded; both real fertilizers were inert. Whether optimal recency differs across targets (the thing that would make tuning worthwhile) is untested.
- The robot **+0.92pp** "any-vs-none" came from recovered dashboard jobs, **not** a single controlled baseline-vs-keyword run → treat as *suggestive*. The one clean controlled any-vs-none test (macro) showed keywords slightly *hurt*.

## Observations for the Sybilion team *(constructive feedback)*

1. **`keywords`** — accepted and echoed in `input.json` (verified 12/12 match), but content did not change backtest error in any run.
2. **`filters.categories`** — not enforced: a run restricted to Agriculture/Health/Tourism returned Energy/Global-risk/Services as top importance-100 drivers, identical metrics to the Energy/Financial-restricted run.
3. **`filters.limit`** — *is* enforced but **quantized**: `limit=1` and `limit=5` both returned 15 drivers (not a literal top-N cap); `limit=0` special-cases to zero drivers.
4. **`backtest_metrics` MASE / RMSSE appear off-scale** — e.g. MASE **1788.40** / RMSSE **1444.79** at a 2.924% MAPE forecast (`416cb286`, `3ac73567`), ~10⁷ on robots; `RMSE == MAE` exactly. All three move in lockstep with MAPE — **MASE adds no independent resolution**.
5. **Latency variance** — identical driver-rich forecasts settled in **11–57 min**; concurrency >2 appeared to slow throughput.

---

## Evidence appendix (verifiable Sybilion job IDs)

| Run | Job ID | 12m MAPE |
|---|---|---|
| Robot baseline (no-kw) | `b334e08f` | 9.424% |
| Robot keyworded (2 different sets) | `98ee0c6d`, `b9a5ea40` | 8.506% (both) |
| Urea baseline (empty signals) | `9d992d09` | 10.091% |
| MOP recency sweep (6 jobs, flat) | `4b9af782`, `3c43a213`, `0a4c5dd4`, `49484d35`, `48cdd1a1`, `180b759c` | 9.7287% (all) |
| Macro baseline (recency 0.6, 28 drivers) | `49254b4d` | **2.661%** |
| Macro keywords correct / wrong | `4d36a13f`, `7b3393f5` | 2.924% (both) |
| Macro recency sweep (9 jobs → 4 buckets) | 0.0`9e77af8e` · 0.1`dedd6694` · 0.2`c06f47b2` · 0.4`11227d3d` · 0.5`1087a76a` · 0.6`6b2f24e6` · 0.7`77eb5891` · 0.8`6f77f18a` · 1.0`1dcbc841` | 2.661–3.657% |
| Macro category filter — relevant / wrong (identical) | `416cb286`, `3ac73567` | 2.924253% (both) |
| Macro driver ablation — `limit` 0 / 1 / 5 (recency 0.6) | (dashboard; baseline ref `49254b4d`) | 3.453% / 2.924% / 2.924% |

*Cost: ~€100 total this session. One night of evidence-first testing closed an expensive premise (keyword distillation) before it was built — and motivated the triage proposal instead.*


<!-- ============================================================================ -->
<!-- ===== APPENDED BELOW: full content of kwopt_findings1.md (merged, verbatim) ===== -->
<!-- ===== Adds: scope header, the description-discrimination test, and the     ===== -->
<!-- ===== /drivers-vs-/forecasts divergence finding not present above.         ===== -->
<!-- ============================================================================ -->

---
---

# ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯  Appended findings — `kwopt_findings1.md` (full)  ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

# kwopt — Findings on the Sybilion Forecast API
### From "keyword optimizer" to a forecastability-triage proposal — an evidence-driven pivot
*ZeroOne Hack. Every quantitative claim maps to a cited job ID (verifiable on the Sybilion async-jobs dashboard). Where we did not measure something, we say so.*

**Testing scope:** **39 forecasts · 4 targets · 5 caller inputs tested · ≈€88 · 8.9 h compute** · 12-month MAPE observed 2.66%–10.09%.

---

## Original aim & premise

We built **kwopt** to find the keyword set that minimizes a target's Sybilion **12-month backtest MAPE**, then have it **"use itself"** — reuse past wins to propose keywords for new series in one pass (eventually a local distilled model). The entire design rested on one premise:

> **Keyword choice → which drivers Sybilion attaches → backtest MAPE.**

(Full engineering design: `keyword_optimization_engine_spec.md` — the three-tier architecture, the `S(K)` objective, cache schema, ablation protocol, and build phases.) Phases 0–2 were deliberately structured to **test that premise cheaply before** building the expensive distillation. This report is what the testing revealed.

## TL;DR

- **Keyword *content* has no measurable effect on accuracy** — 3 targets, incl. a synthetic one built from real Brent + S&P 500 (drivers provably in-catalog) and rigged in keywords' favor.
- We tested **every caller-controllable input Sybilion exposes.** All three *semantic* inputs — **keywords, category filters, and description** — are **ignored** by the forecast (opposite descriptions → byte-identical drivers + MAPE). Recency works on only 1 of 3 driver-bearing targets (quantized). **`filters.limit` (driver *count*) is the one input that genuinely works** — but it sets *how many* drivers, not *which*, and the default (max) is already best.
- **Drivers genuinely help — measured by ablation:** suppressing them on macro (`limit=0`) raised MAPE 2.661% → 3.453% (**≈0.79pp, ~23% relative**). But Sybilion **selects which drivers itself from the series' shape**.
- **Attachment ≠ value:** potash attaches 41–107 KB of drivers whose *variation* moves error by zero.
- Conclusion → the useful product isn't input tuning; it's **forecastability triage** (rank which series Sybilion forecasts well, spend only there). **Proposed, not yet built.**

## What we built

`kwopt` — a headless Python engine over the Sybilion REST API: a `/drivers` **relevance screen**, parallel forecast **orchestration**, an **order-invariant cache** (sqlite), a **MAPE objective**, and a **controlled-experiment harness**. (The keyword-distillation/"reuse past wins" layer was designed but left as a stub — the experiments below are *why*.) REST only; the Sybilion MCP server was evaluated and rejected for headless loops (OAuth/per-call approval).

## Method

Monthly series, `pipeline_version v1`, `backtest=true`, `soft_horizon` (not `horizon`). Targets: 2 real World Bank fertilizer benchmarks (urea, potash/MOP), 1 real US industrial-robot import series, and 1 **synthetic control** (`macro_index`), growth = `0.4·oil_return + 0.6·lagged_equity_return + noise` — engineered so Energy + Equities *must* be its true drivers, built from real series so they exist in the catalog. **MAPE is the only usable error metric** (MASE/RMSSE off-scale — see Observations).

---

## Results — every caller input, tested

| Input | What it should do | Verdict | Evidence |
|---|---|---|---|
| **Keywords (content)** | steer *which* drivers attach | ❌ **No effect** | macro `correct`=`wrong`=**2.924%** (worse than no-kw 2.661%); urea 3 sets all **10.091%**; robots 2 sets both **8.506%** |
| **Category filter** | constrain *which* drivers | ❌ **Inert** | relevant `[25,40,46,42,6]` == wrong `[28,10,26]` == **2.924253%** (MAPE/MASE/RMSSE identical), same drivers; "wrong" arm's #1 is Energy-US (out of filter) |
| **Description (text)** | feed semantic driver search | ❌ **Inert** | financial vs agricultural description → **byte-identical 2.661226%** AND identical 28-driver set; **zero** agricultural drivers appeared |
| **Recency** | temporal weighting → MAPE | ⚠️ **1 of 3 driver-rich targets; quantized** | macro ~1pp (4 buckets / 9 points), best @0.6; urea & MOP **0.00pp** |
| **Driver count (`filters.limit`)** | cap *how many* drivers | ✅ **Works — the only one** | 0 drivers→**3.453%**, 15→**2.924%**, 28(full)→**2.661%**; quantized (`limit`=1 and =5 both → 15 drivers) |

**The grouping that matters:** the **three semantic inputs (keywords, filters, description) are all ignored** — Sybilion conditions driver selection on *no* caller-supplied text. The only caller knobs that touch the forecast are *how many* drivers (`limit`) and a quantized recency weighting; **neither steers *which* drivers.**

## Keyword controlled experiment — `macro_index`, recency 0.6

| Run | 12m MAPE | job |
|---|---|---|
| No keywords (baseline) | **2.661%** ← best | `49254b4d` |
| `correct_drivers` (oil/energy/equities) | 2.924% | `4d36a13f` |
| `wrong_drivers` (agriculture/tourism) | 2.924% | `7b3393f5` |

Correct keywords (naming the *true* drivers) did **not** beat wrong keywords, and both *underperformed* sending none — even though the no-keyword baseline found **Energy (#1) + Equities (#3) at importance 100 on its own** (verified in `49254b4d`).

## Description discriminating test — the final lever

Two semantically opposite descriptions of the **same** series — financial ("commodity and equity market movements") vs agricultural ("crops, harvest, livestock, farming, growing-season weather") — title / series / recency / empty-keywords all held constant:

| description | 12m MAPE | drivers | bytes | job |
|---|---|---|---|---|
| financial | 2.661226% | 28 | 68,575 | `18306642` |
| agricultural | 2.661226% | 28 | 68,575 | `c521f732` |

→ Identical to 6 decimals, identical payload, identical 28-driver set (0 unique to either), identical top-8 order. **Not one agricultural driver appeared in the agricultural run.** The forecast ignores caller text entirely — proving the keyword nulls weren't "wrong field," there is *no* steering field.

## Driver ablation — measured driver value

`filters.limit` is enforced, so `limit=0` gave the driver-free macro forecast we previously lacked (recency 0.6, no keywords):

| drivers | 12m MAPE | via |
|---|---|---|
| 0 | 3.453% | `limit=0` |
| 15 | 2.924% | `limit=1`, `limit=5` |
| 28 | 2.661% | full (baseline `49254b4d`) |

→ **On macro, external drivers contribute ≈0.79pp (~23% relative).** A *measured* value, not an inference. Caveats: `limit` is **quantized** (1 and 5 both yield 15 drivers — not a literal top-N cap); the *specific* driver set matters, not just the count (keyword/filter runs with 29–34 drivers still landed in the worse 2.924% bucket); and `limit` only caps *below* what Sybilion selects (28), so no value beats the full baseline.

## The mechanism

Across every keyword / recency / filter / description change, the **high-importance core spine is stable** (Energy, Equities, Global-risk) while only the low-importance tail churns. Recency's effect is **quantized** (9 inputs → 4 MAPE buckets).

A sharp corollary that **answers the spec's own §11 open question**: the cheap `/drivers` endpoint *does* respond to keywords, but `/forecasts` does **not** — they diverge completely. So the engine's screen `S(K)` is a real signal but **disconnected from the objective**; optimizing it optimizes something the forecast ignores. (The sync `/drivers` call is *not* a faithful preview of the async forecast's driver basket.)

**Corrected one-line model:** Sybilion **does** use external drivers (the `limit` ablation proves it), but **selects which ones itself from the series' shape** — **no caller text (keywords, categories, description) steers that.** Only the *count* is caller-exposed (`limit`, already maxed) and recency (quantized). Driver value is real but auto-managed; the inputs meant to steer it don't.

## Cross-target summary — the structural picture

| Target | Type | Baseline MAPE | Signals | Recency | Drivers useful? |
|---|---|---|---|---|---|
| Robots (`b334e08f`) | US robot imports $ | 9.424% | rich ~18 KB | not swept | partial (keywords reshuffle, MAPE flat) |
| Urea (`9d992d09`) | WB fertilizer price | 10.091% | **empty 37 B** | inert | no (none attach) |
| MOP (`4b9af782`) | WB fertilizer price | 9.729% | rich 41–107 KB, varies | inert | no (variation adds nothing) |
| Macro (`49254b4d`) | synthetic cyclical | **2.661%** | rich 67 KB | active ~1pp | **yes — ~0.79pp / ~23% (via `limit=0`)** |

The two WB fertilizer benchmarks are essentially **autoregressive** series the macro driver basket can't improve; the synthetic index responds (to recency, and to driver count). The backend anchors on a fixed Energy/Equities/Global-risk spine regardless of any caller input.

## Attachment ≠ value

Potash is the sharpest case: recency **changes its driver set** (signals jump 41→107 KB across recencies) while MAPE is **byte-identical (9.7287%) across all 6 recencies**. The driver *variation* carries **zero marginal value** — the forecast rides the series' own autoregression.

---

## The pivot — forecastability triage *(proposed, not yet built)*

Since driver *selection* isn't steerable by any caller input and the *count* is already maxed, input optimization is a dead end. The real value for a multi-series portfolio (≈20k units):

> **kwopt as a triage layer:** for each series, cheaply estimate whether Sybilion **adds value over a no-driver baseline**, and route ~€3 forecast spend only where it does.

- The signal is **lift over a baseline**, *not* whether drivers attach (potash proves attachment is a false positive).
- The `limit=0` result hands us an **API-native triage measurement**: a cheap "Sybilion-univariate" forecast vs the full forecast → the gap *is* the driver value (the ablation is the triage test). A free local seasonal-naive baseline works too.
- This is a **specification, not running code** — the baseline + lift-scoring component is designed, not yet implemented.

## Honesty note (boundaries of what we measured)

- **Driver contribution is now measured** (via `limit=0`): ≈0.79pp / ~23% on macro — specific to macro, below Sybilion's marketed 30–70% (different baseline).
- **Recency / limit value beyond n=1 is unproven** — only the synthetic macro target responded; both real fertilizers were inert.
- The robot **+0.92pp** "any-vs-none" came from recovered dashboard jobs, **not** a single controlled run → *suggestive*. The one clean controlled any-vs-none test (macro) showed keywords slightly *hurt*.

## Observations for the Sybilion team *(constructive feedback)*

1. **`keywords`** — accepted and echoed in `input.json` (verified 12/12 match), but content did not change backtest error in any run.
2. **`filters.categories`** — not enforced: a run restricted to Agriculture/Health/Tourism returned Energy/Global-risk/Services as top drivers, identical metrics to the Energy/Financial-restricted run.
3. **`description`** — ignored for driver selection: two opposite descriptions of one series produced byte-identical drivers and MAPE.
4. **`/drivers` vs `/forecasts` diverge** — the sync `/drivers` endpoint responds to keyword text, but the async `/forecasts` driver-selection does **not**. The sync endpoint is *not* a faithful preview of the forecast's driver basket (a natural assumption that doesn't hold).
5. **`filters.limit`** — *is* enforced but **quantized**: `limit=1` and `limit=5` both returned 15 drivers (not a literal top-N cap); `limit=0` special-cases to zero.
6. **`backtest_metrics` MASE / RMSSE off-scale** — e.g. MASE **1788.40** / RMSSE **1444.79** at a 2.924% MAPE forecast (`416cb286`, `3ac73567`), ~10⁷ on robots; `RMSE == MAE` exactly. All three move in lockstep with MAPE — MASE adds no independent resolution.
7. **Latency variance** — identical driver-rich forecasts settled in **11–57 min**; concurrency >2 appeared to slow throughput.

---

## Evidence appendix (verifiable Sybilion job IDs)

| Run | Job ID | 12m MAPE |
|---|---|---|
| Robot baseline (no-kw) | `b334e08f` | 9.424% |
| Robot keyworded (2 different sets) | `98ee0c6d`, `b9a5ea40` | 8.506% (both) |
| Urea baseline (empty signals) | `9d992d09` | 10.091% |
| MOP recency sweep (6 jobs, flat) | `4b9af782`, `3c43a213`, `0a4c5dd4`, `49484d35`, `48cdd1a1`, `180b759c` | 9.7287% (all) |
| Macro baseline (recency 0.6, 28 drivers) | `49254b4d` | **2.661%** |
| Macro keywords correct / wrong | `4d36a13f`, `7b3393f5` | 2.924% (both) |
| Macro recency sweep (9 jobs → 4 buckets) | 0.0`9e77af8e` · 0.5`1087a76a` · 0.6`6b2f24e6` · 1.0`1dcbc841` (+5 more) | 2.661–3.657% |
| Macro category filter — relevant / wrong (identical) | `416cb286`, `3ac73567` | 2.924253% (both) |
| Macro driver ablation — `limit` 0 / 1 / 5 | (baseline ref `49254b4d`) | 3.453% / 2.924% / 2.924% |
| Macro description test — financial / agricultural (identical) | `18306642`, `c521f732` | 2.661226% (both) |

*Scope: 39 forecasts · 4 targets · 5 caller inputs · ≈€88 · 8.9 h compute. One night of evidence-first testing closed an expensive premise (keyword distillation) before it was built — and motivated the triage proposal instead.*
