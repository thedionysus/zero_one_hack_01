# Fertilizer Procurement Decision Agent — Design Brief

**Date:** 2026-05-30 · **Track:** Forecasting AI (Sybilion) · **Status:** design locked except one gating experiment

Derived from a structured grilling session. Source context: `tracks/forecasting-sybilion/Track_Build_on_Probability.md`,
`data/forecast_exploration/FINDINGS.md`, `data/forecast_exploration/diag/DIAG_FINDINGS.md`, `data/README_two_datasets.md`.

---

## 1. Use case (locked)

**Who:** Companies that warehouse fertilizer (e.g. a mid-size Austrian agri co-op).
**What:** A decision agent that turns Sybilion's probabilistic fertilizer-price forecasts into a
**buy-now / wait / split** procurement recommendation, with a target purchase month and a quantified
€-saving versus naive purchasing.
**Why (impact):**
- *Economic* — lower input cost for farmers via smarter procurement timing.
- *Social* — lower input cost → cheaper food → more accessible food.

### Spine: timing (NOT sourcing, NOT driver-research)
The 8 target questions split into three products; we ship **timing** as the spine and the others as
supporting layers:
- **A — Timing (spine):** Q1 (up/down 6–12mo), Q2 (best month to buy), Q3 (buy-more-now-if-rising).
- **B — Sourcing (thin second act):** Q4 (cheaper country), Q5 (Austria landed cost). Data-poor → see §3.
- **C — Drivers (visible-reasoning layer):** Q6 (drivers), Q7 (cross-fertilizer similarity), Q8 (keyword sensitivity).

---

## 2. Architecture (locked)

```
per fertilizer (×5, pre-cached offline):
  Sybilion(forecast + backtest_trajectories + external_signals)
    → conformal recalibration of quantiles (fix overconfident bands) + per-fertilizer TRUST score
    → cost-min order schedule over CORRECTED quantiles × persona params
    → buy / wait / split  +  €-savings vs buy-as-you-go baseline
adaptive (live):
  param shift (storage cost, runway, demand, risk, budget)  → instant deterministic RE-SOLVE
  forecast shock injector (level/trend/band perturbation of CACHED quantiles) → instant re-solve
                                                                + optional true API re-fetch in background
```

- **Decision function (locked):** cost-minimisation over recalibrated quantiles with inventory + carrying
  cost. Inputs: forecast quantiles, current stock & monthly burn (runway), storage/carrying %/yr
  (default 15–25%, editable), risk tolerance. Output: order schedule (when + how much) minimising
  expected landed+holding cost subject to no stockout. **This is the substantive logic** that keeps us
  clear of the banned "thin LLM wrapper".
- **Calibration (locked):** empirical/conformal recalibration from the 13 hindcast windows in
  `backtest_trajectories.json` so the 80% band covers ~80%; correct the systematic under-prediction
  during rises (bias toward buying earlier on uptrends). Emit a **trust score** (coverage + MAPE) that
  down-weights low-trust series (e.g. phosphate-rock's flat tail). Visual: native vs corrected bands.
- **Adaptive (locked):** decision is a **pure function of (forecast, params)** → any mid-run change
  re-solves and renders an old→new diff. Shock injector perturbs cached quantiles (no 3-min wait on stage).

### Tech stack (locked)
- **Decision core:** pure Python (numpy/scipy/pandas), unit-tested, deterministic.
- **Agent layer:** Claude (Anthropic SDK) tool-use loop. Tools = `get_forecast` (Sybilion MCP),
  `recalibrate`, `solve_decision`, `inject_shock`, `set_param`. LLM only at the edges: parse NL
  assumption-shifts → param/shock deltas, and narrate reasoning.
- **Explicitly rejected:** LangChain deepagents (built for open-ended long-horizon research; our flow is
  bounded fetch→calibrate→solve→explain) and LangGraph up front (boilerplate for a 5-node mostly-linear
  flow). LangGraph kept as a *targeted refactor* only if the adapt loop later needs checkpoint/rewind.
- **UI:** Streamlit + Plotly (all-Python). Param **sliders = the live adaptive levers**; **chat box =
  NL curveball** to the agent. Charts: forecast w/ bands, native-vs-corrected calibration overlay,
  decision/€-savings surface, driver-importance-over-horizon. Cache slow fetch via `st.cache_data`,
  hold session state in `st.session_state`.

---

## 3. Data sufficiency — gap analysis (locked)

**Timing spine: sufficient.** Almost every input is either the forecast (have it) or a number the
company supplies about itself:

| Input | Source | Status |
|---|---|---|
| Forecast quantiles P05–P95 | Sybilion | ✅ have |
| Inventory + monthly burn → runway | Company input (persona) | ✅ user-supplied |
| Storage / carrying %/yr | Default 15–25%, editable | ✅ |
| Cost-of-capital | Fold into carrying %, or ECB/FRED (free) | ✅ |
| Risk tolerance | User preference | ✅ |
| Absolute price for €-headline | FOB benchmark proxy × persona tonnage | ⚠️ proxy, defensible |

**Company params enter via a realistic Austrian-warehouse persona, user-editable** (e.g. ~12,000 t/yr
urea, ~3 months runway, 18%/yr carrying). Generic = any company plugs in their own = scalable story.
Persona fields double as adaptive levers.

**Sourcing second act: data-poor → transparent method, not fake data.** Dataset2 (African farm-gate
urea, annual 2010–2018, PPP-adjusted) does NOT represent Austrian sourcing origins, is 8 yrs stale, and
is not level-comparable to the FOB benchmark. We have **zero** freight/duty data. Approach (locked):
- Build a **transparent landed-cost calculator**: `landed = origin FOB + freight + duty + inland`, with
  freight/duty as explicit editable assumptions (cite real EU urea import-duty history).
- Use Dataset2 **only** as a caveated "cross-country price dispersion is real" exhibit — never as
  Austria's actual options. Honest about limits → scores on the rubric's "honest evaluation".

**Social-impact story does NOT depend on geography** — it flows from timing savings lowering input cost.

---

## 4. Impact quantification (locked)

**Two-tier, explicit about rigorous vs illustrative:**
- **Tier 1 — Economic (rigorous, backtested):** at each historical decision point, using only the
  forecast available then (Sybilion hindcast trajectories), simulate the agent's policy vs a
  **buy-as-you-go baseline** over Dataset1 history → honest €/% saved on persona tonnage. This is also
  the **"decision change"** proof (agent policy must differ meaningfully from naive).
  *Stretch:* add a **perfect-hindsight ceiling** → "agent captures N% of achievable savings."
- **Tier 2 — Social (illustrative, cited):** fertilizer ≈ 15–20% of cereal variable cost → pass-through
  to food price, presented as a **cited coefficient with a sensitivity range**, never a hard claim.

---

## 5. Fertilizer scope (locked)
Run **all 5** (urea, DAP, TSP, MOP, phosphate-rock) through the pipeline — just a loop. **Per-fertilizer**
decisions (joint portfolio optimisation = stretch). The **demo-hero fertilizer is chosen by trust
score** after forecasts return (not pre-committed to urea). Remaining 4 populate the trust table →
credibility + partial Q7 answer. Cost ≈ €4–5 across the cheap forecasts.

---

## 6. Drivers (Q6–Q8) — role locked, config pending one experiment

**Key finding (`DIAG_FINDINGS.md`):** the lever to surface drivers is **`recency_factor=0.0`** (full
archive), NOT keywords. At 0.0, urea-class series surface ~35 drivers (MOP potash confirmed). Cost
~3–4× (€2.5–3.3), runtime 8–20 min. Caveats that shape honest use:
1. `importance` ≠ `pearson_correlation`; some high-importance drivers are **spurious** monotonic-trend
   artifacts ("Population–Afghanistan" importance 99.85).
2. Archive is **macro/European** (HICP, EU price-expectation surveys, Equities-World, Commodities-World)
   → drivers are inflation/energy/expectations **proxies, not fertilizer fundamentals** → **context only**.
3. 8–20 min runtime → **cannot fetch live**; must pre-cache.

**Role (locked):** drivers are a **visible-reasoning + adaptivity layer, NOT a decision input** (they
never touch the cost-min math). Build:
- A **spurious-driver filter** (rank by importance AND corr, flag monotonic-trend/population artifacts) —
  substantive, honest work.
- **Driver-importance-over-horizon** viz (rubric explicitly wants this; show a month-1 dominant driver
  fading by month-6).
- Tie a driver to the **adaptive curveball** (e.g. "equities/energy shock" → narrate why forecast/decision
  reacts).
- **Q6** = filtered hero drivers; **Q7** = cross-fertilizer driver-set overlap; **Q8** = documented
  "recency, not keywords" finding (our own controlled experiment is the evidence).

### ✅ GATING EXPERIMENT — RESOLVED (job `fffb5762…`, see `diag/CALIB_FINDINGS.md`)
Ran **urea, `recency_factor=0.0`, `backtest=true`, `soft_horizon=12`, full 360-pt series** (€0.32, ~1 min).
Two findings forced the decision:
1. **No drivers** — `external_signals.json` empty; the cheap/fast run confirms no driver search. Drivers
   require the DIAG config (~120-pt trimmed, backtest=false), NOT recency=0.0 on the full series. So the
   "one coherent config serves decision + drivers" idea is **dead**.
2. **Calibration poor at recency=0.0** — 80% band covers **22.2%** (worse than recency 0.5–0.7's 48%);
   actual above P50 in **96.7%** of months. *Caveat:* the only hindcast window is the 2025–26 rally +
   2026-03 spike tail → partly a window artifact (the stale-data gotcha).

**Decision = TWO forecasts (forced by data):**
- **Decision forecast:** default `recency=0.5` + `backtest=true` + `soft_horizon=12`, full series.
  recency=0.0 buys neither calibration nor drivers, so don't pay for it.
- **Driver forecast (optional, visible-reasoning only):** DIAG-style ~120-pt trimmed + recency=0.0,
  pre-cached, labelled "correlated macro context," not "drivers of this exact forecast."
- **Conformal recalibration + rise-bias correction is non-negotiable** (bands unusable at any recency).
- **Trust score must down-weight/exclude spike-tail hindcast windows**, else every fertilizer looks
  untrustworthy from the 2026-03 artifact alone.

`soft_horizon=12` covers the full 6–12mo question window (360 pts ≫ 120 min required).

---

## 7. Question → answer map

| Q | Question | Answered by |
|---|---|---|
| 1 | Price up/down 6–12mo? | Recalibrated P50 trajectory + trend, soft_horizon=12 |
| 2 | Best month to buy? | Cost-min order schedule → target month |
| 3 | If rising, buy more now? | Cost-min vs carrying cost trade-off + rise-bias correction |
| 4 | Cheaper country historically? | Transparent landed-cost calc; Dataset2 caveated illustration |
| 5 | Austria shipping/import cost? | Parametric freight + cited EU duty in landed-cost calc (flagged illustrative) |
| 6 | Most important drivers? | recency=0.0 external_signals, spurious-filtered, on hero |
| 7 | Driver similarity across fertilizers? | Cross-fertilizer driver-set overlap |
| 8 | Keyword impact on drivers? | Documented: recency_factor is the lever, keywords secondary |

---

## 8. Live-demo readiness vs rubric

| Rubric dimension | How we satisfy it |
|---|---|
| Decision change | Agent buy/wait/split vs buy-as-you-go baseline, backtested €-delta |
| Visible reasoning | Native-vs-corrected bands, trust score, decision math, driver-over-horizon panel |
| Adaptive (mid-run) | Pure re-solve on param/shock; chat curveball → old→new decision diff, no stage wait |
| Commercial/social impact | Two-tier impact §4 |
| Originality | Calibration-correction + trust-gating + honest sourcing/driver treatment |
| Technical sophistication | Conformal recalibration, cost-min optimiser, deterministic adaptive core |

---

## 9. Agent layer — resolved (grill session 2, 2026-05-30)

Decision *core* is built (`lib/recalibration.py`, `lib/trust.py`, `lib/decision.py`, 83 tests green).
These four decisions spec the *agent* around it.

**1. Economic-impact backtest = TWO-TRACK.** (Hard constraint: Sybilion's recency rule rejects series
whose latest point is >1yr old, so historical re-fetch is impossible — the only real hindcast data is
`backtest_trajectories`, last ~13 windows, most stale-excluded.)
- *Primary (rigorous, honest):* run the agent policy on each non-stale Sybilion hindcast window
  (expanding-window residuals → no leakage) vs buy-as-you-go on that window's actuals → €/% saved WITH
  explicit n and a confidence range. Faithful to the real API.
- *Supporting (illustrative):* replay the policy across 30yr of realized prices with a cheap surrogate
  forecast (clearly labelled) + a perfect-hindsight ceiling, to show behaviour across rises/crashes/flat.

**2. Shock injector = BASICS ONLY.**
- *Price-outlook shock:* uniform level shift ±X% applied to the **corrected** band (one transform; the
  decision consumes the corrected band directly). No trend/volatility/spike shocks in v1 (add if time).
- *Company-situation shifts:* go straight to `Persona` (stock/runway, storage cost, demand, risk,
  budget) → instant deterministic re-solve. No forecast touch.
- LLM parses NL → one concrete change; Python applies + re-solves; UI shows old→new diff.

**3. Control flow = FIXED STEPS + CHAT SHELL.** The pipeline (cached forecast → recalibrate → solve →
show) always runs the same fixed order in Python. The LLM does exactly two edge jobs: (a) translate a
typed curveball into one concrete change, (b) narrate before→after in plain English. Not a thin wrapper
— the decision math is substantive. Predictable + debuggable on stage; still conversational.

**4. Demo script = PRICE-RISE FLIPS WAIT → BUY-NOW.** Open on the trust-picked hero fertilizer; agent
shows a calm forecast → recommends WAIT, surfacing visible reasoning (native-vs-corrected bands
21%→83%, trust score, cost-min schedule, € saved vs naive = the *decision change*). Curveball:
"gas spiked, prices +30%" → instant re-solve → flips to BUY-NOW with target month + larger saving
(the *adaptive* moment). One arc, all three judged dimensions.

### Still open (🟡 research, NOT blocking the build)
- Social pass-through coefficient + citation (Tier-2 impact; placeholder "15–20% of cereal cost").
- EU urea import-duty figure to cite in the landed-cost calculator.
- Spurious-driver filter rules (Q6/Q8) + cross-fertilizer driver-overlap metric (Q7), from the separate
  trimmed driver-forecast config.

### Build order (agent layer)
1. Data-loading/caching layer → run all 5 fertilizers through recalibrate→trust→solve, pick trust-hero.
2. Two-track impact backtest → the real € savings headline.
3. `lib/shocks.py` (level shift on corrected band) + Persona re-solve path.
4. Streamlit + Plotly UI (sliders = levers, chat box = curveball) wiring the modules + charts.
5. Thin Claude chat shell: NL curveball → one change → re-solve → narrate.
```
