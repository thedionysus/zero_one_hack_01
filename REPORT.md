# Granary — Forecasting AI (Sybilion)

> Turning a probabilistic price forecast into a defensible procurement decision —
> with the forecast's own confidence bands recalibrated so the decision can be trusted.

---

## Team

- **Arlav Dullahi** — decision engine, app, evaluation
- **h12014883 (TU Wien)** — data engineering, forecast bake-off

**Track:** Forecasting AI (Sybilion)

---

## TL;DR

**Granary** is a fertilizer-procurement decision agent. It takes Sybilion's probabilistic
price forecasts, **recalibrates their (badly overconfident) confidence bands** against
historical residuals, then solves a cost-minimizing **when-and-how-much-to-buy** schedule
for a warehouse — and re-solves live when a user types a real-world curveball
("a supplier fell through", "gas spiked 25%/month"). The headline technical result is the
calibration lift: an "80%" band that historically covered only **~21–50%** of actual prices
is rebuilt to cover **~80%**, which is what makes the buy/wait recommendation defensible.

---

## Problem

A forecast is a number; a number alone doesn't change a decision. Agricultural buyers face a
concrete question every month: **do I buy my urea now, or wait?** Buy too early and you pay
to carry inventory; wait too long and you eat a price spike. Sybilion ships *probabilistic*
forecasts (quantile bands), which is exactly the right input for that trade-off — **except
the bands are not trustworthy as shipped.**

We measured it: on urea, the model's nominal **80% band covered only ~21%** of realized
prices, and actuals sat **above** the median forecast during sustained rallies. A procurement
tool that prices decisions off those bands is confidently wrong. So the problem we chose:
**make the forecast's uncertainty honest, then turn it into a cost-minimizing purchase
schedule a buyer can defend to their CFO.** We focus on five fertilizers (urea, DAP, MOP,
TSP, phosphate rock) and an Austrian warehouse persona.

---

## Approach

- **Conformal recalibration of the bands (`lib/recalibration.py`).** We rebuild each forecast
  month's band from hindcast residuals `r = actual − P50`: `corrected_q(τ) = P50 + quantile(r, τ)`.
  This simultaneously **widens** the band to the true error spread (fixes overconfidence) and
  **shifts** it by the median residual (fixes the low bias). Split-conformal in spirit.
- **Cost-minimizing decision core (`lib/decision.py`, pure stdlib).** Per demand-month, pick the
  purchase month minimizing `price[p]·(1 + carry·(d−p))`. Buy-as-you-go (`p=d`) is always a
  candidate, so the agent **never does worse than naive** (savings ≥ 0). A risk lever prices
  the plan at P50/P70/P80 of the *recalibrated* band.
- **Forecast-agnostic shocks (`lib/shocks.py`).** Two levers: a **level shift** (decision-inert,
  scales magnitude) and a compounding **trend shift** (steepens the curve and can flip the
  recommendation toward BUY_NOW). This is the "adapt to a mid-run assumption shift" mechanism.
- **Claude as a thin NL edge, not the brain (`app/agent.py`).** Claude does exactly two jobs:
  parse one free-text curveball into a lever change, and narrate the before→after diff. The
  decision itself is deterministic stdlib. **No API key? It degrades to a deterministic offline
  parser/narrator** — the demo runs fully offline.
- **Rigorous backtest (`lib/impact.py`).** Leave-one-out hindcast: recalibrate from the *other*
  windows (no leakage), decide on the forecast, **re-price on realized actuals** — "decide on
  the forecast, pay on the truth" — and compare against a perfect-hindsight ceiling.

Runs locally; Streamlit UI + Plotly charts. Decision core has **zero** third-party dependencies.

---

## How to run it

See [`README.md`](./README.md) for full detail. Short version:

```bash
git clone https://github.com/thedionysus/zero_one_hack_01.git
cd zero_one_hack_01
python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app/main.py          # opens http://localhost:8501
```

No API key required — the chat curveball uses a deterministic offline fallback. To enable the
Claude-powered parse/narrate, put `ANTHROPIC_API_KEY=...` in a `.env` file (gitignored).
Run the tests with `.venv/bin/python -m unittest discover -s tests`.

---

## Results

**Headline — calibration lift (the core, verifiable result).** Recalibration moves the in-sample
80% band coverage onto the 80% target across all five fertilizers:

| Fertilizer      | 80% coverage (native → corrected) | Trust score | Default recommendation | Forward saving vs naive* |
|-----------------|-----------------------------------|-------------|------------------------|--------------------------|
| urea            | 0.21 → 0.83                       | 0.48 (med)  | SPLIT                  | €387,250                 |
| phosphate-rock  | 1.00 → 0.83                       | 0.69 (high) | WAIT                   | €166,164                 |
| DAP             | 0.21 → 0.83                       | 0.47 (med)  | SPLIT                  | €11,896                  |
| TSP             | 0.21 → 0.83                       | 0.44 (med)  | SPLIT                  | €9,056                   |
| MOP             | 0.50 → 0.83                       | 0.54 (med)  | SPLIT                  | €0                       |

*\*Forward saving is priced on the **corrected** forecast: optimal schedule vs. a buy-as-you-go
buyer over the 12-month horizon. It isolates the value of **timing**, assuming the forecast is
right.* MOP's **€0 is a correct result**, not a bug — its prices never rise faster than the 1.5%/mo
carrying cost, so buying ahead can't pay and the agent correctly defers to buy-as-you-go.

**Baseline comparison — out-of-sample backtest (`lib/impact.py`).** Decisions made on the
forecast, then paid at realized prices, vs. buy-as-you-go, over the available hindcast windows:

| Fertilizer | Windows | Total saving % (out-of-sample) |
|------------|---------|--------------------------------|
| urea       | 2       | **+2.69%**                     |
| TSP        | 2       | 0.00%                          |
| MOP        | 2       | −0.28%                         |
| DAP        | 2       | −1.07%                         |
| phosphate  | 2       | −3.33%                         |

We report this **honestly**: on a 2-window hindcast the policy is directionally positive on
urea (its strongest, most-rallying series) but **mixed-to-negative elsewhere**. The sample is
too small to claim robust out-of-sample profit — see "What didn't work".

**Evidence.** 163 unit/integration tests pass (`.venv/bin/python -m unittest discover -s tests`).
Calibration diagnostics in `data/forecast_exploration/`.

---

## What worked

- **The calibration story is real and measurable.** The 0.21→0.83 coverage lift on urea is the
  single most defensible thing we built, and it's *visible* in the app as a two-bar chart — the
  jury can see the native band was 4× too narrow.
- **Decision core is provably no-worse-than-naive.** Seeding the argmin with buy-as-you-go means
  `savings ≥ 0` by construction; the level-shift-inertness property is unit-tested.
- **The offline fallback.** The whole adaptive-curveball demo runs with no API key — Claude is an
  enhancement, not a dependency, so the demo can't fail on a network blip.

## What didn't work

- **Out-of-sample savings are thin.** Only 2 scorable hindcast windows survive the staleness
  filter, and on that sample the policy is negative on 3 of 5 fertilizers. The forward (in-model)
  savings look great; the truth-paid backtest says "directional, not proven." We chose to surface
  this rather than hide it.
- **Trust score is a blunt composite.** It blends calibration/skill/accuracy into one number;
  three of five fertilizers land in an undifferentiated "medium" bucket.
- **Python 3.14 friction.** A lazy numpy import inside Plotly, interrupted by a Streamlit rerun,
  left numpy half-initialized and crashed every chart render until restart; we fixed it with an
  eager import (`app/charts.py`).

## What you'd do with another 36 hours

- Widen the hindcast: generate more scorable windows (relax the staleness filter, add
  cross-fertilizer pooling) to get the out-of-sample backtest to statistical significance.
- Add **driver-importance** attribution (which input moved the forecast) to the chart, closing
  the last Sybilion track deliverable.
- Replace the single trust scalar with a per-dimension trust panel.

---

## Track-specific deliverables (Forecasting AI / Sybilion)

- [x] Working application — not slideware (`app/main.py`, Streamlit)
- [x] Backtest results validating the decision logic (`lib/impact.py`, table above)
- [ ] **Driver-importance visualization** — *not yet in the demo* (honest gap; see next steps)
- [x] Agent adapts to a mid-run assumption shift (chat curveball → trend/level shock → re-solve)
- [x] Domain choice rationale stated above in "Problem"

---

## Credits & dependencies

- **Open-source libraries:** streamlit 1.58.0, plotly 6.7.0, anthropic 0.105.2 (UI/chat only;
  the decision core is pure Python stdlib). numpy is a transitive Plotly dependency.
- **Pre-trained models:** none of our own; Sybilion provided the price forecasts.
- **External APIs:** Anthropic Claude (optional NL parse + narration; offline fallback otherwise).
- **AI coding assistants used:** Claude Code.
- **Datasets:** Sybilion fertilizer price forecasts + hindcast trajectories (provided for the track).

---

## A note on honesty

The **forward saving** numbers are priced on our own corrected forecast — they measure timing
value *if the forecast holds*, not realized profit. The **out-of-sample backtest** is the honest
check, and on a small 2-window hindcast it is only convincing for urea. Nothing in the decision
core is mocked; the only stubbed-out path is the offline NL parser, which is a deterministic
keyword/number extractor used when no `ANTHROPIC_API_KEY` is present (clearly labeled in
`app/agent.py`).

---

*Submitted by team Granary for Zero One Hack_01, May 2026.*


<!-- ============================================================================ -->
<!-- ===== APPENDED BELOW: full content of report_draft.md (merged, verbatim) ===== -->
<!-- ============================================================================ -->

---
---

# ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯  Appended draft — `report_draft.md` (full)  ⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯

# Granary — Forecasting AI (Sybilion)

> Turning a probabilistic price forecast into a defensible procurement decision —
> with the forecast's own confidence bands recalibrated so the decision can be trusted.

**Track:** Forecasting AI — *Build on Probability: Decision Agents on a Probabilistic Forecasting API* (Sybilion)
**Team:** Granary
**Repo:** `app/` (Streamlit decision agent) · `lib/` (pure-stdlib decision core) · `data/` (forecast evidence) · `KeywordOptimization/` (input-tuning exploration)

---

## TL;DR

**Granary** is a fertilizer-procurement decision agent for an Austrian agri co-op. It takes Sybilion's
probabilistic price forecasts, **recalibrates their badly overconfident confidence bands** against
historical residuals, then solves a cost-minimizing **when-and-how-much-to-buy** schedule — and
**re-solves live** when a user types a real-world curveball ("a supplier fell through", "gas spiked
25%/month"). The headline result is the calibration lift: an "80%" band that historically covered only
**~21%** of realized urea prices is rebuilt to cover **~83%**, which is what makes the buy/wait
recommendation defensible to a CFO. Everything in the decision core is pure stdlib and **163 tests pass**.

---

## Problem

A forecast is a number; a number alone doesn't change a decision. Agricultural buyers face one concrete
question every month: **buy now, or wait?** Buy too early and you pay to carry inventory; wait too long
and a price spike eats your margin — and those input costs flow straight into the price of food.

Probabilistic forecasts are exactly the right input for that trade-off — *except Sybilion's bands are not
trustworthy as shipped*. We measured it on the real hindcast: on urea, the nominal **80% band covered only
~21%** of realized prices (≈4× too narrow), and actuals sat **above** the median forecast during sustained
rallies because the model mean-reverted real uptrends (`data/forecast_exploration/FINDINGS.md`). A tool
that prices decisions off those raw bands is *confidently wrong*.

So the problem we chose: **make the forecast's uncertainty honest first, then turn it into a
cost-minimizing purchase schedule a buyer can defend.** We scope to five fertilizers — urea, DAP, MOP,
TSP, phosphate rock — and one concrete persona: an Austrian co-op buying **1,000 t/month**, holding
**3,000 t** of stock, at an **18%/yr (1.5%/mo) carrying cost** (`lib/pipeline.py`).

**Why this domain.** Fertilizer prices are volatile, the buy/wait decision is monthly and high-stakes, and
the cost flows through to food security — a domain where probabilistic forecasting genuinely changes a
decision and where a naive "always buy now" buyer leaves money on the table.

---

## Approach

- **Conformal recalibration of the bands (`lib/recalibration.py`).** We rebuild each forecast month's band
  from hindcast residuals `r = actual − P50`: `corrected_q(τ) = P50 + quantile(r, τ)`. This simultaneously
  **widens** the band to the true error spread (fixes overconfidence) and **shifts** it by the median
  residual (fixes the systematic low bias). Split-conformal in spirit, pure stdlib.
- **Cost-minimizing decision core (`lib/decision.py`, zero dependencies).** For each demand month, pick the
  purchase month minimizing `price[p]·(1 + carry·(d−p))`. Buy-as-you-go (`p=d`) is always a candidate, so
  the agent is **provably never worse than naive** — `savings ≥ 0` by construction. A risk lever prices the
  plan at **P50/P70/P80** of the *recalibrated* band; the recommendation is `BUY_NOW / WAIT / SPLIT / COVERED`.
- **Per-series trust, not blind faith (`lib/trust.py`, `lib/forecast_scoring.py`).** We score every series
  against a **lag-12 seasonal-naive** baseline (MASE/RMSSE/MAPE + band coverage) and fold calibration (0.4),
  skill (0.4) and accuracy (0.2) into a trust score. This is honest about *where Sybilion is worth trusting*:
  the bake-off found it **beats seasonal-naive on only 2 of 5 fertilizers** (MOP, phosphate rock).
- **Forecast-agnostic shocks = the adaptive lever (`lib/shocks.py`).** Two levers: a **level shift**
  (decision-inert — scales magnitude, unit-tested to *not* change the plan) and a compounding **trend shift**
  (steepens the curve and can flip the recommendation toward BUY_NOW). This is the "adapt to a mid-run
  assumption change" mechanism the Sunday demo exercises.
- **Claude as a thin NL edge, not the brain (`app/agent.py`).** Claude (Haiku 4.5, tool-use) does exactly
  two jobs: parse one free-text curveball into a lever change, and narrate the before→after diff. The
  decision itself is deterministic stdlib. **No API key needed** — it degrades to a deterministic rule-based
  parser + template narrator (`PROCUREMENT_NO_LLM=1`), so the demo **runs fully offline** and can't fail on a
  network blip.
- **Rigorous truth-paid backtest (`lib/impact.py`).** Leave-one-out hindcast: recalibrate from the *other*
  windows (no leakage), decide on the forecast, then **re-price on realized actuals** — "decide on the
  forecast, pay on the truth" — and compare against buy-as-you-go and a perfect-hindsight ceiling.

The Streamlit app (`app/`) wires these into live sliders + a chat box, with Plotly charts for the forecast
band, native-vs-recalibrated coverage, and the purchase schedule.

---

## How to run it

Requires **Python 3.14** (UI deps are pinned to cp314 wheels; the decision core is pure stdlib and runs on
any 3.x).

```bash
git clone https://github.com/thedionysus/zero_one_hack_01.git
cd zero_one_hack_01

python3.14 -m venv .venv
.venv/bin/pip install -r requirements.txt

.venv/bin/streamlit run app/main.py          # opens http://localhost:8501
```

**Optional — Claude-powered chat:** put `ANTHROPIC_API_KEY=sk-ant-...` in a gitignored `.env`. Without it,
the curveball chat still works via the deterministic offline fallback.

**Tests:**

```bash
.venv/bin/python -m unittest discover -s tests     # 163 tests, all passing
```

**What to try in the demo**

1. Pick a fertilizer in the sidebar; watch the recommendation, target month, and forward saving.
2. Toggle the risk lever (neutral → cautious → averse): the plan biases toward buying earlier.
3. Type a curveball — *"gas spiked, prices rising 25% a month"* — the trend lever moves, the plan
   re-solves, and the recommendation can flip to **BUY_NOW** with a narrated explanation. *(This is the
   mid-run assumption shift.)*
4. Read the two-bar **coverage** chart: native vs. recalibrated 80% band.

---

## Results

**Headline — calibration lift (the core, verifiable result).** Recalibration moves the in-sample 80% band
coverage onto the 80% target across all five fertilizers:

| Fertilizer      | 80% coverage (native → corrected) | Trust score | Default recommendation | Forward saving vs naive* |
|-----------------|-----------------------------------|-------------|------------------------|--------------------------|
| urea            | 0.21 → 0.83                       | 0.48 (med)  | SPLIT                  | €387,250                 |
| phosphate-rock  | 1.00 → 0.83                       | 0.69 (high) | WAIT                   | €166,164                 |
| DAP             | 0.21 → 0.83                       | 0.47 (med)  | SPLIT                  | €11,896                  |
| TSP             | 0.21 → 0.83                       | 0.44 (med)  | SPLIT                  | €9,056                   |
| MOP             | 0.50 → 0.83                       | 0.54 (med)  | SPLIT                  | €0                       |

*\*Forward saving is priced on the **corrected** forecast — the optimal schedule vs. a buy-as-you-go buyer
over the 12-month horizon. It isolates the value of **timing**, assuming the forecast holds.* MOP's **€0 is a
correct result**, not a bug: its prices never rise faster than the 1.5%/mo carrying cost, so buying ahead
can't pay and the agent correctly defers to buy-as-you-go. phosphate-rock's native **1.00** coverage is a
degenerate flat-tail artifact (over-wide bands), which recalibration tightens *down* to 0.83 — the lift goes
both ways.

**Baseline comparison — out-of-sample backtest (`lib/impact.py`).** Decisions made on the forecast, then
paid at realized prices, vs. buy-as-you-go, over the available hindcast windows:

| Fertilizer | Windows | Total saving % (out-of-sample) |
|------------|---------|--------------------------------|
| urea       | 2       | **+2.69%**                     |
| TSP        | 2       | 0.00%                          |
| MOP        | 2       | −0.28%                         |
| DAP        | 2       | −1.07%                         |
| phosphate  | 2       | −3.33%                         |

We report this **honestly**: on a 2-window hindcast the policy is directionally positive on urea (its
strongest, most-rallying series) but **mixed-to-negative elsewhere**. The sample is too small to claim
robust out-of-sample profit — see "What didn't work".

**Evidence.** 163 unit/integration tests pass. Calibration diagnostics and the 15-forecast bake-off
(3 recency variants × 5 fertilizers) live in `data/forecast_exploration/`; the bake-off champions
(`champions.json`) are the agent's input contract.

---

## What worked

- **The calibration story is real, measured, and visible.** The 0.21→0.83 coverage lift on urea is the
  single most defensible thing we built, and it's a two-bar chart in the app — the jury can *see* the native
  band was ~4× too narrow.
- **The decision core is provably no-worse-than-naive.** Seeding the argmin with buy-as-you-go means
  `savings ≥ 0` by construction; the level-shift inertness property is unit-tested.
- **Trust is per-series and earned.** We don't pretend Sybilion is good everywhere — the bake-off shows it
  loses to seasonal-naive on 3 of 5 series, and the trust score down-weights those.
- **The offline fallback.** The whole adaptive-curveball demo runs with no API key. Claude is an
  enhancement, not a dependency.

## What didn't work

- **Out-of-sample savings are thin.** Only 2 scorable hindcast windows survive the staleness filter, and on
  that sample the policy is negative on 3 of 5 fertilizers. Forward (in-model) savings look great; the
  truth-paid backtest says "directional, not proven." We chose to surface this, not hide it.
- **Driver hints don't steer Sybilion** (see exploration section). We spent real budget proving the
  keyword/filter levers are inert before concluding the value lives in *recalibration + triage*, not input
  tuning. An expensive lesson, learned cheaply on purpose.
- **The trust score is a blunt composite.** It collapses calibration/skill/accuracy into one number; three
  of five fertilizers land in an undifferentiated "medium" bucket.
- **Python 3.14 friction.** A lazy numpy import inside Plotly, interrupted by a Streamlit rerun, left numpy
  half-initialized and crashed every chart render until restart; fixed with an eager import (`app/charts.py`).

## What you'd do with another 36 hours

- **Wire the driver-importance panel into the demo** (the one open track deliverable, below). The data
  already exists — `external_signals.json` per job carries each driver's importance (0–100) and signed
  direction by horizon — it just isn't rendered in the Streamlit UI yet.
- **Widen the hindcast** to reach significance: relax the staleness filter and pool windows across
  fertilizers so the out-of-sample backtest stops resting on 2 windows.
- **Build the forecastability-triage layer** the KeywordOptimization study proposed: cheaply rank which of a
  20k-series portfolio Sybilion actually beats a baseline on, and spend the ~€3/forecast only there.
- **Replace the single trust scalar** with a per-dimension trust panel (calibration / skill / accuracy shown
  separately).

---

## Track deliverables (Forecasting AI / Sybilion)

| Deliverable | Status | Where |
|---|---|---|
| Working agent/application — not slideware | ✅ | `app/main.py` (Streamlit), 163 tests pass |
| Backtest validating the decision logic | ✅ | `lib/impact.py` truth-paid LOO backtest + table above |
| Agent adapts to a mid-run assumption shift on Sunday | ✅ | chat curveball → trend/level shock → re-solve → narrated diff (`app/agent.py`, `lib/shocks.py`) |
| Visible reasoning (driver/band/decision surfaced, not a black box) | ◑ | recalibrated band + coverage + purchase schedule charts shown; **driver-importance not yet a live chart** |
| Driver-importance visualization in the demo | ⬜ | **Honest gap.** Driver importance is *measured* (ablation study, exploration section) and the data is in `external_signals.json`, but not rendered in the app (`app/main.py:220` — "drivers panel: not wired in v1"). |
| Domain-choice rationale in the README | ✅ | `README.md` + "Problem" above |

We mark the driver-importance chart as a **known, honest gap** rather than claim it. We measured driver
importance rigorously (the ablation below); we did not get it onto the procurement canvas in time.

---

## Exploration: KeywordOptimization — can we steer Sybilion's drivers? (a rigorous negative result)

> This is a **side exploration, not the core product.** It is worth reading because it is *why* the core
> agent invests in **recalibration and trust** instead of input tuning — a conclusion we paid ~€100 of API
> budget and 34 forecast jobs to reach. All raw evidence is checked into the repo:
> `KeywordOptimization/sybilion_jobs/<job_id>/` (34 jobs × 5 artifacts), with the design in
> `keyword_optimization_engine_spec.md` and the full write-up in `kwopt_findings_last.md`.

**The premise we set out to prove.** *Keyword choice → which drivers Sybilion attaches → backtest MAPE.* If
true, we could optimize keywords per series and then distil the loop into a small local model that proposes
near-optimal keywords in one pass — eliminating the €3.14/run cost.

**What we built (`KeywordOptimization/kwopt/`).** A headless Python engine over the Sybilion REST API:
- a cheap `/drivers` **relevance screen** as a proxy objective (validated: **6/6** of a real forecast's used
  drivers also surfaced as `/drivers` candidates),
- parallel forecast **orchestration** with an **order-invariant SQLite cache** (so permuted keyword sets are
  one cache hit, not two paid runs),
- a **MAPE objective** (the only usable error metric — MASE/RMSSE come back off-scale, ~10⁷), and
- a **controlled-experiment harness** for ablation.
- *(The keyword-distillation "reuse past wins" layer was designed but deliberately left a stub — the
  experiments below are why we stopped before building it.)* We evaluated the Sybilion **MCP server** and
  chose **REST** for the headless loop (per-call OAuth approval doesn't suit automated fan-out).

**What the evidence said — every input lever Sybilion exposes, tested:**

| Lever | Should do | Verdict | Evidence (job IDs in repo) |
|---|---|---|---|
| **Keyword content** | steer *which* drivers attach | **No measurable effect** | macro `correct`=`wrong`=**2.924%**, both *worse* than no-keywords **2.661%** (`4d36a13f`, `7b3393f5`, `49254b4d`); urea 3 sets all 10.091%; robots 2 sets both 8.506% |
| **Category filter** | constrain *which* drivers | **Inert (not enforced)** | "relevant" vs "wrong" category arms identical to 6 decimals (`416cb286`, `3ac73567`) |
| **Recency** | temporal weighting | works on **1 of 3** targets; quantized; optimum = our default 0.6 | macro ~1pp swing over 9 jobs → 4 buckets; urea/MOP inert |
| **`filters.limit`** (driver *count*) | cap how many drivers | **The one lever that works** — but caps count, not *which*, and the default max is already best | macro 0→3.453%, 15→2.924%, 28(full)→**2.661%** |

**The decisive measurement.** Because `limit=0` yields a driver-free forecast, we could finally *measure*
driver value by ablation: on the synthetic macro target, external drivers contributed **≈0.79pp (~23%
relative MAPE reduction)**. So drivers genuinely help — **but Sybilion selects which ones itself from the
series' shape, and keywords/category filters can't steer that.** "Attachment ≠ value": potash (MOP) attaches
41–107 KB of drivers whose variation moves error by *exactly zero* across recencies.

**The pivot (proposed, not built).** Since driver *selection* isn't steerable and the *count* is already
maxed, input optimization is a dead end. The real value for a 20k-series portfolio is **forecastability
triage**: for each series, cheaply estimate whether Sybilion beats a no-driver baseline (the `limit=0` run
*is* that test), and route the ~€3/forecast spend only where it pays. This directly informed the core
agent's per-series **trust score**.

**Constructive feedback for Sybilion** (all reproducible from the checked-in jobs): `filters.categories`
appears unenforced; `filters.limit` is enforced but quantized (`limit=1` and `=5` both return 15 drivers);
and `backtest_metrics` MASE/RMSSE read off-scale (~10⁷) while `RMSE == MAE` exactly — only MAPE was usable.

---

## Credits & dependencies

- **Forecasting engine:** **Sybilion** hosted forecasting API (provided for the track) — probabilistic
  monthly quantile forecasts, backtest trajectories, and external-signal/driver importance. We do **not**
  train a forecasting model; all forecasting is Sybilion's.
- **Open-source libraries:** `streamlit==1.58.0`, `plotly==6.7.0`, `anthropic==0.105.2` (UI/chat only); the
  KeywordOptimization engine additionally uses `requests`. The decision core (`lib/`) is **pure Python
  stdlib**; numpy is only a transitive Plotly dependency.
- **Models:** none of our own. Anthropic **Claude (Haiku 4.5)** is used as an optional NL parse + narration
  edge, with a deterministic offline fallback.
- **Datasets:** World Bank "Pink Sheet" fertilizer benchmark prices (urea, DAP, TSP, rock phosphate, MOP),
  monthly Apr 1996–Mar 2026, via IndexMundi (free/open); plus a synthetic macro control series built from
  real Brent + S&P 500 returns for the keyword experiments. Provenance in `data/CITATIONS.md` and
  `data/README_two_datasets.md`.
- **AI coding tools:** Claude Code.
- **Raw forecast evidence:** 34 Sybilion forecast jobs (5 artifacts each) checked into
  `KeywordOptimization/sybilion_jobs/`, plus the bake-off artifacts in `data/forecast_exploration/`.

---

## A note on honesty

The **forward saving** numbers are priced on our own corrected forecast — they measure timing value *if the
forecast holds*, not realized profit. The **out-of-sample backtest** is the honest check, and on a small
2-window hindcast it is only convincing for urea. The **driver-importance chart is not yet in the demo**, and
we say so rather than claim it. Nothing in the decision core is mocked; the only stubbed path is the offline
NL parser (a deterministic keyword/number extractor used when no `ANTHROPIC_API_KEY` is present, clearly
labeled in `app/agent.py`), and the keyword-distillation layer, which we documented as designed-but-unbuilt
because the experiments showed it wouldn't pay.

---

*Submitted by team Granary for Zero One Hack_01, May 2026.*
